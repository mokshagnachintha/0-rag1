"""Offline RAG app entry point with segmented top navigation."""

import os
os.environ.setdefault("KIVY_LOG_LEVEL", "warning")

from app.config import ENV_FORCE_BOOTSTRAP_DOWNLOAD

if not os.environ.get("ANDROID_PRIVATE"):
    os.environ.setdefault(ENV_FORCE_BOOTSTRAP_DOWNLOAD, "1")

from kivy.config import Config
Config.set("kivy", "window_icon", "assets/app_icon.png")

from kivy.core.window import Window
Window.softinput_mode = "below_target"

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, ScreenManager

import sys
import threading
import traceback

sys.path.insert(0, os.path.dirname(__file__))

from app.rag.pipeline import init
from app.ui.chat.chat_screen import ChatScreen
from app.ui.docs.docs_screen import DocsScreen
from app.ui.settings.settings_screen import SettingsScreen
from app.ui.theme import MIN_TOUCH, Radius, Space, Theme, TypeScale
from app.ui.widgets import PillButton, SurfaceCard, bind_label_size, paint_background


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
        self._build_ui()

    def _build_ui(self):
        top = SurfaceCard(
            radius=0,
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=(1, None),
            height=dp(130),
            padding=[Space.MD, Space.SM],
            spacing=Space.SM,
        )

        title = Label(
            text="[b]O-RAG[/b]",
            markup=True,
            color=Theme.TEXT,
            font_size=TypeScale.XL,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(28),
        )
        bind_label_size(title)
        top.add_widget(title)

        segmented = SurfaceCard(
            radius=Radius.PILL,
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(1, None),
            height=MIN_TOUCH + 8,
            padding=[Space.XS, Space.XS],
            spacing=Space.XS,
        )

        for label, name in (("Chat", "chat"), ("Documents", "docs"), ("Settings", "settings")):
            btn = PillButton(
                text=label,
                bg_color=Theme.SURFACE_ALT,
                size_hint=(1, None),
                height=MIN_TOUCH,
                font_size=TypeScale.SM,
            )
            btn.bind(on_release=lambda _, target=name: self.switch_tab(target))
            segmented.add_widget(btn)
            self._tabs[name] = btn

        top.add_widget(segmented)
        self.add_widget(top)

        self._screens = ScreenManager(transition=NoTransition())
        self._screens.add_widget(ChatScreen(name="chat", open_docs_tab=lambda: self.switch_tab("docs")))
        self._screens.add_widget(DocsScreen(name="docs"))
        self._screens.add_widget(SettingsScreen(name="settings"))
        self.add_widget(self._screens)

        self.switch_tab("chat")

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

        shell = AppShell()
        root.add_widget(shell)

        Clock.schedule_once(self._start_pipeline_init_async, 0.3)
        return root


if __name__ == "__main__":
    RAGApp().run()

