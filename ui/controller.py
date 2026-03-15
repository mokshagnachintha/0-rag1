"""
Centralized app controller:
- model bootstrap callbacks
- chat orchestration
- document ingest/clear
- shared app state exposed via EventBus events
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Callable, Optional

from rag import pipeline as rag_pipeline
from rag.db import list_documents

from .event_bus import EventBus


class AppController:
    def __init__(self) -> None:
        self.events = EventBus()
        self.model_ready = False
        self.model_error = ""
        self.model_status = "Preparing AI models..."
        self.has_docs = False
        self.active_doc = ""
        self._history: list[tuple[str, str]] = []
        self._history_summary = ""
        self._lock = threading.RLock()
        self._init_lock = threading.Lock()
        self._init_started = False
        self._sync_docs_state()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        with self._init_lock:
            if self._init_started:
                return
            self._init_started = True

        rag_pipeline.register_auto_download_callbacks(
            on_progress=self._on_model_progress,
            on_done=self._on_model_ready,
        )
        rag_pipeline.init()

    def _on_model_progress(self, frac: float, text: str) -> None:
        with self._lock:
            self.model_status = text
        self.events.emit("model_progress", frac, text)

    def _on_model_ready(self, success: bool, message: str) -> None:
        with self._lock:
            self.model_ready = success
            self.model_error = "" if success else message
            self.model_status = message
        self.events.emit("model_ready", success, message)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def send_message(
        self,
        text: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        question = text.strip()
        if not question:
            if on_done:
                on_done(False, "Message is empty.")
            return
        if not self.model_ready:
            if on_done:
                on_done(False, "AI engine is still preparing.")
            return

        with self._lock:
            use_rag = self.has_docs
            history = list(self._history)
            summary = self._history_summary

        def _finalize(success: bool, message: str) -> None:
            if success and not use_rag:
                clean = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", message).strip()
                with self._lock:
                    self._history.append((question, clean))
                    if len(self._history) > 6:
                        old = self._history[:-3]
                        keep = self._history[-3:]
                        for q_old, a_old in old:
                            first_sentence = a_old.split(".")[0].strip()[:120]
                            if first_sentence:
                                self._history_summary += f"- {q_old}: {first_sentence}.\n"
                        self._history = keep
            if on_done:
                on_done(success, message)

        if use_rag:
            rag_pipeline.ask(question, stream_cb=stream_cb, on_done=_finalize)
        else:
            rag_pipeline.chat_direct(
                question,
                history=history,
                summary=summary,
                stream_cb=stream_cb,
                on_done=_finalize,
            )

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def ingest_document(
        self,
        path: str,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        if not path:
            if on_done:
                on_done(False, "Path is empty.")
            return

        file_name = Path(path).name

        def _done(success: bool, message: str) -> None:
            if success:
                with self._lock:
                    self.has_docs = True
                    self.active_doc = file_name
                self.events.emit("docs_changed")
            if on_done:
                on_done(success, message)

        rag_pipeline.ingest_document(path, on_done=_done)

    def clear_documents(self) -> tuple[bool, str]:
        try:
            rag_pipeline.clear_all_documents()
            with self._lock:
                self.has_docs = False
                self.active_doc = ""
            self.events.emit("docs_changed")
            return True, "All documents cleared."
        except Exception as exc:
            return False, f"Failed to clear documents: {exc}"

    def get_documents(self) -> list[dict]:
        try:
            return list_documents()
        except Exception:
            return []

    def refresh_docs_state(self) -> None:
        self._sync_docs_state()
        self.events.emit("docs_changed")

    def _sync_docs_state(self) -> None:
        try:
            docs = list_documents()
        except Exception:
            docs = []
        with self._lock:
            self.has_docs = bool(docs)
            self.active_doc = docs[0]["name"] if docs else ""

    # ------------------------------------------------------------------
    # Metadata for UI
    # ------------------------------------------------------------------

    def current_mode_label(self) -> str:
        return "RAG mode" if self.has_docs else "Chat mode"

    def storage_models_path(self) -> str:
        base = os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~"))
        return os.path.join(base, "models")
