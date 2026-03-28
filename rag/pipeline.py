"""
pipeline.py - Orchestrates document ingest, retrieval and generation.
"""
from __future__ import annotations

import copy
import os
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
_auto_dl_state_cb: Optional[Callable[[dict], None]] = None
_latest_bootstrap_state: dict = {
    "overall_status": "preparing",
    "overall_text": "Preparing AI models...",
    "overall_fraction": 0.0,
    "models": {
        "qwen": {
            "id": "qwen",
            "label": "Qwen model",
            "filename": QWEN_MODEL["filename"],
            "fraction": 0.0,
            "status": "Pending",
        },
        "nomic": {
            "id": "nomic",
            "label": "Nomic embeddings",
            "filename": NOMIC_MODEL["filename"],
            "fraction": 0.0,
            "status": "Pending",
        },
    },
}
_service_probe_lock = threading.Lock()
_service_probe_active = False


def _service_qwen_ready(wait_seconds: float = 0.0, per_try_timeout: float = 0.35) -> bool:
    import urllib.request

    attempts = max(1, int(wait_seconds / 0.5))
    for i in range(attempts):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8082/health",
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
    on_state: Optional[Callable[[dict], None]] = None,
) -> None:
    """
    Register UI callbacks for model bootstrap progress.
    If the model is already ready, on_done fires immediately.
    """
    global _auto_dl_progress_cb, _auto_dl_done_cb, _auto_dl_state_cb
    _auto_dl_progress_cb = on_progress
    _auto_dl_done_cb = on_done
    _auto_dl_state_cb = on_state

    if on_state:
        on_state(copy.deepcopy(_latest_bootstrap_state))

    if on_done and llm.is_loaded():
        on_done(True, "Models ready: Qwen + Nomic")
        return

    # Avoid even short socket checks on UI thread; do this in background.
    def _service_probe():
        if _service_qwen_ready(wait_seconds=0.0):
            llm._backend = "llama_server"
            llm._model_path = model_dest_path(QWEN_MODEL["filename"])
            _set_bootstrap_state(
                overall_status="ready",
                overall_text="Offline ready. AI engine connected.",
                overall_fraction=1.0,
                qwen_frac=1.0,
                qwen_status="Ready (service)",
            )
            if on_done:
                on_done(True, "Models ready: Qwen + Nomic (service)")

    threading.Thread(target=_service_probe, daemon=True).start()


def _set_bootstrap_state(
    *,
    overall_status: Optional[str] = None,
    overall_text: Optional[str] = None,
    overall_fraction: Optional[float] = None,
    qwen_frac: Optional[float] = None,
    qwen_status: Optional[str] = None,
    nomic_frac: Optional[float] = None,
    nomic_status: Optional[str] = None,
) -> None:
    if overall_status is not None:
        _latest_bootstrap_state["overall_status"] = overall_status
    if overall_text is not None:
        _latest_bootstrap_state["overall_text"] = overall_text
    if overall_fraction is not None:
        _latest_bootstrap_state["overall_fraction"] = max(0.0, min(1.0, overall_fraction))
    if qwen_frac is not None:
        _latest_bootstrap_state["models"]["qwen"]["fraction"] = max(0.0, min(1.0, qwen_frac))
    if qwen_status is not None:
        _latest_bootstrap_state["models"]["qwen"]["status"] = qwen_status
    if nomic_frac is not None:
        _latest_bootstrap_state["models"]["nomic"]["fraction"] = max(0.0, min(1.0, nomic_frac))
    if nomic_status is not None:
        _latest_bootstrap_state["models"]["nomic"]["status"] = nomic_status
    if _auto_dl_state_cb:
        _auto_dl_state_cb(copy.deepcopy(_latest_bootstrap_state))


def _emit_progress(frac: float, text: str) -> None:
    if _auto_dl_progress_cb:
        _auto_dl_progress_cb(frac, text)


