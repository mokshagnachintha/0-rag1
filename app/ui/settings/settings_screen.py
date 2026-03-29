"""Responsive Settings screen with diagnostics and maintenance controls."""
from __future__ import annotations

import time

from app.rag import pipeline
from app.runtime.bootstrap import BootstrapState
from app.ui.chat.controller import ChatController
from app.ui.responsive import current_metrics, is_split_class
from app.ui.theme import Theme, TypeScale
from app.ui.widgets import PillButton, SurfaceCard, bind_label_size, paint_background

from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._controller = ChatController()
        self._metrics = current_metrics()
        self._confirm_deadline = 0.0
        self._build_ui()
        Window.bind(size=self._on_window_size)
        Clock.schedule_once(lambda *_: self._register_bootstrap_callbacks(), 0)

    def on_pre_enter(self, *_):
        self._refresh_cards()

    def on_responsive_metrics(self, metrics):
        if metrics.size_class != self._metrics.size_class:
            self._metrics = metrics
            self._rebuild_ui()
        else:
            self._metrics = metrics
            self._apply_layout_metrics()

    def _on_window_size(self, *_):
        self.on_responsive_metrics(current_metrics())

    def _rebuild_ui(self):
        self.clear_widgets()
        self._build_ui()
        self._refresh_cards()

    def _build_ui(self):
        m = self._metrics
        root = BoxLayout(orientation="horizontal" if is_split_class(m.size_class) else "vertical")
        paint_background(root, Theme.BG)
        root.padding = [m.screen_pad_h, m.screen_pad_v, m.screen_pad_h, m.screen_pad_v]
        root.spacing = m.gap_md
        self._root = root

        left_col = BoxLayout(orientation="vertical", spacing=m.gap_sm, size_hint=(m.split_primary_ratio, 1) if is_split_class(m.size_class) else (1, 1))

        self._engine_card = SurfaceCard(color=Theme.SURFACE, orientation="vertical", size_hint=(1, None))
        self._engine_state = Label(
            text="[b]Engine:[/b] Unknown",
            markup=True,
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(22),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._engine_state)
        self._engine_detail = Label(
            text="Waiting for bootstrap events...",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._engine_detail)
        self._engine_hint = Label(
            text="",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._engine_hint)
        self._engine_card.add_widget(self._engine_state)
        self._engine_card.add_widget(self._engine_detail)
        self._engine_card.add_widget(self._engine_hint)
        left_col.add_widget(self._engine_card)

        self._stats_card = SurfaceCard(color=Theme.SURFACE, orientation="vertical", size_hint=(1, None))
        self._stats_docs = Label(
            text="Indexed docs: 0",
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(22),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._stats_docs)
        self._stats_chunks = Label(
            text="Indexed chunks: 0",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._stats_chunks)
        self._stats_model = Label(
            text="Model loaded: no",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._stats_model)
        self._stats_card.add_widget(self._stats_docs)
        self._stats_card.add_widget(self._stats_chunks)
        self._stats_card.add_widget(self._stats_model)
        left_col.add_widget(self._stats_card)

        self._status = Label(
            text="",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._status)
        left_col.add_widget(self._status)

        root.add_widget(left_col)

        self._action_col = BoxLayout(orientation="vertical", size_hint=(1 - m.split_primary_ratio, 1) if is_split_class(m.size_class) else (1, None), spacing=m.gap_sm)
        self._action_card = SurfaceCard(color=Theme.SURFACE, orientation="vertical", size_hint=(1, None))

        refresh_btn = PillButton(
            text="Refresh Diagnostics",
            bg_color=Theme.PRIMARY_DARK,
            size_hint=(1, None),
            height=m.control_h,
            font_size=TypeScale.SM,
            radius=m.control_radius,
        )
        refresh_btn.bind(on_release=lambda *_: self._refresh_cards())

        self._clear_btn = PillButton(
            text="Clear All Documents",
            bg_color=Theme.DANGER,
            size_hint=(1, None),
            height=m.control_h,
            font_size=TypeScale.SM,
            radius=m.control_radius,
        )
        self._clear_btn.bind(on_release=self._on_clear_documents)

        self._action_card.add_widget(refresh_btn)
        self._action_card.add_widget(self._clear_btn)
        self._action_col.add_widget(self._action_card)
        root.add_widget(self._action_col)

        self.add_widget(root)
        self._apply_layout_metrics()

    def _apply_layout_metrics(self):
        m = self._metrics
        self._root.padding = [m.screen_pad_h, m.screen_pad_v, m.screen_pad_h, m.screen_pad_v]
        self._root.spacing = m.gap_sm

        self._engine_card.height = m.docs_summary_h + m.gap_sm
        self._engine_card.padding = [m.gap_md, m.gap_sm, m.gap_md, m.gap_sm]
        self._engine_card.spacing = m.gap_xs

        self._stats_card.height = m.docs_summary_h + m.gap_xs
        self._stats_card.padding = [m.gap_md, m.gap_sm, m.gap_md, m.gap_sm]
        self._stats_card.spacing = m.gap_xs

        self._action_card.height = (m.control_h * 2) + (m.gap_sm * 3)
        self._action_card.padding = [m.gap_sm, m.gap_sm, m.gap_sm, m.gap_sm]
        self._action_card.spacing = m.gap_sm

        if is_split_class(m.size_class):
            self._action_col.size_hint = (1 - m.split_primary_ratio, 1)
            self._action_col.height = 0
        else:
            self._action_col.size_hint = (1, None)
            self._action_col.height = self._action_card.height

    def _register_bootstrap_callbacks(self):
        self._controller.register_bootstrap_callbacks(
            on_progress=self._on_bootstrap_progress,
            on_done=self._on_bootstrap_done,
        )
        self._refresh_cards()

    def _set_status(self, text: str, tone: str = "muted"):
        color = Theme.TEXT_MUTED
        if tone == "success":
            color = Theme.SUCCESS
        elif tone == "danger":
            color = Theme.DANGER
        elif tone == "warning":
            color = Theme.WARNING
        self._status.color = color
        self._status.text = text

    def _refresh_cards(self):
        try:
            docs = self._controller.list_documents()
        except Exception:
            docs = []
        chunk_total = sum(int(doc.get("num_chunks", 0)) for doc in docs)
        self._stats_docs.text = f"Indexed docs: {len(docs)}"
        self._stats_chunks.text = f"Indexed chunks: {chunk_total}"
        self._stats_model.text = f"Model loaded: {'yes' if pipeline.is_model_loaded() else 'no'}"

        try:
            event = self._controller.get_bootstrap_state()
            self._apply_bootstrap_state(event.state, event.message)
        except Exception:
            self._apply_bootstrap_state(BootstrapState.IDLE, "")

    def _apply_bootstrap_state(self, state, message: str):
        if state == BootstrapState.READY:
            self._engine_state.text = "[b]Engine:[/b] Ready"
            self._engine_state.color = Theme.SUCCESS
            self._engine_detail.text = message or "Local runtime is healthy."
            self._engine_hint.text = "Chat and docs mode available."
            return

        if state == BootstrapState.DOWNLOADING:
            self._engine_state.text = "[b]Engine:[/b] Downloading"
            self._engine_state.color = Theme.WARNING
            self._engine_detail.text = message or "Preparing first-run assets."
            self._engine_hint.text = "Send actions are locked until startup completes."
            return

        if state == BootstrapState.ERROR:
            self._engine_state.text = "[b]Engine:[/b] Error"
            self._engine_state.color = Theme.DANGER
            self._engine_detail.text = message or "Bootstrap failed."
            self._engine_hint.text = "Check network for first launch and retry app startup."
            return

        self._engine_state.text = "[b]Engine:[/b] Idle"
        self._engine_state.color = Theme.TEXT_MUTED
        self._engine_detail.text = message or "Waiting for bootstrap state."
        self._engine_hint.text = "Open Chat tab to trigger startup flow."

    @mainthread
    def _on_bootstrap_progress(self, _progress: float, message: str):
        self._apply_bootstrap_state(BootstrapState.DOWNLOADING, message)

    @mainthread
    def _on_bootstrap_done(self, success: bool, message: str):
        self._apply_bootstrap_state(BootstrapState.READY if success else BootstrapState.ERROR, message)
        self._set_status(message, tone="success" if success else "danger")

    def _on_clear_documents(self, *_):
        now = time.monotonic()
        if now > self._confirm_deadline:
            self._confirm_deadline = now + 3.0
            self._clear_btn.text = "Tap Again To Confirm"
            self._set_status("Confirmation armed for 3 seconds.", tone="warning")
            Clock.schedule_once(self._reset_clear_button, 3.1)
            return

        self._controller.clear_documents()
        self._reset_clear_button()
        self._set_status("All documents cleared.", tone="warning")
        self._refresh_cards()

    def _reset_clear_button(self, *_):
        self._confirm_deadline = 0.0
        self._clear_btn.text = "Clear All Documents"
