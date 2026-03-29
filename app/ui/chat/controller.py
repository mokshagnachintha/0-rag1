"""
Chat controller: isolates side effects from Kivy chat view.
"""
from __future__ import annotations

from typing import Callable, Optional

from app.platform.android.service import start_foreground_service
from . import actions


class ChatController:
    def __init__(self) -> None:
        self._service_started = False

    def register_bootstrap_callbacks(
        self,
        on_progress: Optional[Callable[[float, str], None]],
        on_done: Optional[Callable[[bool, str], None]],
    ) -> None:
        actions.register_bootstrap_callbacks(on_progress=on_progress, on_done=on_done)

    def get_bootstrap_state(self):
        return actions.get_bootstrap_state()

    def ingest_document(
        self,
        file_path: str,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        actions.ingest_document(file_path, on_done=on_done)

    def clear_documents(self) -> None:
        actions.clear_documents()

    def list_documents(self) -> list[dict]:
        return actions.list_documents()

    def delete_document(self, doc_id: int) -> None:
        actions.delete_document(doc_id)

    def ask(
        self,
        question: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        actions.ask_rag(question, stream_cb=stream_cb, on_done=on_done)

    def chat_direct(
        self,
        question: str,
        history: list | None = None,
        summary: str = "",
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        actions.ask_direct(
            question,
            history=history,
            summary=summary,
            stream_cb=stream_cb,
            on_done=on_done,
        )

    def start_service_once(self) -> bool:
        if self._service_started:
            return True
        started = start_foreground_service()
        self._service_started = started
        return started