def _wait_for_service_backend(
    qwen_path: str,
    timeout_seconds: float = 240.0,
    fail_message: str = (
        "AI engine unavailable. Tap Retry to restart engine probe "
        "(network is only required for first-time downloads)."
    ),
) -> None:
    global _service_probe_active
    with _service_probe_lock:
        if _service_probe_active:
            return
        _service_probe_active = True

    def _run():
        global _service_probe_active
        try:
            start = time.time()
            delay = 1.0
            attempt = 0
            _set_bootstrap_state(
                overall_status="starting_engine",
                overall_text="Starting AI engine...",
                qwen_status="Waiting for service...",
            )
            _emit_progress(0.98, "Starting AI engine...")

            while (time.time() - start) < timeout_seconds:
                if _service_qwen_ready(wait_seconds=2.0, per_try_timeout=0.5):
                    llm._backend = "llama_server"
                    llm._model_path = qwen_path
                    _set_bootstrap_state(
                        overall_status="ready",
                        overall_text="Offline ready. AI engine connected.",
                        overall_fraction=1.0,
                        qwen_frac=1.0,
                        qwen_status="Ready (service)",
                        nomic_frac=1.0,
                        nomic_status="Ready",
                    )
                    _emit_progress(1.0, "Offline ready. AI engine connected.")
                    if _auto_dl_done_cb:
                        _auto_dl_done_cb(True, "Models ready: Qwen + Nomic")
                    return

                attempt += 1
                msg = f"Starting AI engine... retry {attempt}"
                _set_bootstrap_state(
                    overall_status="starting_engine",
                    overall_text=msg,
                    qwen_status=msg,
                )
                _emit_progress(0.98, msg)
                time.sleep(delay)
                delay = min(delay * 1.5, 10.0)

            _set_bootstrap_state(
                overall_status="error",
                overall_text=fail_message,
                qwen_status="Service not reachable.",
            )
            if _auto_dl_done_cb:
                _auto_dl_done_cb(False, fail_message)
        finally:
            with _service_probe_lock:
                _service_probe_active = False

    threading.Thread(target=_run, daemon=True).start()


def retry_engine_probe() -> None:
    """Retry Android service probe after a bootstrap-engine failure."""
    qwen_path = model_dest_path(QWEN_MODEL["filename"])
    if not os.path.isfile(qwen_path):
        if _auto_dl_done_cb:
            _auto_dl_done_cb(False, "Qwen model file missing. Re-run first-launch download.")
        return
    _wait_for_service_backend(qwen_path)


def init() -> None:
    """Call once at app start: set up DB + retriever + model bootstrap."""
    init_db()
    retriever.reload()
    _start_auto_download()


def _start_auto_download() -> None:
    """Ensure Qwen + Nomic are on disk, then load/connect Qwen."""

    def _progress(frac: float, text: str):
        _emit_progress(frac, text)

    def _state(state: dict):
        _latest_bootstrap_state.update(copy.deepcopy(state))
        if _auto_dl_state_cb:
            _auto_dl_state_cb(copy.deepcopy(_latest_bootstrap_state))

    def _done(success: bool, message: str):
        qwen_path = model_dest_path(QWEN_MODEL["filename"])

        if not success:
            if _auto_dl_done_cb:
                _auto_dl_done_cb(False, message)
            return

        if llm.is_loaded():
            _set_bootstrap_state(
                overall_status="ready",
                overall_text="Offline ready. AI engine loaded.",
                overall_fraction=1.0,
            )
            if _auto_dl_done_cb:
                _auto_dl_done_cb(True, "Models ready: Qwen + Nomic")
            return

        # Android policy: service-first only. Do not fallback to in-app load.
        if os.environ.get("ANDROID_PRIVATE"):
            _wait_for_service_backend(qwen_path)
            return

        # Prefer the service-owned Qwen server if it is up.
        if _service_qwen_ready(wait_seconds=12.0):
            llm._backend = "llama_server"
            llm._model_path = qwen_path
            _set_bootstrap_state(
                overall_status="ready",
                overall_text="Offline ready. AI engine connected.",
                overall_fraction=1.0,
                qwen_frac=1.0,
                qwen_status="Ready (service)",
            )
            if _auto_dl_done_cb:
                _auto_dl_done_cb(True, "Models ready: Qwen + Nomic")
            return

        # Fallback: load/connect from app process.
        load_model(
            qwen_path,
            on_progress=_progress,
            on_done=lambda ok, msg: (_auto_dl_done_cb(ok, msg) if _auto_dl_done_cb else None),
        )

    auto_download_default(on_progress=_progress, on_done=_done, on_state=_state)


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

