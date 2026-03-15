"""
Simple in-process event bus used by the UI controller/screens.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Callable


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event: str, callback: Callable) -> None:
        with self._lock:
            self._subs[event].append(callback)

    def emit(self, event: str, *args, **kwargs) -> None:
        with self._lock:
            callbacks = list(self._subs.get(event, []))
        for cb in callbacks:
            try:
                cb(*args, **kwargs)
            except Exception as exc:
                print(f"[event_bus] callback error for '{event}': {exc}")
