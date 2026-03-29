"""
Typed bootstrap coordinator for model download/load lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Callable, Optional


class BootstrapState(str, Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class BootstrapEvent:
    state: BootstrapState
    progress: float
    message: str


class BootstrapCoordinator:
    def __init__(self) -> None:
        self._lock = Lock()
        self._event = BootstrapEvent(BootstrapState.IDLE, 0.0, "")
        self._listeners: list[
            tuple[
                Optional[Callable[[float, str], None]],
                Optional[Callable[[bool, str], None]],
            ]
        ] = []

    def register_callbacks(
        self,
        on_progress: Optional[Callable[[float, str], None]],
        on_done: Optional[Callable[[bool, str], None]],
    ) -> None:
        with self._lock:
            self._listeners.append((on_progress, on_done))
            event = self._event

        self._notify_single(on_progress, on_done, event)

    def event(self) -> BootstrapEvent:
        with self._lock:
            return self._event

    def emit_downloading(self, progress: float, message: str) -> None:
        self._emit(BootstrapEvent(BootstrapState.DOWNLOADING, max(0.0, min(1.0, progress)), message))

    def emit_ready(self, message: str) -> None:
        self._emit(BootstrapEvent(BootstrapState.READY, 1.0, message))

    def emit_error(self, message: str) -> None:
        self._emit(BootstrapEvent(BootstrapState.ERROR, 1.0, message))

    def _emit(self, event: BootstrapEvent) -> None:
        with self._lock:
            self._event = event
            listeners = list(self._listeners)

        for on_progress, on_done in listeners:
            self._notify_single(on_progress, on_done, event)

    @staticmethod
    def _notify_single(
        on_progress: Optional[Callable[[float, str], None]],
        on_done: Optional[Callable[[bool, str], None]],
        event: BootstrapEvent,
    ) -> None:
        if event.state == BootstrapState.DOWNLOADING and on_progress:
            on_progress(event.progress, event.message)
            return
        if event.state == BootstrapState.READY and on_done:
            on_done(True, event.message)
            return
        if event.state == BootstrapState.ERROR and on_done:
            on_done(False, event.message)
