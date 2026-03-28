from __future__ import annotations
import time
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.resources import resource_find
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton
from rag.debug_logger import debug_log, list_log_sources, tail_logs

def _paint(widget, color):
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle()
    widget.bind(pos=lambda w, _: setattr(rect, "pos", w.pos))
    widget.bind(size=lambda w, _: setattr(rect, "size", w.size))

class DebugLoggerOverlay(ModalView):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.size_hint = (1, 1)
        self.auto_dismiss = False
        self.background = ""
        self.background_color = (0, 0, 0, 0)
        self._source_key = "all"
        self._paused = False
        self._poll_event = None
        self._last_refresh_ts = 0.0

        root = BoxLayout(orientation="vertical", padding=[dp(12), dp(12), dp(12), dp(12)], spacing=dp(8))
        _paint(root, (0.06, 0.06, 0.07, 0.98))

        title_row = BoxLayout(size_hint=(1, None), height=dp(34), spacing=dp(8))
        title = Label(
            text="[b]Debug Logger[/b]",
            markup=True,
            color=(1, 1, 1, 1),
            font_size=sp(15),
            halign="left",
            valign="middle",
        )
        title.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        title_row.add_widget(title)

        self._status = Label(
            text="Live",
            size_hint=(None, 1),
            width=dp(160),
            color=(0.72, 0.74, 0.78, 1),
            font_size=sp(11),
            halign="right",
            valign="middle",
        )
        self._status.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        title_row.add_widget(self._status)
        root.add_widget(title_row)

        tab_row = BoxLayout(size_hint=(1, None), height=dp(34), spacing=dp(6))
        tabs = [
            ("all", "All"),
            ("app_events", "App Events"),
            ("service_runtime", "Service Runtime"),
            ("llama_server", "Llama Server"),
            ("crash", "Crash"),
            ("debug_notes", "Debug Notes"),
        ]
        self._tab_buttons = {}
        for key, label in tabs:
            tb = ToggleButton(
                text=label,
                group="log_source",
                state="down" if key == "all" else "normal",
                size_hint=(None, 1),
                width=dp(122) if key != "all" else dp(74),
                background_normal="",
                background_down="",
                background_color=(0.18, 0.22, 0.30, 1) if key == "all" else (0.17, 0.17, 0.19, 1),
                color=(1, 1, 1, 1),
                font_size=sp(10.5),
            )
            tb.bind(on_release=lambda btn, sk=key: self._on_source_change(sk))
            self._tab_buttons[key] = tb
            tab_row.add_widget(tb)
        root.add_widget(tab_row)

        controls = BoxLayout(size_hint=(1, None), height=dp(36), spacing=dp(6))
        self._btn_refresh = Button(
            text="Refresh",
            background_normal="",
            background_color=(0.25, 0.45, 0.66, 1),
            color=(1, 1, 1, 1),
            font_size=sp(11),
        )
        self._btn_refresh.bind(on_release=lambda *_: self.refresh_now())
        controls.add_widget(self._btn_refresh)

        self._btn_pause = Button(
            text="Pause",
            background_normal="",
            background_color=(0.36, 0.33, 0.20, 1),
            color=(1, 1, 1, 1),
            font_size=sp(11),
        )
        self._btn_pause.bind(on_release=self._toggle_pause)
        controls.add_widget(self._btn_pause)

        self._btn_copy = Button(
            text="Copy Logs",
            background_normal="",
            background_color=(0.27, 0.27, 0.27, 1),
            color=(1, 1, 1, 1),
            font_size=sp(11),
        )
        self._btn_copy.bind(on_release=self._copy_logs)
        controls.add_widget(self._btn_copy)

        self._btn_clear = Button(
            text="Clear View",
            background_normal="",
            background_color=(0.27, 0.27, 0.27, 1),
            color=(1, 1, 1, 1),
            font_size=sp(11),
        )
        self._btn_clear.bind(on_release=self._clear_view)
        controls.add_widget(self._btn_clear)

        self._btn_close = Button(
            text="Close",
            background_normal="",
            background_color=(0.50, 0.20, 0.20, 1),
            color=(1, 1, 1, 1),
            font_size=sp(11),
        )
        self._btn_close.bind(on_release=lambda *_: self.dismiss())
        controls.add_widget(self._btn_close)
        root.add_widget(controls)

        mono = resource_find("data/fonts/RobotoMono-Regular.ttf")
        kwargs = {}
        if mono:
            kwargs["font_name"] = mono

        self._scroll_view = ScrollView(size_hint=(1, 1))
        _paint(self._scroll_view, (0.10, 0.10, 0.12, 1))

        self._text_label = Label(
            text="Preparing log view...",
            size_hint_y=None,
            font_size=sp(11),
            color=(0.87, 0.89, 0.92, 1),
            halign="left",
            valign="top",
            padding=(dp(4), dp(4)),
            **kwargs
        )
        self._text_label.bind(width=lambda w, _: setattr(w, "text_size", (w.width, None)))
        self._text_label.bind(texture_size=self._text_label.setter("size"))
        self._scroll_view.add_widget(self._text_label)
        root.add_widget(self._scroll_view)

        foot = BoxLayout(size_hint=(1, None), height=dp(22), spacing=dp(6))
        self._source_info = Label(
            text="Sources: loading...",
            color=(0.55, 0.57, 0.62, 1),
            font_size=sp(10),
            halign="left",
            valign="middle",
        )
        self._source_info.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        foot.add_widget(self._source_info)
        root.add_widget(foot)

        self.add_widget(root)

    def on_open(self):
        debug_log("ui.logger", "Debug logger overlay opened")
        self._refresh_source_info()
        self.refresh_now()
        if self._poll_event is None:
            self._poll_event = Clock.schedule_interval(self._on_tick, 1.0)

    def on_dismiss(self):
        debug_log("ui.logger", "Debug logger overlay closed")
        if self._poll_event is not None:
            Clock.unschedule(self._poll_event)
            self._poll_event = None

    def _refresh_source_info(self):
        sources = list_log_sources()
        visible = sources.get(self._source_key, [])
        names = ", ".join(e["filename"] for e in visible) if visible else "none"
        self._source_info.text = f"Sources: {names}"

    def _on_source_change(self, source_key: str):
        self._source_key = source_key
        for key, btn in self._tab_buttons.items():
            btn.background_color = (0.18, 0.22, 0.30, 1) if key == source_key else (0.17, 0.17, 0.19, 1)
        debug_log("ui.logger", f"Switched source tab to '{source_key}'")
        self._refresh_source_info()
        self.refresh_now()

    def _on_tick(self, *_):
        if self._paused:
            return
        self.refresh_now()

    def _update_scroll_to_bottom(self, *_):
        self._scroll_view.scroll_y = 0

    def refresh_now(self):
        self._last_refresh_ts = time.time()
        
        auto_scroll = self._scroll_view.scroll_y <= 0.05

        text = tail_logs(source_key=self._source_key, max_bytes_per_file=48 * 1024, max_lines=900)
        self._text_label.text = text if text else "No logs yet."
        self._status.text = f"Live | {time.strftime('%H:%M:%S')}"

        if auto_scroll:
            Clock.schedule_once(self._update_scroll_to_bottom, 0)

    def _toggle_pause(self, *_):
        self._paused = not self._paused
        self._btn_pause.text = "Resume" if self._paused else "Pause"
        self._btn_pause.background_color = (0.19, 0.39, 0.24, 1) if self._paused else (0.36, 0.33, 0.20, 1)
        self._status.text = "Paused" if self._paused else "Live"
        debug_log("ui.logger", f"Pause toggled -> {self._paused}")
        if not self._paused:
            self.refresh_now()

    def _copy_logs(self, *_):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(self._text_label.text or "")
            self._status.text = "Copied logs to clipboard"
            debug_log("ui.logger", "Copied logs to clipboard")
        except Exception as exc:
            self._status.text = f"Copy failed: {exc}"
            debug_log("ui.logger", f"Copy logs failed: {exc}", level="ERROR")

    def _clear_view(self, *_):
        self._paused = True
        self._btn_pause.text = "Resume"
        self._btn_pause.background_color = (0.19, 0.39, 0.24, 1)
        self._text_label.text = ""
        self._status.text = "View cleared (files unchanged)"
        debug_log("ui.logger", "Cleared viewer text (non-destructive)")