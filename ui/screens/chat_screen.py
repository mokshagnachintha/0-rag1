from __future__ import annotations

from kivy.clock import Clock, mainthread
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from ui.controller import AppController


def _paint(widget, color, radius: float = 0):
    with widget.canvas.before:
        Color(*color)
        rect = RoundedRectangle(radius=[dp(radius)])
    widget.bind(
        pos=lambda w, _: setattr(rect, "pos", w.pos),
        size=lambda w, _: setattr(rect, "size", w.size),
    )


class _MessageRow(BoxLayout):
    def __init__(self, role: str, text: str, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            spacing=dp(8),
            padding=[dp(12), dp(6)],
            **kwargs,
        )
        self.role = role
        is_user = role == "user"

        self._label = Label(
            text=text,
            markup=True,
            size_hint=(None, None),
            text_size=(dp(260), None),
            halign="left",
            valign="top",
            color=(1, 1, 1, 1),
            font_size=sp(14),
        )
        self._label.bind(texture_size=self._sync_size)

        bubble = BoxLayout(
            size_hint=(None, None),
            padding=[dp(12), dp(10)],
        )
        _paint(bubble, (0.16, 0.54, 0.38, 1) if is_user else (0.20, 0.20, 0.22, 1), 12)
        bubble.add_widget(self._label)
        self._bubble = bubble

        if is_user:
            self.add_widget(Widget(size_hint_x=1))
            self.add_widget(bubble)
        else:
            self.add_widget(bubble)
            self.add_widget(Widget(size_hint_x=1))

        self.bind(width=self._on_width)
        self._sync_size(self._label, self._label.texture_size)

    def _on_width(self, *_):
        max_w = max(dp(160), self.width * 0.72)
        self._label.text_size = (max_w, None)

    def _sync_size(self, _label, tex):
        self._label.size = (tex[0], tex[1])
        self._bubble.size = (tex[0] + dp(24), tex[1] + dp(18))
        self.height = self._bubble.height + dp(6)

    def append(self, token: str):
        self._label.text += token

    @property
    def text(self) -> str:
        return self._label.text

    @text.setter
    def text(self, value: str):
        self._label.text = value


