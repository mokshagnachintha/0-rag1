"""Offline RAG app entry point with responsive segmented top navigation."""

import os
import sys
import threading
import traceback

os.environ.setdefault("KIVY_LOG_LEVEL", "warning")

from app.config import ENV_FORCE_BOOTSTRAP_DOWNLOAD

if not os.environ.get("ANDROID_PRIVATE"):
    os.environ.setdefault(ENV_FORCE_BOOTSTRAP_DOWNLOAD, "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, ScreenManager

from app.rag.pipeline import init
from app.ui.chat.chat_screen import ChatScreen
from app.ui.docs.docs_screen import DocsScreen
from app.ui.responsive import current_metrics
from app.ui.settings.settings_screen import SettingsScreen
from app.ui.theme import Theme, TypeScale
from app.ui.widgets import PillButton, SurfaceCard, bind_label_size, paint_background

Config.set("kivy", "window_icon", "assets/app_icon.png")
Window.softinput_mode = "below_target"

sys.path.insert(0, os.path.dirname(__file__))


def _global_exception_handler(exc_type, exc_value, exc_tb):
    """Log unhandled exceptions instead of silently crashing."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"[CRASH] Unhandled exception:\n{msg}")
    private_dir = os.environ.get("ANDROID_PRIVATE", "")
    if private_dir:
        try:
            with open(os.path.join(private_dir, "crash.log"), "a", encoding="utf-8") as handle:
                handle.write(msg + "\n")
        except Exception:
            pass


sys.excepthook = _global_exception_handler


class AppShell(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        paint_background(self, Theme.BG)
        self._tabs: dict[str, PillButton] = {}
        self._metrics = current_metrics()
        self._build_ui()
        Window.bind(size=self._on_window_size)

    def _build_ui(self):
        self._top = SurfaceCard(
            radius=0,
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=(1, None),
        )

        self._title = Label(
            text="[b]O-RAG[/b]",
            markup=True,
            color=Theme.TEXT,
            font_size=TypeScale.LG,
            halign="left",
            valign="middle",
            size_hint=(1, None),
        )
        bind_label_size(self._title)
        self._top.add_widget(self._title)

        self._segmented = SurfaceCard(
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(1, None),
        )

        for label, name in (("Chat", "chat"), ("Documents", "docs"), ("Settings", "settings")):
            btn = PillButton(
                text=label,
                bg_color=Theme.SURFACE_ALT,
                size_hint=(1, None),
                font_size=TypeScale.SM,
            )
            btn.bind(on_release=lambda _, target=name: self.switch_tab(target))
            self._segmented.add_widget(btn)
            self._tabs[name] = btn

        self._top.add_widget(self._segmented)
        self.add_widget(self._top)

        self._screens = ScreenManager(transition=NoTransition())
        self._screens.add_widget(ChatScreen(name="chat", open_docs_tab=lambda: self.switch_tab("docs")))
        self._screens.add_widget(DocsScreen(name="docs"))
        self._screens.add_widget(SettingsScreen(name="settings"))
        self.add_widget(self._screens)

        self.switch_tab("chat")
        self._apply_metrics(self._metrics)

    def _apply_metrics(self, metrics):
        self._metrics = metrics
        self._top.height = metrics.shell_height
        self._top.padding = [metrics.screen_pad_h, metrics.gap_sm, metrics.screen_pad_h, metrics.gap_sm]
        self._top.spacing = metrics.gap_sm

        self._title.height = metrics.shell_title_h
        self._title.font_size = TypeScale.LG if metrics.size_class == "medium" else TypeScale.MD

        self._segmented.height = metrics.shell_tabs_h
        self._segmented.padding = [metrics.gap_sm, metrics.gap_sm, metrics.gap_sm, metrics.gap_sm]
        self._segmented.spacing = metrics.gap_sm
        self._segmented.set_color(Theme.SURFACE_ALT)

        for btn in self._tabs.values():
            btn.height = metrics.shell_tab_btn_h

        for screen in self._screens.screens:
            callback = getattr(screen, "on_responsive_metrics", None)
            if callable(callback):
                callback(metrics)

    def _on_window_size(self, *_):
        self._apply_metrics(current_metrics())

    def switch_tab(self, name: str):
        if name not in self._tabs:
            return
        self._screens.current = name
        for key, btn in self._tabs.items():
            if key == name:
                btn.set_bg(Theme.PRIMARY)
                btn.color = Theme.TEXT
            else:
                btn.set_bg(Theme.SURFACE_ALT)
                btn.color = Theme.TEXT_MUTED


class RAGApp(App):
    title = "O-RAG"

    def _start_pipeline_init_async(self, *_):
        def _run():
            try:
                init()
            except Exception:
                _global_exception_handler(*sys.exc_info())

        threading.Thread(target=_run, daemon=True).start()

    def build(self):
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(*Theme.BG)
            bg = Rectangle()
        root.bind(pos=lambda w, _: setattr(bg, "pos", w.pos), size=lambda w, _: setattr(bg, "size", w.size))

        root.add_widget(AppShell())
        Clock.schedule_once(self._start_pipeline_init_async, 0.3)
        return root


if __name__ == "__main__":
    RAGApp().run()
