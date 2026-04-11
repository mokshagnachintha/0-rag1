"""Chat controller that owns execution via shared chat service."""
from __future__ import annotations

from typing import Callable, Optional

from .services.chat_service import get_chat_service
from .services.worker import TASK_CHAT, TASK_RAG


class ChatController:
    def __init__(self) -> None:
        self._service = get_chat_service()

    def ensure_initialized(self) -> None:
        self._service.ensure_initialized()

    def register_bootstrap_callbacks(
        self,
        on_progress: Optional[Callable[[float, str], None]],
        on_done: Optional[Callable[[bool, str], None]],
    ) -> None:
        self._service.register_bootstrap_callbacks(on_progress=on_progress, on_done=on_done)

    def get_bootstrap_state(self):
        return self._service.get_bootstrap_state()

    def ingest_document(
        self,
        file_path: str,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        return self._service.ingest_document(file_path, on_done=on_done)

    def clear_documents(self) -> None:
        self._service.clear_documents()

    def list_documents(self) -> list[dict]:
        return self._service.list_documents()

    def delete_document(self, doc_id: int) -> None:
        self._service.delete_document(doc_id)

    def send_message(
        self,
        question: str,
        mode: str,
        history: list | None = None,
        summary: str = "",
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        task_mode = TASK_RAG if mode == TASK_RAG else TASK_CHAT
        return self._service.send_message(
            question=question,
            mode=task_mode,
            history=history,
            summary=summary,
            stream_cb=stream_cb,
            on_done=on_done,
        )

    def ask(
        self,
        question: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        return self._service.ask(question, stream_cb=stream_cb, on_done=on_done)

    def chat_direct(
        self,
        question: str,
        history: list | None = None,
        summary: str = "",
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        return self._service.chat_direct(
            question,
            history=history,
            summary=summary,
            stream_cb=stream_cb,
            on_done=on_done,
        )

    def load_model(
        self,
        model_path: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        return self._service.load_model(model_path, on_progress=on_progress, on_done=on_done)

    def cancel_task(self, task_id: Optional[str] = None) -> bool:
        return self._service.cancel_task(task_id)

    def cancel_current_task(self) -> bool:
        return self._service.cancel_task(None)

    def get_status(self, task_id: Optional[str] = None) -> dict:
        return self._service.get_status(task_id)

    def start_service_once(self) -> bool:
        return self._service.start_service_once()