class ChatScreen(Screen):
    def __init__(self, controller: AppController, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller
        self._assistant_row: _MessageRow | None = None
        self._token_buf: list[str] = []
        self._token_flush_ev = None
        self._build_ui()

        self.controller.events.subscribe("model_ready", self._on_model_ready_event)
        self.controller.events.subscribe("docs_changed", self._on_docs_changed_event)

    def _build_ui(self):
        root = BoxLayout(orientation="vertical")
        _paint(root, (0.09, 0.09, 0.10, 1), 0)

        header = BoxLayout(
            size_hint=(1, None),
            height=dp(58),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            spacing=dp(10),
        )
        _paint(header, (0.12, 0.12, 0.13, 1), 0)

        title = Label(
            text="[b]Chat[/b]",
            markup=True,
            font_size=sp(17),
            halign="left",
            valign="middle",
            size_hint=(1, 1),
        )
        self._mode = Label(
            text="[CHAT MODE]",
            markup=True,
            font_size=sp(11),
            size_hint=(None, 1),
            width=dp(130),
            color=(0.6, 0.9, 0.7, 1),
        )
        docs_btn = Button(
            text="Docs",
            size_hint=(None, 1),
            width=dp(72),
            background_normal="",
            background_color=(0.19, 0.42, 0.70, 1),
        )
        docs_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "docs"))

        header.add_widget(title)
        header.add_widget(self._mode)
        header.add_widget(docs_btn)
        root.add_widget(header)

        self._scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._messages = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            spacing=dp(4),
            padding=[0, dp(8), 0, dp(16)],
        )
        self._messages.bind(minimum_height=self._messages.setter("height"))
        self._scroll.add_widget(self._messages)
        root.add_widget(self._scroll)

        self._welcome = self._add_message(
            "assistant",
            "[b]New architecture loaded.[/b]\nAsk anything, or upload a document in Docs.",
        )

        composer = BoxLayout(
            size_hint=(1, None),
            height=dp(72),
            spacing=dp(10),
            padding=[dp(12), dp(12)],
        )
        _paint(composer, (0.12, 0.12, 0.13, 1), 0)

        self._input = TextInput(
            multiline=False,
            hint_text="Type your message...",
            size_hint=(1, 1),
            font_size=sp(14),
            foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.6, 0.6, 0.62, 1),
            background_color=(0.18, 0.18, 0.20, 1),
            cursor_color=(1, 1, 1, 1),
        )
        self._input.bind(on_text_validate=self._on_send)

        self._send = Button(
            text="Send",
            size_hint=(None, 1),
            width=dp(90),
            background_normal="",
            background_color=(0.14, 0.62, 0.44, 1),
            disabled=True,
        )
        self._send.bind(on_release=self._on_send)

        composer.add_widget(self._input)
        composer.add_widget(self._send)
        root.add_widget(composer)

        self.add_widget(root)
        self._refresh_mode_chip()

    def on_pre_enter(self, *_):
        self._refresh_mode_chip()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_model_ready_event(self, success: bool, _message: str):
        self._apply_model_ready(success)

    def _on_docs_changed_event(self):
        self._apply_docs_changed()

    @mainthread
    def _apply_model_ready(self, success: bool):
        self._send.disabled = not success
        if success:
            self._welcome.text = (
                "[b]Ready.[/b]\n"
                "Chat directly, or upload docs and switch to RAG mode automatically."
            )
        else:
            self._welcome.text = "[color=ff5555]Model startup failed.[/color]"

    @mainthread
    def _apply_docs_changed(self):
        self._refresh_mode_chip()

    # ------------------------------------------------------------------
    # Chat actions
    # ------------------------------------------------------------------

    def _on_send(self, *_):
        text = self._input.text.strip()
        if not text:
            return
        self._input.text = ""
        self._add_message("user", text)
        self._assistant_row = self._add_message("assistant", "")

        self._token_buf.clear()
        if self._token_flush_ev is not None:
            Clock.unschedule(self._token_flush_ev)
            self._token_flush_ev = None

        self.controller.send_message(
            text=text,
            stream_cb=self._on_token,
            on_done=self._on_done,
        )

    def _on_token(self, token: str):
        self._token_buf.append(token)
        if self._token_flush_ev is None:
            self._token_flush_ev = Clock.schedule_once(self._flush_tokens, 0.08)

    @mainthread
    def _flush_tokens(self, *_):
        self._token_flush_ev = None
        if not self._assistant_row or not self._token_buf:
            return
        chunk = "".join(self._token_buf)
        self._token_buf.clear()
        self._assistant_row.append(chunk)
        self._scroll_bottom()

    @mainthread
    def _on_done(self, success: bool, message: str):
        if self._token_buf:
            self._flush_tokens()
        if not success and self._assistant_row:
            self._assistant_row.text = f"[color=ff6666]{message}[/color]"
        self._assistant_row = None
        self._scroll_bottom()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _add_message(self, role: str, text: str) -> _MessageRow:
        row = _MessageRow(role=role, text=text)
        self._messages.add_widget(row)
        self._scroll_bottom()
        return row

    def _refresh_mode_chip(self):
        if self.controller.has_docs:
            label = self.controller.active_doc or "RAG mode"
            self._mode.text = f"[RAG: {label[:14]}]"
            self._mode.color = (0.55, 0.87, 1, 1)
        else:
            self._mode.text = "[CHAT MODE]"
            self._mode.color = (0.6, 0.9, 0.7, 1)

    def _scroll_bottom(self):
        Clock.schedule_once(lambda *_: setattr(self._scroll, "scroll_y", 0), 0.01)
