"""
Action handlers for chat-side effects.
"""
from __future__ import annotations

from typing import Callable, Optional

from app.rag import pipeline


def register_bootstrap_callbacks(
    on_progress: Optional[Callable[[float, str], None]],
    on_done: Optional[Callable[[bool, str], None]],
) -> None:
    pipeline.register_auto_download_callbacks(on_progress=on_progress, on_done=on_done)


def get_bootstrap_state():
    return pipeline.get_bootstrap_event()


def ingest_document(file_path: str, on_done: Optional[Callable[[bool, str], None]] = None) -> None:
    pipeline.ingest_document(file_path, on_done=on_done)


def clear_documents() -> None:
    pipeline.clear_all_documents()


def list_documents() -> list[dict]:
    return pipeline.list_documents()


def delete_document(doc_id: int) -> None:
    pipeline.delete_document_by_id(doc_id)


def ask_rag(
    question: str,
    stream_cb: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    pipeline.ask(question, stream_cb=stream_cb, on_done=on_done)


def ask_direct(
    question: str,
    history: list | None,
    summary: str,
    stream_cb: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    pipeline.chat_direct(
        question,
        history=history,
        summary=summary,
        stream_cb=stream_cb,
        on_done=on_done,
    )
