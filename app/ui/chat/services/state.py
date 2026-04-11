"""Shared chat application state container."""
from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Lock
from typing import Optional


@dataclass(frozen=True)
class AppState:
    model_ready: bool = False
    loading: bool = False
    current_task: Optional[str] = None
    current_task_id: Optional[str] = None
    error: Optional[str] = None


class AppStateStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._state = AppState()

    def snapshot(self) -> AppState:
        with self._lock:
            return self._state

    def update(self, **changes) -> AppState:
        with self._lock:
            self._state = replace(self._state, **changes)
            return self._state
