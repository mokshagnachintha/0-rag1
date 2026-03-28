"""
pipeline.py - Orchestrates document ingest, retrieval and generation.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .chunker import process_document
from .db import (
    get_conn,
    init_db,
    insert_chunks,
    insert_document,
    update_doc_chunk_count,
)
from .downloader import NOMIC_MODEL, QWEN_MODEL, auto_download_default, model_dest_path
from .llm import build_direct_prompt, build_rag_prompt, list_available_models, llm
from .retriever import HybridRetriever


# Module-level retriever (shared across the whole app)
retriever = HybridRetriever(alpha=0.5)


# ------------------------------------------------------------------ #
#  Initialisation                                                    #
# ------------------------------------------------------------------ #

_auto_dl_progress_cb: Optional[Callable[[float, str], None]] = None
_auto_dl_done_cb: Optional[Callable[[bool, str], None]] = None


def _service_qwen_ready(wait_seconds: float = 0.0) -> bool:
    import urllib.request

    attempts = max(1, int(wait_seconds / 0.5))
    for i in range(attempts):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8082/health", timeout=1) as r:
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
    Register UI callbacks for model bootstrap progress.
    If the model is already ready, on_done fires immediately.
    """
    global _auto_dl_progress_cb, _auto_dl_done_cb
    _auto_dl_progress_cb = on_progress
    _auto_dl_done_cb = on_done

    if on_done and llm.is_loaded():
        on_done(True, "Models ready: Qwen + Nomic")
        return

    if _service_qwen_ready(wait_seconds=0.0):
        llm._backend = "llama_server"
        llm._model_path = model_dest_path(QWEN_MODEL["filename"])
        if on_done:
            on_done(True, "Models ready: Qwen + Nomic (service)")


def init() -> None:
    """Call once at app start: set up DB + retriever + model bootstrap."""
    init_db()
    retriever.reload()
    _start_auto_download()


def _start_auto_download() -> None:
    """Ensure Qwen + Nomic are on disk, then load/connect Qwen."""

    def _progress(frac: float, text: str):
        if _auto_dl_progress_cb:
            _auto_dl_progress_cb(frac, text)

    def _done(success: bool, message: str):
        qwen_path = model_dest_path(QWEN_MODEL["filename"])

        if not success:
            if _auto_dl_done_cb:
                _auto_dl_done_cb(False, message)
            return

        if llm.is_loaded():
            if _auto_dl_done_cb:
                _auto_dl_done_cb(True, "Models ready: Qwen + Nomic")
            return

        # Prefer the service-owned Qwen server if it is up.
        if _service_qwen_ready(wait_seconds=12.0):
            llm._backend = "llama_server"
            llm._model_path = qwen_path
            if _auto_dl_done_cb:
                _auto_dl_done_cb(True, "Models ready: Qwen + Nomic")
            return

        # Fallback: load/connect from app process.
        load_model(
            qwen_path,
            on_progress=_progress,
            on_done=lambda ok, msg: (_auto_dl_done_cb(ok, msg) if _auto_dl_done_cb else None),
        )

    auto_download_default(on_progress=_progress, on_done=_done)


# ------------------------------------------------------------------ #
#  Document ingestion                                                #
# ------------------------------------------------------------------ #

def ingest_document(
    file_path: str,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Ingest a .txt or .pdf file in a background thread.
    Starts Nomic server lazily on first call.
    """

    def _run():
        try:
            # Lazy-start Nomic server only when indexing is needed.
            import os

            nomic_path = model_dest_path(NOMIC_MODEL["filename"])
            if os.path.isfile(nomic_path):
                from .llm import _NOMIC_PORT, _probe_port, start_nomic_server

                if not _probe_port(_NOMIC_PORT):
                    start_nomic_server(nomic_path)

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


# ------------------------------------------------------------------ #
#  Model management                                                  #
# ------------------------------------------------------------------ #

def load_model(
    model_path: str,
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """Load a GGUF model in a background thread."""

    def _run():
        try:
            llm.load(model_path, on_progress=on_progress)
            if on_done:
                on_done(True, f"Model loaded: {Path(model_path).name}")
        except Exception as exc:
            if on_done:
                on_done(False, f"Failed to load model: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def get_available_models() -> list[str]:
    return list_available_models()


def clear_all_documents() -> None:
    """Delete all ingested documents + chunks and reset the in-memory retriever."""
    with get_conn() as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM documents")
    retriever.reload()


def is_model_loaded() -> bool:
    return llm.is_loaded()


# ------------------------------------------------------------------ #
#  Query                                                             #
# ------------------------------------------------------------------ #

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

    def _run():
        try:
            if not llm.is_loaded():
                if on_done:
                    on_done(False, "No LLM model loaded. Please load a GGUF model first.")
                return

            prompt = build_direct_prompt(question, history, summary)
            answer = llm.generate(prompt, stream_cb=stream_cb).strip()
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

    def _run():
        try:
            if retriever.is_empty():
                if on_done:
                    on_done(False, "No documents ingested yet.")
                return

            if not llm.is_loaded():
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
            answer = llm.generate(prompt, stream_cb=stream_cb).strip()

            if on_done:
                on_done(True, answer)

        except Exception as exc:
            if on_done:
                on_done(False, f"Error during inference: {exc}")

    threading.Thread(target=_run, daemon=True).start()

