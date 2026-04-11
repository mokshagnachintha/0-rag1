"""High-level chat service that owns worker execution and app state."""
from __future__ import annotations

from threading import Lock
from typing import Callable, Optional

from app.platform.android.service import start_foreground_service
from app.rag import pipeline

from .state import AppState, AppStateStore
from .worker import (
    TASK_CHAT,
    TASK_INGEST,
    TASK_INIT,
    TASK_LOAD_MODEL,
    TASK_RAG,
    TaskWorker,
)


class ChatService:
    def __init__(self) -> None:
        self._state_store = AppStateStore()
        self._worker = TaskWorker(self._state_store)
        self._worker.start()

        self._init_lock = Lock()
        self._init_submitted = False

        self._service_lock = Lock()
        self._service_started = False

    def ensure_initialized(self) -> None:
        with self._init_lock:
            if self._init_submitted:
                return
            self._init_submitted = True
        self._worker.submit(TASK_INIT)

    def register_bootstrap_callbacks(
        self,
        on_progress: Optional[Callable[[float, str], None]],
        on_done: Optional[Callable[[bool, str], None]],
    ) -> None:
        self.ensure_initialized()

        def _wrapped_progress(frac: float, message: str) -> None:
            self._state_store.update(
                loading=True,
                current_task="bootstrap",
                current_task_id=None,
                model_ready=False,
                error=None,
            )
            if on_progress:
                on_progress(frac, message)

        def _wrapped_done(success: bool, message: str) -> None:
            self._state_store.update(
                loading=False,
                current_task=None,
                current_task_id=None,
                model_ready=success,
                error=None if success else message,
            )
            if on_done:
                on_done(success, message)

        pipeline.register_auto_download_callbacks(on_progress=_wrapped_progress, on_done=_wrapped_done)

    def get_bootstrap_state(self):
        return pipeline.get_bootstrap_event()

    def list_documents(self) -> list[dict]:
        return pipeline.list_documents()

    def delete_document(self, doc_id: int) -> None:
        pipeline.delete_document_by_id(doc_id)

    def clear_documents(self) -> None:
        pipeline.clear_all_documents()

    def ingest_document(
        self,
        file_path: str,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        return self._worker.submit(
            TASK_INGEST,
            data={"file_path": file_path},
            callbacks={"on_done": on_done} if on_done else None,
        )

    def load_model(
        self,
        model_path: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        callbacks = {}
        if on_progress:
            callbacks["on_progress"] = on_progress
        if on_done:
            callbacks["on_done"] = on_done
        return self._worker.submit(
            TASK_LOAD_MODEL,
            data={"model_path": model_path},
            callbacks=callbacks or None,
        )

    def send_message(
        self,
        question: str,
        mode: str,
        history: list | None = None,
        summary: str = "",
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        task_type = TASK_RAG if mode == TASK_RAG else TASK_CHAT
        return self._worker.submit(
            task_type,
            data={
                "question": question,
                "history": history,
                "summary": summary,
            },
            callbacks={
                "on_token": stream_cb,
                "on_done": on_done,
            },
        )

    def ask(
        self,
        question: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        return self.send_message(question=question, mode=TASK_RAG, stream_cb=stream_cb, on_done=on_done)

    def chat_direct(
        self,
        question: str,
        history: list | None = None,
        summary: str = "",
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> str:
        return self.send_message(
            question=question,
            mode=TASK_CHAT,
            history=history,
            summary=summary,
            stream_cb=stream_cb,
            on_done=on_done,
        )

    def cancel_task(self, task_id: Optional[str] = None) -> bool:
        if task_id:
            return self._worker.cancel_task(task_id)
        return self._worker.cancel_current_task()

    def get_status(self, task_id: Optional[str] = None) -> dict:
        state = self._state_store.snapshot()
        lookup_id = task_id or state.current_task_id
        task_status = self._worker.get_status(lookup_id) if lookup_id else None
        return {
            "model_ready": state.model_ready,
            "loading": state.loading,
            "current_task": state.current_task,
            "current_task_id": state.current_task_id,
            "error": state.error,
            "task": task_status,
        }

    def app_state(self) -> AppState:
        return self._state_store.snapshot()

    def start_service_once(self) -> bool:
        with self._service_lock:
            if self._service_started:
                return True
            started = start_foreground_service()
            self._service_started = started
            return started


_chat_service_singleton: Optional[ChatService] = None
_chat_service_lock = Lock()


def get_chat_service() -> ChatService:
    global _chat_service_singleton
    with _chat_service_lock:
        if _chat_service_singleton is None:
            _chat_service_singleton = ChatService()
        return _chat_service_singleton
