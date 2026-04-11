"""Single-thread task worker for chat, RAG, ingest and model operations."""
from __future__ import annotations

import queue
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.rag import pipeline

from .state import AppStateStore

TASK_CHAT = "chat"
TASK_RAG = "rag"
TASK_INGEST = "ingest"
TASK_LOAD_MODEL = "load_model"
TASK_INIT = "init"

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_DONE = "done"
TASK_STATUS_ERROR = "error"
TASK_STATUS_CANCELLED = "cancelled"


class _TaskCancelled(Exception):
    pass


@dataclass
class Task:
    type: str
    data: dict[str, Any]
    on_done: Optional[Callable[[bool, str], None]] = None
    on_token: Optional[Callable[[str], None]] = None
    on_progress: Optional[Callable[[float, str], None]] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = TASK_STATUS_QUEUED
    cancel_flag: bool = False


class TaskWorker:
    def __init__(self, state_store: AppStateStore) -> None:
        self._state_store = state_store
        self._queue: queue.Queue[Task] = queue.Queue()
        self._tasks: dict[str, Task] = {}
        self._tasks_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True, name="chat-task-worker")
        self._start_lock = threading.Lock()
        self._started = False
        self._llm_lock = threading.Lock()
        self._current_task_id: Optional[str] = None

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._thread.start()
            self._started = True

    def submit(
        self,
        task_type: str,
        data: Optional[dict[str, Any]] = None,
        callbacks: Optional[dict[str, Callable[..., Any]]] = None,
    ) -> str:
        callbacks = callbacks or {}
        task = Task(
            type=task_type,
            data=data or {},
            on_done=callbacks.get("on_done"),
            on_token=callbacks.get("on_token"),
            on_progress=callbacks.get("on_progress"),
        )
        with self._tasks_lock:
            self._tasks[task.id] = task
        self._queue.put(task)
        return task.id

    def cancel_task(self, task_id: str) -> bool:
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task.cancel_flag = True
            if task.status == TASK_STATUS_QUEUED:
                task.status = TASK_STATUS_CANCELLED
        return True

    def cancel_current_task(self) -> bool:
        task_id = self.current_task_id()
        if not task_id:
            return False
        return self.cancel_task(task_id)

    def current_task_id(self) -> Optional[str]:
        with self._tasks_lock:
            return self._current_task_id

    def get_status(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return {
                "id": task.id,
                "type": task.type,
                "status": task.status,
                "cancel_flag": task.cancel_flag,
            }

    def _set_status(self, task: Task, status: str) -> None:
        with self._tasks_lock:
            task.status = status

    def _set_current_task(self, task: Optional[Task]) -> None:
        with self._tasks_lock:
            self._current_task_id = task.id if task else None

    def _emit_done(self, task: Task, ok: bool, message: str) -> None:
        if task.on_done:
            task.on_done(ok, message)

    def _stream_cb(self, task: Task) -> Callable[[str], None]:
        def _cb(token: str) -> None:
            if task.cancel_flag:
                raise _TaskCancelled("Task cancelled")
            if task.on_token:
                task.on_token(token)

        return _cb

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            try:
                if task.cancel_flag:
                    self._set_status(task, TASK_STATUS_CANCELLED)
                    self._emit_done(task, False, "Task cancelled")
                    continue

                self._set_status(task, TASK_STATUS_RUNNING)
                self._set_current_task(task)
                self._state_store.update(
                    loading=True,
                    current_task=task.type,
                    current_task_id=task.id,
                    error=None,
                )

                ok, message = self._execute_task(task)
                if task.cancel_flag:
                    raise _TaskCancelled("Task cancelled")

                if ok:
                    self._set_status(task, TASK_STATUS_DONE)
                    if task.type == TASK_LOAD_MODEL:
                        self._state_store.update(model_ready=True)
                    self._state_store.update(
                        loading=False,
                        current_task=None,
                        current_task_id=None,
                        error=None,
                    )
                else:
                    self._set_status(task, TASK_STATUS_ERROR)
                    if task.type == TASK_LOAD_MODEL:
                        self._state_store.update(model_ready=False)
                    self._state_store.update(
                        loading=False,
                        current_task=None,
                        current_task_id=None,
                        error=message,
                    )

                self._emit_done(task, ok, message)

            except _TaskCancelled as exc:
                self._set_status(task, TASK_STATUS_CANCELLED)
                self._state_store.update(
                    loading=False,
                    current_task=None,
                    current_task_id=None,
                    error=None,
                )
                self._emit_done(task, False, str(exc))

            except Exception as exc:
                traceback.print_exc()
                self._set_status(task, TASK_STATUS_ERROR)
                self._state_store.update(
                    loading=False,
                    current_task=None,
                    current_task_id=None,
                    error=str(exc),
                )
                self._emit_done(task, False, f"Task failed: {exc}")

            finally:
                self._set_current_task(None)
                self._queue.task_done()

    def _execute_task(self, task: Task) -> tuple[bool, str]:
        if task.type == TASK_INIT:
            pipeline.init()
            return True, "Pipeline initialized"

        if task.type == TASK_INGEST:
            return pipeline.ingest_document(task.data["file_path"])

        if task.type == TASK_LOAD_MODEL:
            return pipeline.load_model(
                task.data["model_path"],
                on_progress=task.on_progress,
            )

        if task.type == TASK_CHAT:
            with self._llm_lock:
                return pipeline.chat_direct(
                    task.data["question"],
                    history=task.data.get("history"),
                    summary=task.data.get("summary", ""),
                    stream_cb=self._stream_cb(task),
                )

        if task.type == TASK_RAG:
            with self._llm_lock:
                return pipeline.ask(
                    task.data["question"],
                    stream_cb=self._stream_cb(task),
                )

        raise ValueError(f"Unknown task type: {task.type}")
