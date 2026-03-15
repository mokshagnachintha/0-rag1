"""
main.py -- O-RAG app entry point (v2 architecture).
"""
from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("KIVY_LOG_LEVEL", "warning")

from kivy.app import App
from kivy.config import Config
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform as kivy_platform

sys.path.insert(0, os.path.dirname(__file__))

from ui.app_shell import AppShell


Config.set("kivy", "window_icon", "assets/icon.png")

if kivy_platform == "android":
    Window.softinput_mode = "below_target"
else:
    Window.softinput_mode = "pan"


def _global_exception_handler(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"[CRASH] Unhandled exception:\n{msg}")
    priv = os.environ.get("ANDROID_PRIVATE", "")
    if priv:
        try:
            with open(os.path.join(priv, "crash.log"), "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass


sys.excepthook = _global_exception_handler


def _start_android_service():
    """Start foreground service that owns llama-server process(es)."""
    try:
        from android import AndroidService  # type: ignore

        svc = AndroidService("O-RAG AI Engine", "AI engine running in background")
        svc.start("start")
        print("[main] Android foreground service started.")
    except Exception as exc:
        print(f"[main] Service start skipped: {exc}")


class RAGApp(App):
    title = "O-RAG"

    def build(self):
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(0.102, 0.102, 0.102, 1)
            bg = Rectangle()
        root.bind(
            pos=lambda w, _: setattr(bg, "pos", w.pos),
            size=lambda w, _: setattr(bg, "size", w.size),
        )

        root.add_widget(AppShell())
        _start_android_service()
        return root


if __name__ == "__main__":
    RAGApp().run()
