"""
main.py — Offline RAG App entry point (Kivy / Android).

Single-screen design: one chat interface.
  • Tap + to attach a PDF or TXT document (RAG mode activates automatically)
  • Otherwise chat freely with the AI
  • Model is bundled in the APK — extracted to device storage on first launch
"""

# ── Kivy config BEFORE any other kivy import ──────────────────────── #
import os
os.environ.setdefault("KIVY_LOG_LEVEL", "warning")
# Desktop development helper:
# force model bootstrap download flow on every local run.
# (Android builds are unaffected.)
if not os.environ.get("ANDROID_PRIVATE"):
    os.environ.setdefault("ORAG_FORCE_BOOTSTRAP_DOWNLOAD", "1")

from kivy.config import Config
Config.set("kivy", "window_icon", "assets/icon.png")
# ─────────────────────────────────────────────────────────────────── #

# Keep input bar visible above the soft keyboard on Android
from kivy.core.window import Window
Window.softinput_mode = "below_target"

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.graphics import Color, Rectangle
from kivy.clock import Clock

import sys
import threading
import traceback
sys.path.insert(0, os.path.dirname(__file__))

from ui.screens.chat_screen import ChatScreen
from rag.pipeline           import init


_SERVICE_START_LOCK = threading.Lock()
_SERVICE_STARTED = False


def _global_exception_handler(exc_type, exc_value, exc_tb):
    """Log unhandled exceptions instead of silently crashing."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"[CRASH] Unhandled exception:\n{msg}")
    # Write to Android log file if possible
    priv = os.environ.get("ANDROID_PRIVATE", "")
    if priv:
        try:
            with open(os.path.join(priv, "crash.log"), "a") as f:
                f.write(msg + "\n")
        except Exception:
            pass

sys.excepthook = _global_exception_handler


def _start_android_service():
    """Start the foreground service that owns llama-server processes.
    No-op on desktop (ImportError is silently ignored).
    """
    global _SERVICE_STARTED
    with _SERVICE_START_LOCK:
        if _SERVICE_STARTED:
            return
    try:
        from android import AndroidService  # type: ignore
        svc = AndroidService("O-RAG AI Engine", "AI engine running in background")
        svc.start("start")
        _SERVICE_STARTED = True
        print("[main] Android foreground service started.")
    except Exception as exc:
        print(f"[main] Service start skipped: {exc}")


class RAGApp(App):
    title = "O-RAG"

    def _start_pipeline_init_async(self, *_):
        """Run heavy startup work off the UI thread to avoid ANR/freezes."""
        def _run():
            try:
                init()
            except Exception:
                _global_exception_handler(*sys.exc_info())
        threading.Thread(target=_run, daemon=True).start()

    def build(self):
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(0.102, 0.102, 0.102, 1)   # #1a1a1a
            bg = Rectangle()
        root.bind(
            pos =lambda w, _: setattr(bg, "pos",  w.pos),
            size=lambda w, _: setattr(bg, "size", w.size),
        )

        sm = ScreenManager(transition=FadeTransition(duration=0.12))
        sm.add_widget(ChatScreen(name="chat"))
        root.add_widget(sm)

        # Start service early (Android only) so model bootstrap can connect to it.
        Clock.schedule_once(
            lambda *_: _start_android_service(),
            0.05,
        )

        # Init DB + retriever + model bootstrap in background thread.
        # Delay by 0.3 s so the ChatScreen's pipeline callbacks are registered
        # first — prevents a race where models load before the UI can hear about it.
        Clock.schedule_once(self._start_pipeline_init_async, 0.3)
        return root


if __name__ == "__main__":
    RAGApp().run()

