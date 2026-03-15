from __future__ import annotations

from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from ui.controller import AppController
from ui.screens.boot_screen import BootScreen
from ui.screens.chat_screen import ChatScreen
from ui.screens.docs_screen import DocsScreen
from ui.screens.settings_screen import SettingsScreen


class AppShell(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.controller = AppController()
        self._nav_buttons: dict[str, Button] = {}
        self._nav = None
        self._build()

    def _build(self):
        with self.canvas.before:
            Color(0.09, 0.09, 0.10, 1)
            self._bg = Rectangle()
        self.bind(
            pos=lambda w, _: setattr(self._bg, "pos", w.pos),
            size=lambda w, _: setattr(self._bg, "size", w.size),
        )

        self.sm = ScreenManager(transition=FadeTransition(duration=0.12))

        self.sm.add_widget(BootScreen(
            controller=self.controller,
            on_continue=lambda: self.go("chat"),
            name="boot",
        ))
        self.sm.add_widget(ChatScreen(controller=self.controller, name="chat"))
        self.sm.add_widget(DocsScreen(controller=self.controller, name="docs"))
        self.sm.add_widget(SettingsScreen(controller=self.controller, name="settings"))
        self.add_widget(self.sm)

        nav = BoxLayout(
            size_hint=(1, None),
            height=dp(58),
            spacing=dp(8),
            padding=[dp(10), dp(10), dp(10), dp(10)],
        )
        with nav.canvas.before:
            Color(0.12, 0.12, 0.13, 1)
            self._nav_bg = Rectangle()
        nav.bind(
            pos=lambda w, _: setattr(self._nav_bg, "pos", w.pos),
            size=lambda w, _: setattr(self._nav_bg, "size", w.size),
        )

        for label, target in [("Chat", "chat"), ("Documents", "docs"), ("Settings", "settings")]:
            btn = Button(
                text=label,
                background_normal="",
                background_color=(0.20, 0.20, 0.22, 1),
            )
            btn.bind(on_release=lambda _, t=target: self.go(t))
            nav.add_widget(btn)
            self._nav_buttons[target] = btn

        self._nav = nav
        self.add_widget(nav)

        # Bind only after nav exists; ScreenManager emits 'current'
        # during add_widget(), and this prevents early callback crashes.
        self.sm.bind(current=self._on_screen_changed)
        self._update_nav_visibility()
        self._highlight_active_button()

    def go(self, screen_name: str):
        self.sm.current = screen_name

    def _on_screen_changed(self, *_):
        self._update_nav_visibility()
        self._highlight_active_button()

    def _update_nav_visibility(self):
        if self._nav is None:
            return
        is_boot = self.sm.current == "boot"
        self._nav.height = 0 if is_boot else dp(58)
        self._nav.opacity = 0 if is_boot else 1
        self._nav.disabled = is_boot

    def _highlight_active_button(self):
        if not self._nav_buttons:
            return
        active = self.sm.current
        for name, btn in self._nav_buttons.items():
            btn.background_color = (
                (0.14, 0.62, 0.44, 1) if name == active else (0.20, 0.20, 0.22, 1)
            )
