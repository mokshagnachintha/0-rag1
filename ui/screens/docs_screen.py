from __future__ import annotations

import os
from pathlib import Path

from kivy.clock import mainthread
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from ui.controller import AppController


def _paint(widget, color, radius: float = 0):
    with widget.canvas.before:
        Color(*color)
        rect = RoundedRectangle(radius=[dp(radius)])
    widget.bind(
        pos=lambda w, _: setattr(rect, "pos", w.pos),
        size=lambda w, _: setattr(rect, "size", w.size),
    )


class _DocCard(BoxLayout):
    def __init__(self, name: str, chunks: int, added_at: str, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(1, None),
            padding=[dp(12), dp(10)],
            spacing=dp(4),
            **kwargs,
        )
        _paint(self, (0.17, 0.17, 0.20, 1), 10)

        self.add_widget(Label(
            text=f"[b]{name}[/b]",
            markup=True,
            size_hint=(1, None),
            height=dp(20),
            halign="left",
            valign="middle",
            font_size=sp(13),
        ))
        self.add_widget(Label(
            text=f"{chunks} chunks • {added_at[:16]}",
            size_hint=(1, None),
            height=dp(18),
            color=(0.72, 0.72, 0.75, 1),
            halign="left",
            valign="middle",
            font_size=sp(11),
        ))
        self.height = dp(68)


class DocsScreen(Screen):
    def __init__(self, controller: AppController, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller
        self._build_ui()
        self.controller.events.subscribe("docs_changed", self._on_docs_changed_event)

    def on_pre_enter(self, *_):
        self._refresh_docs()

    def _build_ui(self):
        root = BoxLayout(orientation="vertical")
        _paint(root, (0.09, 0.09, 0.10, 1), 0)

        header = BoxLayout(
            size_hint=(1, None),
            height=dp(58),
            padding=[dp(14), dp(10)],
            spacing=dp(8),
        )
        _paint(header, (0.12, 0.12, 0.13, 1), 0)
        header.add_widget(Label(
            text="[b]Documents[/b]",
            markup=True,
            font_size=sp(17),
            halign="left",
            valign="middle",
            size_hint=(1, 1),
        ))
        chat_btn = Button(
            text="Chat",
            size_hint=(None, 1),
            width=dp(78),
            background_normal="",
            background_color=(0.14, 0.62, 0.44, 1),
        )
        chat_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "chat"))
        header.add_widget(chat_btn)
        root.add_widget(header)

        action = BoxLayout(
            size_hint=(1, None),
            height=dp(56),
            spacing=dp(8),
            padding=[dp(12), dp(8)],
        )
        _paint(action, (0.11, 0.11, 0.12, 1), 0)

        pick_btn = Button(
            text="+ Add PDF/TXT",
            background_normal="",
            background_color=(0.19, 0.42, 0.70, 1),
        )
        pick_btn.bind(on_release=self._on_pick)

        clear_btn = Button(
            text="Clear All",
            size_hint=(None, 1),
            width=dp(92),
            background_normal="",
            background_color=(0.62, 0.18, 0.22, 1),
        )
        clear_btn.bind(on_release=self._on_clear_all)

        action.add_widget(pick_btn)
        action.add_widget(clear_btn)
        root.add_widget(action)

        path_row = BoxLayout(
            size_hint=(1, None),
            height=dp(60),
            spacing=dp(8),
            padding=[dp(12), dp(10)],
        )
        _paint(path_row, (0.11, 0.11, 0.12, 1), 0)

        self._path_input = TextInput(
            multiline=False,
            hint_text="Or paste full document path...",
            size_hint=(1, 1),
            font_size=sp(13),
            foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.6, 0.6, 0.62, 1),
            background_color=(0.18, 0.18, 0.20, 1),
            cursor_color=(1, 1, 1, 1),
        )
        add_path_btn = Button(
            text="Ingest",
            size_hint=(None, 1),
            width=dp(86),
            background_normal="",
            background_color=(0.14, 0.62, 0.44, 1),
        )
        add_path_btn.bind(on_release=self._on_ingest_manual)

        path_row.add_widget(self._path_input)
        path_row.add_widget(add_path_btn)
        root.add_widget(path_row)

        self._scroll = ScrollView(size_hint=(1, 1))
        self._list = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            spacing=dp(8),
            padding=[dp(12), dp(12)],
        )
        self._list.bind(minimum_height=self._list.setter("height"))
        self._scroll.add_widget(self._list)
        root.add_widget(self._scroll)

        self._status = Label(
            text="",
            size_hint=(1, None),
            height=dp(32),
            font_size=sp(12),
            color=(0.72, 0.92, 0.75, 1),
        )
        root.add_widget(self._status)

        self.add_widget(root)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_pick(self, *_):
        try:
            from plyer import filechooser

            filechooser.open_file(
                on_selection=self._on_file_selected,
                filters=[["Documents", "*.pdf", "*.txt", "*.PDF", "*.TXT"]],
                title="Pick document",
                multiple=False,
            )
        except Exception as exc:
            self._set_status(f"Picker unavailable: {exc}", ok=False)

    @mainthread
    def _on_file_selected(self, selection):
        if not selection:
            return
        from rag.chunker import resolve_uri
        try:
            path = resolve_uri(selection[0])
            self._ingest(path)
        except Exception as exc:
            self._set_status(f"Could not open selected file: {exc}", ok=False)

    def _on_ingest_manual(self, *_):
        path = self._path_input.text.strip()
        if not path:
            return
        self._path_input.text = ""
        self._ingest(path)

    def _ingest(self, path: str):
        if not os.path.isfile(path):
            self._set_status("File not found.", ok=False)
            return
        self._set_status(f"Ingesting {Path(path).name} ...", ok=True)
        self.controller.ingest_document(path, on_done=self._on_ingest_done)

    @mainthread
    def _on_ingest_done(self, success: bool, message: str):
        self._set_status(message, ok=success)
        if success:
            self._refresh_docs()

    def _on_clear_all(self, *_):
        ok, msg = self.controller.clear_documents()
        self._set_status(msg, ok=ok)
        self._refresh_docs()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _on_docs_changed_event(self):
        self._refresh_docs_mainthread()

    @mainthread
    def _refresh_docs_mainthread(self):
        self._refresh_docs()

    def _refresh_docs(self):
        self._list.clear_widgets()
        docs = self.controller.get_documents()
        if not docs:
            self._list.add_widget(Label(
                text="No documents yet.\nAdd one to activate RAG mode.",
                size_hint=(1, None),
                height=dp(90),
                halign="center",
                valign="middle",
                font_size=sp(13),
                color=(0.65, 0.65, 0.68, 1),
            ))
            return

        for doc in docs:
            self._list.add_widget(_DocCard(
                name=doc["name"],
                chunks=doc["num_chunks"],
                added_at=doc["added_at"],
            ))

    def _set_status(self, text: str, ok: bool):
        self._status.text = text
        self._status.color = (0.72, 0.92, 0.75, 1) if ok else (0.95, 0.55, 0.55, 1)
