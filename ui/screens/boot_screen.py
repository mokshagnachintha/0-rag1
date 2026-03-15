from __future__ import annotations

from kivy.clock import Clock, mainthread
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen

from ui.controller import AppController


class BootScreen(Screen):
    def __init__(self, controller: AppController, on_continue, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller
        self.on_continue = on_continue
        self._ready = False
        self._build_ui()

        self.controller.events.subscribe("model_progress", self._on_model_progress)
        self.controller.events.subscribe("model_ready", self._on_model_ready)

    def on_pre_enter(self, *_):
        self.controller.initialize()

    def _build_ui(self):
        root = BoxLayout(
            orientation="vertical",
            padding=[dp(20), dp(40), dp(20), dp(40)],
            spacing=dp(14),
        )

        root.add_widget(Label(
            text="[b]O-RAG v2[/b]",
            markup=True,
            font_size=sp(30),
            size_hint=(1, None),
            height=dp(62),
        ))
        root.add_widget(Label(
            text="Offline AI assistant rebuilt with a clean architecture.",
            font_size=sp(14),
            color=(0.75, 0.75, 0.78, 1),
            size_hint=(1, None),
            height=dp(28),
        ))

        self._progress = ProgressBar(
            max=100, value=0,
            size_hint=(1, None), height=dp(8),
        )
        root.add_widget(self._progress)

        self._status = Label(
            text="Preparing AI models...",
            font_size=sp(13),
            color=(0.85, 0.85, 0.9, 1),
            size_hint=(1, None),
            height=dp(28),
        )
        root.add_widget(self._status)

        root.add_widget(Label(size_hint=(1, 1)))

        self._cta = Button(
            text="Initializing...",
            size_hint=(1, None),
            height=dp(48),
            disabled=True,
            background_normal="",
            background_color=(0.15, 0.55, 0.38, 1),
            font_size=sp(15),
        )
        self._cta.bind(on_release=lambda *_: self._continue())
        root.add_widget(self._cta)

        self.add_widget(root)

    def _continue(self):
        if self._ready:
            self.on_continue()

    def _on_model_progress(self, fraction: float, text: str):
        self._apply_progress(fraction, text)

    def _on_model_ready(self, success: bool, message: str):
        self._apply_ready(success, message)

    @mainthread
    def _apply_progress(self, fraction: float, text: str):
        self._progress.value = int(max(0.0, min(1.0, fraction)) * 100)
        self._status.text = text

    @mainthread
    def _apply_ready(self, success: bool, message: str):
        if success:
            self._ready = True
            self._progress.value = 100
            self._status.text = "AI models ready."
            self._cta.disabled = False
            self._cta.text = "Enter App"
            Clock.schedule_once(lambda *_: self._continue(), 0.6)
        else:
            self._ready = False
            self._status.text = f"Startup failed: {message}"
            self._cta.disabled = True
            self._cta.text = "Startup Failed"
