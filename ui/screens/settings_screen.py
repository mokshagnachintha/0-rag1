from __future__ import annotations

from kivy.clock import mainthread
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from ui.controller import AppController


def _paint(widget, color, radius: float = 0):
    with widget.canvas.before:
        Color(*color)
        rect = RoundedRectangle(radius=[dp(radius)])
    widget.bind(
        pos=lambda w, _: setattr(rect, "pos", w.pos),
        size=lambda w, _: setattr(rect, "size", w.size),
    )


class SettingsScreen(Screen):
    def __init__(self, controller: AppController, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller
        self._build_ui()

        self.controller.events.subscribe("model_progress", self._on_model_progress_event)
        self.controller.events.subscribe("model_ready", self._on_model_ready_event)
        self.controller.events.subscribe("docs_changed", self._on_docs_changed_event)

    def on_pre_enter(self, *_):
        self._refresh_all()

    def _build_ui(self):
        root = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=[dp(14), dp(14), dp(14), dp(14)],
        )
        _paint(root, (0.09, 0.09, 0.10, 1), 0)

        root.add_widget(Label(
            text="[b]Settings[/b]",
            markup=True,
            size_hint=(1, None),
            height=dp(44),
            font_size=sp(20),
            halign="left",
            valign="middle",
        ))

        self._model_card = self._make_card("Model Status", "Preparing...")
        self._mode_card = self._make_card("Current Mode", "Chat mode")
        self._docs_card = self._make_card("Indexed Documents", "0")
        self._path_card = self._make_card("Models Path", "")

        root.add_widget(self._model_card[0])
        root.add_widget(self._mode_card[0])
        root.add_widget(self._docs_card[0])
        root.add_widget(self._path_card[0])

        actions = BoxLayout(
            size_hint=(1, None),
            height=dp(46),
            spacing=dp(8),
        )

        chat_btn = Button(
            text="Open Chat",
            background_normal="",
            background_color=(0.14, 0.62, 0.44, 1),
        )
        chat_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "chat"))

        docs_btn = Button(
            text="Open Docs",
            background_normal="",
            background_color=(0.19, 0.42, 0.70, 1),
        )
        docs_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "docs"))

        clear_btn = Button(
            text="Clear Docs",
            background_normal="",
            background_color=(0.62, 0.18, 0.22, 1),
        )
        clear_btn.bind(on_release=self._on_clear_docs)

        actions.add_widget(chat_btn)
        actions.add_widget(docs_btn)
        actions.add_widget(clear_btn)
        root.add_widget(actions)

        self._status = Label(
            text="",
            size_hint=(1, None),
            height=dp(30),
            font_size=sp(12),
            color=(0.72, 0.92, 0.75, 1),
        )
        root.add_widget(self._status)
        root.add_widget(Label(size_hint=(1, 1)))

        self.add_widget(root)

    def _make_card(self, title: str, value: str):
        card = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(72),
            padding=[dp(12), dp(10)],
            spacing=dp(4),
        )
        _paint(card, (0.16, 0.16, 0.19, 1), 10)
        card.add_widget(Label(
            text=title,
            size_hint=(1, None),
            height=dp(18),
            color=(0.74, 0.74, 0.78, 1),
            font_size=sp(11),
            halign="left",
            valign="middle",
        ))
        value_lbl = Label(
            text=value,
            size_hint=(1, None),
            height=dp(22),
            font_size=sp(14),
            halign="left",
            valign="middle",
        )
        card.add_widget(value_lbl)
        return card, value_lbl

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _on_model_progress_event(self, _frac: float, text: str):
        self._set_model_text(text)

    def _on_model_ready_event(self, success: bool, message: str):
        if success:
            self._set_model_text("Ready")
            self._set_status(message, ok=True)
        else:
            self._set_model_text("Startup failed")
            self._set_status(message, ok=False)

    def _on_docs_changed_event(self):
        self._refresh_docs()

    @mainthread
    def _set_model_text(self, text: str):
        self._model_card[1].text = text

    @mainthread
    def _set_status(self, text: str, ok: bool):
        self._status.text = text
        self._status.color = (0.72, 0.92, 0.75, 1) if ok else (0.95, 0.55, 0.55, 1)

    def _refresh_all(self):
        self._refresh_docs()
        self._refresh_mode()
        self._path_card[1].text = self.controller.storage_models_path()
        self._model_card[1].text = "Ready" if self.controller.model_ready else self.controller.model_status

    @mainthread
    def _refresh_docs(self):
        docs = self.controller.get_documents()
        self._docs_card[1].text = str(len(docs))
        self._refresh_mode()

    @mainthread
    def _refresh_mode(self):
        self._mode_card[1].text = self.controller.current_mode_label()

    def _on_clear_docs(self, *_):
        ok, msg = self.controller.clear_documents()
        self._set_status(msg, ok=ok)
        self._refresh_docs()
