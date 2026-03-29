"""
pipeline.py - Orchestrates document ingest, retrieval and generation.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from app.config import QWEN_SERVER_PORT
from app.runtime.bootstrap import BootstrapCoordinator
from app.runtime.model_runtime import LlamaModelRuntime, ModelRuntime

from .chunker import process_document
from .downloader import NOMIC_MODEL, QWEN_MODEL, auto_download_default, model_dest_path
from .llm import build_direct_prompt, build_rag_prompt
from .retriever import HybridRetriever
from .storage import (
    delete_document as storage_delete_document,
    get_conn,
    init_db,
    insert_chunks,
    insert_document,
    list_documents as storage_list_documents,
    update_doc_chunk_count,
)


# Module-level retriever/runtime (shared across the whole app)
retriever = HybridRetriever(alpha=0.5)
runtime: ModelRuntime = LlamaModelRuntime()
bootstrap = BootstrapCoordinator()


def _service_qwen_ready(wait_seconds: float = 0.0, per_try_timeout: float = 0.35) -> bool:
    import urllib.request

    attempts = max(1, int(wait_seconds / 0.5))
    for i in range(attempts):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{QWEN_SERVER_PORT}/health",
                timeout=per_try_timeout,
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        if i < attempts - 1:
            time.sleep(0.5)
    return False


def register_auto_download_callbacks(
    on_progress: Optional[Callable[[float, str], None]],
    on_done: Optional[Callable[[bool, str], None]],
) -> None:
    """
    Register UI callbacks for model bootstrap lifecycle.
    """
    bootstrap.register_callbacks(on_progress=on_progress, on_done=on_done)

    # Fast-path: if model already loaded or service already healthy, mark ready.
    if runtime.is_loaded():
        bootstrap.emit_ready("Models ready: Qwen + Nomic")
        return

    def _service_probe() -> None:
        if _service_qwen_ready(wait_seconds=0.0):
            qwen_path = model_dest_path(QWEN_MODEL["filename"])
            try:
                runtime.connect_external_server(qwen_path)
                bootstrap.emit_ready("Models ready: Qwen + Nomic (service)")
            except Exception:
                pass

    threading.Thread(target=_service_probe, daemon=True).start()


def init() -> None:
    """Call once at app start: set up DB + retriever + model bootstrap."""
    init_db()
    retriever.reload()
    _start_auto_download()


def _start_auto_download() -> None:
    """Ensure Qwen + Nomic are on disk, then load/connect Qwen."""

    def _progress(frac: float, text: str) -> None:
        bootstrap.emit_downloading(frac, text)

    def _done(success: bool, message: str) -> None:
        qwen_path = model_dest_path(QWEN_MODEL["filename"])

        if not success:
            bootstrap.emit_error(message)
            return

        if runtime.is_loaded():
            bootstrap.emit_ready("Models ready: Qwen + Nomic")
            return

        # Prefer the service-owned Qwen server if it is up.
        if _service_qwen_ready(wait_seconds=12.0):
            try:
                runtime.connect_external_server(qwen_path)
                bootstrap.emit_ready("Models ready: Qwen + Nomic")
                return
            except Exception:
                pass

        # Fallback: load/connect from app process.
        load_model(
            qwen_path,
            on_progress=_progress,
            on_done=lambda ok, msg: (
                bootstrap.emit_ready(msg if ok else "") if ok else bootstrap.emit_error(msg)
            ),
        )

    auto_download_default(on_progress=_progress, on_done=_done)


def ingest_document(
    file_path: str,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Ingest a .txt or .pdf file in a background thread.
    Starts Nomic server lazily on first call.
    """

    def _run() -> None:
        try:
            nomic_path = model_dest_path(NOMIC_MODEL["filename"])
            if os.path.isfile(nomic_path) and isinstance(runtime, LlamaModelRuntime):
                runtime.start_nomic_server_if_needed(nomic_path)

            name = Path(file_path).name
            doc_id = insert_document(name, file_path)
            chunks = process_document(file_path)
            insert_chunks(doc_id, chunks)
            update_doc_chunk_count(doc_id, len(chunks))
            retriever.reload()
            if on_done:
                on_done(True, f"Ingested '{name}' - {len(chunks)} chunks")
        except Exception as exc:
            import traceback

            traceback.print_exc()
            if on_done:
                on_done(False, f"Error: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def load_model(
    model_path: str,
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """Load a GGUF model in a background thread."""

    def _run() -> None:
        try:
            runtime.load(model_path, on_progress=on_progress)
            if on_done:
                on_done(True, f"Model loaded: {Path(model_path).name}")
        except Exception as exc:
            if on_done:
                on_done(False, f"Failed to load model: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def get_available_models() -> list[str]:
    if isinstance(runtime, LlamaModelRuntime):
        return runtime.available_models()
    return []


def clear_all_documents() -> None:
    """Delete all ingested documents + chunks and reset the in-memory retriever."""
    with get_conn() as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM documents")
    retriever.reload()


def is_model_loaded() -> bool:
    return runtime.is_loaded()


def get_bootstrap_event():
    """Return the latest bootstrap state snapshot for UI surfaces."""
    return bootstrap.event()


def list_documents() -> list[dict]:
    """List ingested documents sorted by most recent first.

    Safe during very early startup before init() has run.
    """
    try:
        init_db()
        return storage_list_documents()
    except Exception:
        return []


def delete_document_by_id(doc_id: int) -> None:
    """Delete a document and refresh the in-memory retriever index."""
    try:
        init_db()
        storage_delete_document(doc_id)
    finally:
        retriever.reload()


def chat_direct(
    question: str,
    history: list | None = None,
    summary: str = "",
    stream_cb: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Chat directly with the LLM (no retrieval).
    history: last 3 verbatim (user, assistant) turns.
    summary: compressed plain-text summary of older turns.
    """

    def _run() -> None:
        try:
            if not runtime.is_loaded():
                if on_done:
                    on_done(False, "No LLM model loaded. Please load a GGUF model first.")
                return

            prompt = build_direct_prompt(question, history, summary)
            answer = runtime.generate(prompt, stream_cb=stream_cb).strip()
            if on_done:
                on_done(True, answer)

        except Exception as exc:
            if on_done:
                on_done(False, f"Error during inference: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def ask(
    question: str,
    stream_cb: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Run a RAG query in a background thread.
    Retrieves top-2 chunks to fit mobile context budget.
    """

    def _run() -> None:
        try:
            if retriever.is_empty():
                if on_done:
                    on_done(False, "No documents ingested yet.")
                return

            if not runtime.is_loaded():
                if on_done:
                    on_done(False, "No LLM model loaded. Please load a GGUF model first.")
                return

            results = retriever.query(question, top_k=2)
            if not results:
                if on_done:
                    on_done(False, "No relevant context found.")
                return

            context_chunks = [text for text, _ in results]
            prompt = build_rag_prompt(context_chunks, question)
            answer = runtime.generate(prompt, stream_cb=stream_cb).strip()

            if on_done:
                on_done(True, answer)

        except Exception as exc:
            if on_done:
                on_done(False, f"Error during inference: {exc}")

    threading.Thread(target=_run, daemon=True).start()

