"""Responsive chat screen with compact inline mode toggle."""
from __future__ import annotations

import time
from pathlib import Path

from app.runtime.bootstrap import BootstrapState
from app.ui.chat.controller import ChatController
from app.ui.chat.mode_logic import (
    CHAT_MODE_DOCUMENT,
    CHAT_MODE_GENERAL,
    is_quit_rag_alias,
    mode_title,
    resolve_send_mode,
)
from app.ui.responsive import current_metrics
from app.ui.theme import Theme, TypeScale
from app.ui.widgets import PillButton, SurfaceCard, bind_label_size, paint_background

from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import escape_markup


class RoleBubble(BoxLayout):
    """Single message row with side-aware bubble alignment."""

    def __init__(self, text: str, role: str, metrics_getter, **kwargs):
        super().__init__(orientation="horizontal", size_hint=(1, None), **kwargs)
        self.role = role
        self._metrics_getter = metrics_getter
        self._label = Label(
            text=text,
            markup=True,
            size_hint=(None, None),
            text_size=(dp(180), None),
            halign="left",
            valign="middle",
            color=Theme.TEXT,
            font_size=TypeScale.MD,
        )
        self._label.bind(texture_size=self._on_texture)
        self.bind(width=self._on_width)

        bubble_color = Theme.USER_BUBBLE if role == "user" else Theme.ASSISTANT_BUBBLE
        self._bubble = SurfaceCard(
            color=bubble_color,
            orientation="vertical",
            size_hint=(None, None),
        )
        self._bubble.add_widget(self._label)

        if role == "user":
            self.add_widget(Widget(size_hint_x=1))
            self.add_widget(self._role_chip("YOU"))
            self.add_widget(self._bubble)
        else:
            self.add_widget(self._bubble)
            self.add_widget(self._role_chip("AI"))
            self.add_widget(Widget(size_hint_x=1))

        self._apply_metrics()

    def _role_chip(self, text: str) -> Widget:
        holder = AnchorLayout(size_hint=(None, None), size=(dp(34), dp(26)))
        chip = SurfaceCard(color=Theme.SURFACE_ALT, size_hint=(None, None), size=(dp(32), dp(22)))
        lbl = Label(text=text, color=Theme.TEXT_MUTED, font_size=TypeScale.XS, bold=True)
        bind_label_size(lbl)
        chip.add_widget(lbl)
        holder.add_widget(chip)
        return holder

    def _apply_metrics(self):
        metrics = self._metrics_getter()
        self.padding = [metrics.gap_sm, metrics.gap_sm, metrics.gap_sm, metrics.gap_sm]
        self.spacing = metrics.gap_sm
        self._bubble.set_color(Theme.USER_BUBBLE if self.role == "user" else Theme.ASSISTANT_BUBBLE)

    def _on_texture(self, _, texture_size):
        metrics = self._metrics_getter()
        if not hasattr(self, "_bubble"):
            return
        width = min(texture_size[0] + dp(8), self.width * metrics.bubble_ratio)
        width = max(width, metrics.bubble_min)
        self._label.size = (width, texture_size[1] + dp(4))
        self._bubble.size = (width + metrics.gap_md * 2, self._label.height + metrics.gap_sm * 2)
        self.height = self._bubble.height + metrics.gap_sm

    def _on_width(self, *_):
        metrics = self._metrics_getter()
        max_width = max(metrics.bubble_min, self.width * metrics.bubble_ratio)
        self._label.text_size = (max_width, None)

    def append(self, token: str):
        self._label.text += escape_markup(token)


class IngestStatusCard(SurfaceCard):
    _COLORS = {
        "queued": Theme.TEXT_MUTED,
        "ingesting": Theme.WARNING,
        "indexed": Theme.SUCCESS,
        "failed": Theme.DANGER,
    }

    def __init__(self, filename: str, metrics_getter, **kwargs):
        self._metrics_getter = metrics_getter
        super().__init__(orientation="vertical", size_hint=(1, None), **kwargs)
        self._title = Label(
            text=f"[b]Document:[/b] {escape_markup(filename)}",
            markup=True,
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._title)
        self._stage = Label(
            text="Queued",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._stage)
        self.add_widget(self._title)
        self.add_widget(self._stage)
        self.apply_metrics()

    def apply_metrics(self):
        m = self._metrics_getter()
        self.padding = [m.gap_md, m.gap_sm, m.gap_md, m.gap_sm]
        self.spacing = dp(2)
        self.height = dp(62)
        self._title.height = dp(22)
        self._stage.height = dp(18)

    def set_stage(self, stage: str, detail: str = ""):
        text = stage.capitalize() if not detail else f"{stage.capitalize()}: {escape_markup(detail)}"
        self._stage.color = self._COLORS.get(stage, Theme.TEXT_MUTED)
        self._stage.text = text

    def set_done(self, success: bool, message: str):
        self.set_stage("indexed" if success else "failed", message)


class AttachmentPreviewCard(SurfaceCard):
    def __init__(self, filepath: str, on_remove, metrics_getter, **kwargs):
        self._metrics_getter = metrics_getter
        super().__init__(orientation="horizontal", size_hint=(None, None), **kwargs)

        name = Path(filepath).name
        ext = Path(filepath).suffix.upper().replace(".", "") or "FILE"
        title = name if len(name) <= 24 else f"{name[:21]}..."

        icon = SurfaceCard(color=Theme.PRIMARY_DARK, size_hint=(None, None), size=(dp(36), dp(36)))
        icon_lbl = Label(text=ext[:4], color=Theme.TEXT, bold=True, font_size=TypeScale.XS)
        bind_label_size(icon_lbl)
        icon.add_widget(icon_lbl)
        self.add_widget(icon)

        info = BoxLayout(orientation="vertical", spacing=dp(2))
        name_lbl = Label(
            text=f"[b]{escape_markup(title)}[/b]",
            markup=True,
            color=Theme.TEXT,
            font_size=TypeScale.SM,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(20),
        )
        bind_label_size(name_lbl)
        kind_lbl = Label(
            text=f"{ext} attachment",
            color=Theme.TEXT_MUTED,
            font_size=TypeScale.XS,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(16),
        )
        bind_label_size(kind_lbl)
        info.add_widget(name_lbl)
        info.add_widget(kind_lbl)
        self.add_widget(info)

        remove_btn = Button(
            text="X",
            size_hint=(None, None),
            size=(dp(22), dp(22)),
            background_normal="",
            background_color=(0, 0, 0, 0),
            color=Theme.TEXT_MUTED,
            font_size=TypeScale.XS,
        )
        remove_btn.bind(on_release=lambda *_: on_remove())
        self.add_widget(remove_btn)
        self.apply_metrics()

    def apply_metrics(self):
        m = self._metrics_getter()
        self.padding = [m.gap_sm, m.gap_sm, m.gap_sm, m.gap_sm]
        self.spacing = m.gap_sm
        self.size = (dp(220) if m.size_class == "compact" else dp(250), m.attach_strip_h - dp(10))


class TypingIndicator(BoxLayout):
    def __init__(self, metrics_getter, **kwargs):
        super().__init__(orientation="horizontal", size_hint=(1, None), **kwargs)
        self._metrics_getter = metrics_getter
        self._dots: list[Label] = []
        self._tick = 0
        for _ in range(3):
            dot = Label(text=".", color=Theme.TEXT_MUTED, font_size=TypeScale.MD, size_hint=(None, 1), width=dp(10))
            self._dots.append(dot)
            self.add_widget(dot)
        self.apply_metrics()
        Clock.schedule_interval(self._pulse, 0.36)

    def apply_metrics(self):
        m = self._metrics_getter()
        self.height = dp(24)
        self.spacing = dp(4)
        self.padding = [m.gap_md, 0, m.gap_md, 0]

    def _pulse(self, *_):
        for idx, dot in enumerate(self._dots):
            dot.color = Theme.TEXT if idx == self._tick % 3 else Theme.TEXT_MUTED
        self._tick += 1

    def stop(self):
        Clock.unschedule(self._pulse)


class ChatScreen(Screen):
    _PICK_REQ = 0x4F52

    def __init__(self, open_docs_tab=None, **kwargs):
        super().__init__(**kwargs)
        self._open_docs_tab = open_docs_tab
        self._controller = ChatController()
        self._metrics = current_metrics()

        self._selected_mode = CHAT_MODE_GENERAL
        self._model_ready = False
        self._doc_count = 0
        self._pending_attach: str | None = None
        self._picker_open = False
        self._perm_requested = False

        self._history: list[tuple[str, str]] = []
        self._history_summary = ""

        self._streaming_active = False
        self._pending_q = ""
        self._active_response_mode = CHAT_MODE_GENERAL
        self._current_row: RoleBubble | None = None
        self._typing: TypingIndicator | None = None
        self._token_buf: list[str] = []
        self._token_flush_ev = None
        self._active_task_id: str | None = None
        self._message_widgets: list[Widget] = []
        self._max_message_widgets = 50

        self._last_model_pct = -1
        self._last_model_update_at = 0.0
        self._engine_error = False

        self._build_ui()
        Window.bind(size=self._on_window_size)

    def _get_metrics(self):
        return self._metrics

    def on_pre_enter(self, *_):
        self._refresh_document_inventory()

    def on_responsive_metrics(self, metrics):
        self._metrics = metrics
        self._apply_responsive_layout()

    def _on_window_size(self, *_):
        self.on_responsive_metrics(current_metrics())

    def _build_ui(self):
        m = self._metrics
        root = BoxLayout(orientation="vertical")
        paint_background(root, Theme.BG)
        self._root = root

        self._engine_card = SurfaceCard(color=Theme.SURFACE, orientation="vertical", size_hint=(1, None))
        self._engine_state = Label(
            text="[b]ENGINE:[/b] Starting",
            markup=True,
            color=Theme.WARNING,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._engine_state)
        self._engine_detail = Label(
            text="Preparing offline model",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._engine_detail)
        self._engine_card.add_widget(self._engine_state)
        self._engine_card.add_widget(self._engine_detail)
        root.add_widget(self._engine_card)

        self._docs_notice = SurfaceCard(
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(1, None),
            height=0,
        )
        self._notice_lbl = Label(
            text="Document mode needs indexed files.",
            color=Theme.TEXT_MUTED,
            font_size=TypeScale.XS,
            halign="left",
            valign="middle",
        )
        bind_label_size(self._notice_lbl)
        self._open_docs_btn = PillButton(
            text="Open Docs",
            bg_color=Theme.PRIMARY_DARK,
            size_hint=(None, None),
            font_size=TypeScale.XS,
            radius=m.control_radius,
        )
        self._open_docs_btn.bind(on_release=lambda *_: self._go_to_docs())
        self._docs_notice.add_widget(self._notice_lbl)
        self._docs_notice.add_widget(self._open_docs_btn)
        root.add_widget(self._docs_notice)

        self._scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._msgs = BoxLayout(orientation="vertical", size_hint=(1, None))
        self._msgs.bind(minimum_height=self._msgs.setter("height"))
        self._scroll.add_widget(self._msgs)
        root.add_widget(self._scroll)

        self._empty_state = SurfaceCard(color=Theme.SURFACE_ALT, orientation="vertical", size_hint=(1, None), height=dp(88))
        self._empty_title = Label(
            text="[b]Welcome to O-RAG[/b]",
            markup=True,
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(24),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._empty_title)
        self._empty_hint = Label(
            text="Ask in General mode or index docs for Document Q&A.",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._empty_hint)
        self._empty_actions = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(28), spacing=dp(6))
        self._empty_prompt_btn = PillButton(
            text="Try Prompt",
            bg_color=Theme.SURFACE,
            size_hint=(None, None),
            size=(dp(88), dp(28)),
            font_size=TypeScale.XS,
            radius=m.chip_radius,
        )
        self._empty_prompt_btn.bind(on_release=lambda *_: self._prefill_prompt())
        self._empty_docs_btn = PillButton(
            text="Open Docs",
            bg_color=Theme.PRIMARY_DARK,
            size_hint=(None, None),
            size=(dp(88), dp(28)),
            font_size=TypeScale.XS,
            radius=m.chip_radius,
        )
        self._empty_docs_btn.bind(on_release=lambda *_: self._go_to_docs())
        self._empty_actions.add_widget(self._empty_prompt_btn)
        self._empty_actions.add_widget(self._empty_docs_btn)
        self._empty_state.add_widget(self._empty_title)
        self._empty_state.add_widget(self._empty_hint)
        self._empty_state.add_widget(self._empty_actions)
        self._msgs.add_widget(self._empty_state)

        self._input_zone = SurfaceCard(color=Theme.SURFACE, orientation="vertical", size_hint=(1, None))

        self._attach_strip = BoxLayout(orientation="horizontal", size_hint=(1, None), height=0)
        self._input_zone.add_widget(self._attach_strip)

        self._composer_meta = BoxLayout(orientation="horizontal", size_hint=(1, None))
        self._mode_label = Label(
            text="Mode",
            color=Theme.TEXT_MUTED,
            font_size=TypeScale.XS,
            halign="left",
            valign="middle",
            size_hint=(1, 1),
        )
        bind_label_size(self._mode_label)

        self._btn_general = PillButton(
            text="General",
            bg_color=Theme.PRIMARY,
            size_hint=(None, None),
            font_size=TypeScale.XS,
            radius=m.control_radius,
        )
        self._btn_general.bind(on_release=lambda *_: self._set_mode(CHAT_MODE_GENERAL))
        self._btn_document = PillButton(
            text="Docs",
            bg_color=Theme.SURFACE_ALT,
            size_hint=(None, None),
            font_size=TypeScale.XS,
            radius=m.control_radius,
        )
        self._btn_document.bind(on_release=lambda *_: self._set_mode(CHAT_MODE_DOCUMENT))

        self._engine_inline = SurfaceCard(
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(None, None),
            radius=m.chip_radius,
        )
        self._engine_inline_label = Label(
            text="ENGINE Starting",
            color=Theme.WARNING,
            font_size=TypeScale.XS,
            halign="center",
            valign="middle",
            size_hint=(1, 1),
        )
        bind_label_size(self._engine_inline_label)
        self._engine_inline.add_widget(self._engine_inline_label)

        self._composer_meta.add_widget(self._mode_label)
        self._composer_meta.add_widget(self._btn_general)
        self._composer_meta.add_widget(self._btn_document)
        self._composer_meta.add_widget(self._engine_inline)
        self._input_zone.add_widget(self._composer_meta)

        self._input_row = BoxLayout(orientation="horizontal", size_hint=(1, None))
        self._attach_btn = PillButton(
            text="+",
            bg_color=Theme.SURFACE_ALT,
            size_hint=(None, None),
            font_size=TypeScale.LG,
            radius=m.control_radius,
        )
        self._attach_btn.bind(on_release=self._on_attach)
        self._input_row.add_widget(self._attach_btn)

        self._input_shell = SurfaceCard(color=Theme.SURFACE_ALT, orientation="horizontal", size_hint=(1, None))
        self._input = TextInput(
            hint_text="Type a message...",
            multiline=False,
            size_hint=(1, 1),
            font_size=TypeScale.MD,
            foreground_color=Theme.TEXT,
            hint_text_color=Theme.TEXT_MUTED,
            background_color=(0, 0, 0, 0),
            cursor_color=Theme.TEXT,
        )
        self._input.bind(on_text_validate=self._on_send)
        self._input_shell.add_widget(self._input)

        self._send_btn = PillButton(
            text=">",
            bg_color=Theme.PRIMARY,
            size_hint=(None, None),
            font_size=TypeScale.MD,
            radius=m.control_radius,
        )
        self._send_btn.bind(on_release=self._on_send)
        self._input_shell.add_widget(self._send_btn)

        self._input_row.add_widget(self._input_shell)
        self._input_zone.add_widget(self._input_row)
        root.add_widget(self._input_zone)

        self.add_widget(root)
        self._apply_responsive_layout()
        self._set_send_enabled(False)
        self._set_mode(CHAT_MODE_GENERAL)
        Clock.schedule_once(self._register_pipeline_callbacks, 0)

    def _apply_responsive_layout(self):
        m = self._metrics
        self._root.padding = [m.screen_pad_h, m.screen_pad_v, m.screen_pad_h, m.screen_pad_v]
        self._root.spacing = m.gap_sm

        self._engine_card.padding = [m.gap_md, m.gap_sm, m.gap_md, m.gap_sm]
        self._engine_card.spacing = m.gap_xs
        self._engine_state.height = dp(22)
        self._engine_detail.height = dp(18)

        self._docs_notice.padding = [m.gap_sm, m.gap_sm, m.gap_sm, m.gap_sm]
        self._docs_notice.spacing = m.gap_sm
        self._open_docs_btn.size = (dp(92), m.mode_button_h)

        self._msgs.spacing = m.gap_xs

        if hasattr(self, "_empty_state"):
            self._empty_state.padding = [m.gap_md, m.gap_sm, m.gap_md, m.gap_sm]
            self._empty_state.spacing = m.gap_xs
            self._empty_state.height = m.docs_summary_h + dp(20)
            self._empty_actions.height = m.mode_button_h
            self._empty_prompt_btn.size = (dp(88), m.mode_button_h)
            self._empty_docs_btn.size = (dp(88), m.mode_button_h)

        self._input_zone.padding = [m.gap_sm, m.gap_sm, m.gap_sm, m.gap_sm]
        self._input_zone.spacing = m.gap_sm

        self._composer_meta.height = m.mode_button_h
        self._composer_meta.spacing = m.gap_sm
        self._btn_general.size = (dp(74), m.mode_button_h)
        self._btn_document.size = (dp(58), m.mode_button_h)
        self._engine_inline.size = (dp(106), m.mode_button_h)

        self._input_row.height = m.control_h
        self._input_row.spacing = m.gap_sm

        control_h = m.control_h
        self._attach_btn.size = (m.icon_button_h, m.icon_button_h)

        self._input_shell.height = control_h
        self._input_shell.padding = [m.gap_md, m.gap_xs, m.gap_sm, m.gap_xs]
        self._input_shell.spacing = m.gap_sm
        self._send_btn.size = (m.send_button_h, m.send_button_h)

        base_input_h = m.input_zone_h + m.mode_button_h + m.gap_sm
        if self._pending_attach:
            self._attach_strip.height = m.attach_strip_h
            self._input_zone.height = base_input_h + m.attach_strip_h
        else:
            self._attach_strip.height = 0
            self._input_zone.height = base_input_h
        self._refresh_mode_hint()
        self._refresh_engine_card_height()

        for child in self._msgs.children:
            if isinstance(child, IngestStatusCard):
                child.apply_metrics()
            elif isinstance(child, TypingIndicator):
                child.apply_metrics()
            elif isinstance(child, RoleBubble):
                child._apply_metrics()
                child._on_width()

        if self._attach_strip.children:
            card = self._attach_strip.children[0]
            if isinstance(card, AttachmentPreviewCard):
                card.apply_metrics()

    def _refresh_engine_card_height(self):
        m = self._metrics
        if self._model_ready:
            self._engine_card.height = 0
            self._engine_inline.opacity = 1
            self._engine_inline_label.text = "ENGINE Ready"
            self._engine_inline_label.color = Theme.SUCCESS
        else:
            self._engine_card.height = m.engine_expanded_h
            self._engine_inline.opacity = 1
            if self._engine_error:
                self._engine_inline_label.text = "ENGINE Error"
                self._engine_inline_label.color = Theme.DANGER
            else:
                self._engine_inline_label.text = "ENGINE Starting"
                self._engine_inline_label.color = Theme.WARNING

    def _register_pipeline_callbacks(self, *_):
        self._controller.register_bootstrap_callbacks(on_progress=self._on_model_progress, on_done=self._on_model_ready)
        try:
            event = self._controller.get_bootstrap_state()
            if event.state == BootstrapState.DOWNLOADING:
                self._on_model_progress(event.progress, event.message)
            elif event.state == BootstrapState.READY:
                self._on_model_ready(True, event.message)
            elif event.state == BootstrapState.ERROR:
                self._on_model_ready(False, event.message)
        except Exception:
            pass

    @mainthread
    def _on_model_progress(self, frac: float, text: str):
        pct = int(min(max(frac, 0.0), 0.999) * 100)
        now = time.monotonic()
        if pct == self._last_model_pct and (now - self._last_model_update_at) < 0.7:
            return
        self._last_model_pct = pct
        self._last_model_update_at = now

        self._model_ready = False
        self._engine_error = False
        self._engine_state.text = "[b]ENGINE:[/b] Starting"
        self._engine_state.color = Theme.WARNING
        self._engine_detail.text = f"{text or 'Preparing offline runtime'} ({pct}%)"
        self._refresh_engine_card_height()
        self._set_send_enabled(False)

    @mainthread
    def _on_model_ready(self, success: bool, message: str):
        if success:
            self._model_ready = True
            self._engine_error = False
            self._engine_state.text = "[b]ENGINE:[/b] Ready"
            self._engine_state.color = Theme.SUCCESS
            self._engine_detail.text = "Offline model is ready"
            self._set_send_enabled(True)
            Clock.schedule_once(lambda *_: self._controller.start_service_once(), 0.05)
        else:
            self._model_ready = False
            self._engine_error = True
            self._engine_state.text = "[b]ENGINE:[/b] Error"
            self._engine_state.color = Theme.DANGER
            self._engine_detail.text = message or "Model startup failed"
            self._set_send_enabled(False)
        self._refresh_engine_card_height()

    def _set_send_enabled(self, enabled: bool):
        self._send_btn.disabled = not enabled
        self._send_btn.opacity = 1.0 if enabled else 0.45

    def _refresh_mode_hint(self):
        self._mode_label.text = f"{mode_title(self._selected_mode)}  |  docs: {self._doc_count}"

    def _set_mode(self, mode: str):
        self._selected_mode = CHAT_MODE_DOCUMENT if mode == CHAT_MODE_DOCUMENT else CHAT_MODE_GENERAL
        if self._selected_mode == CHAT_MODE_GENERAL:
            self._btn_general.set_bg(Theme.PRIMARY)
            self._btn_document.set_bg(Theme.SURFACE_ALT)
        else:
            self._btn_general.set_bg(Theme.SURFACE_ALT)
            self._btn_document.set_bg(Theme.PRIMARY)
        self._refresh_document_inventory()

    def _refresh_document_inventory(self):
        try:
            docs = self._controller.list_documents()
        except Exception:
            docs = []
        self._doc_count = len(docs)
        self._refresh_mode_hint()

        show_notice = self._selected_mode == CHAT_MODE_DOCUMENT and self._doc_count == 0
        self._docs_notice.height = self._metrics.control_h if show_notice else 0

    def _go_to_docs(self):
        if callable(self._open_docs_tab):
            self._open_docs_tab()

    def _prefill_prompt(self):
        self._input.text = "What can you help me with offline?"

    def _hide_empty_state(self):
        if hasattr(self, "_empty_state") and self._empty_state.parent is self._msgs:
            self._msgs.remove_widget(self._empty_state)

    def _track_message_widget(self, widget: Widget):
        self._message_widgets.append(widget)
        while len(self._message_widgets) > self._max_message_widgets:
            stale = self._message_widgets.pop(0)
            if stale is self._current_row:
                self._current_row = None
            if stale.parent is self._msgs:
                self._msgs.remove_widget(stale)

    def _is_near_bottom(self) -> bool:
        return self._scroll.scroll_y <= 0.08

    def _show_typing(self):
        self._hide_empty_state()
        self._typing = TypingIndicator(self._get_metrics)
        self._msgs.add_widget(self._typing)
        self._scroll_to_bottom()

    def _hide_typing(self):
        if self._typing:
            self._typing.stop()
            self._msgs.remove_widget(self._typing)
            self._typing = None

    def _add_msg(self, text: str, role: str = "assistant") -> RoleBubble:
        self._hide_empty_state()
        row = RoleBubble(text=text, role=role, metrics_getter=self._get_metrics)
        self._msgs.add_widget(row)
        self._track_message_widget(row)
        Clock.schedule_once(lambda *_: self._scroll_to_bottom(force=True), 0)
        return row

    def _scroll_to_bottom(self, *_, force: bool = False):
        if force or self._is_near_bottom():
            self._scroll.scroll_y = 0

    def _on_attach(self, *_):
        if self._picker_open:
            return
        self._picker_open = True
        import os

        if os.environ.get("ANDROID_PRIVATE"):
            self._request_storage_permissions()
            self._android_pick_file()
        else:
            self._desktop_pick_file()

    def _request_storage_permissions(self):
        import os

        if not os.environ.get("ANDROID_PRIVATE") or self._perm_requested:
            return
        self._perm_requested = True
        try:
            from android.permissions import Permission, request_permissions  # type: ignore

            request_permissions(
                [
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_MEDIA_IMAGES,
                    Permission.READ_MEDIA_VIDEO,
                ]
            )
        except Exception:
            pass

    def _android_pick_file(self):
        try:
            from android.activity import bind as activity_bind  # type: ignore
            from jnius import autoclass  # type: ignore

            activity_bind(on_activity_result=self._on_activity_result)
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")

            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("*/*")
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            try:
                ArrayList = autoclass("java.util.ArrayList")
                mimes = ArrayList()
                mimes.add("application/pdf")
                mimes.add("text/plain")
                intent.putExtra("android.intent.extra.MIME_TYPES", mimes.toArray())
            except Exception:
                pass

            PythonActivity.mActivity.startActivityForResult(intent, self._PICK_REQ)
        except Exception as exc:
            self._picker_open = False
            self._add_msg(f"[color=ff7777]Could not open picker:[/color] {escape_markup(str(exc))}")

    def _on_activity_result(self, request_code, result_code, data):
        try:
            from android.activity import unbind as activity_unbind  # type: ignore

            activity_unbind(on_activity_result=self._on_activity_result)
        except Exception:
            pass

        self._picker_open = False
        if request_code != self._PICK_REQ or result_code != -1 or data is None:
            return

        try:
            uri = data.getData()
            if uri is not None:
                Clock.schedule_once(lambda *_: self._process_picked_uri(uri.toString()), 0)
        except Exception as exc:
            self._add_msg(f"[color=ff7777]Could not read URI:[/color] {escape_markup(str(exc))}")

    @mainthread
    def _process_picked_uri(self, uri_str: str):
        try:
            from app.rag.chunker import resolve_uri

            self._stage_attachment(resolve_uri(uri_str))
        except Exception as exc:
            self._add_msg(f"[color=ff7777]Could not open file:[/color] {escape_markup(str(exc))}")

    def _desktop_pick_file(self):
        try:
            from plyer import filechooser

            filechooser.open_file(
                on_selection=self._on_file_chosen,
                filters=[["Documents", "*.pdf", "*.txt", "*.PDF", "*.TXT"]],
                title="Choose document",
                multiple=False,
            )
        except Exception:
            self._picker_open = False
            self._add_msg("File picker unavailable. Paste a full file path and send.")

    @mainthread
    def _on_file_chosen(self, selection):
        self._picker_open = False
        if not selection or selection[0] is None:
            return
        try:
            from app.rag.chunker import resolve_uri

            self._stage_attachment(resolve_uri(selection[0]))
        except Exception as exc:
            self._add_msg(f"[color=ff7777]Could not open file:[/color] {escape_markup(str(exc))}")

    def _stage_attachment(self, path: str):
        self._pending_attach = path
        self._attach_strip.clear_widgets()
        self._attach_strip.add_widget(AttachmentPreviewCard(path, on_remove=self._clear_attachment, metrics_getter=self._get_metrics))
        self._apply_responsive_layout()

    @mainthread
    def _clear_attachment(self):
        self._pending_attach = None
        self._attach_strip.clear_widgets()
        self._apply_responsive_layout()

    def _maybe_stage_plain_path(self, text: str) -> bool:
        s = text.strip()
        if not s:
            return False
        is_path = (s.startswith("/") or (len(s) > 2 and s[1] == ":")) and Path(s).is_file()
        if is_path:
            self._stage_attachment(s)
            return True
        return False

    def _on_send(self, *_):
        q = self._input.text.strip()
        attach = self._pending_attach

        if not q and not attach:
            return

        if is_quit_rag_alias(q):
            self._input.text = ""
            self._set_mode(CHAT_MODE_GENERAL)
            self._add_msg(escape_markup(q), role="user")
            self._add_msg("Switched to General Chat mode.", role="assistant")
            return

        if attach:
            self._input.text = ""
            self._clear_attachment()
            file_name = Path(attach).name
            bubble = f"[b]{escape_markup(file_name)}[/b]"
            if q:
                bubble += f"\n{escape_markup(q)}"
            self._add_msg(bubble, role="user")
            self._start_ingest(attach, file_name)
            return

        if self._maybe_stage_plain_path(q):
            self._input.text = ""
            return

        if self._streaming_active:
            self._add_msg("Please wait for the current response to finish.")
            return

        if not self._model_ready:
            self._add_msg("AI engine is still starting. Please wait for ready state.")
            return

        self._refresh_document_inventory()
        mode, can_send, reason = resolve_send_mode(self._selected_mode, self._doc_count > 0)
        if not can_send:
            self._add_msg(reason)
            return

        self._input.text = ""
        self._pending_q = q
        self._streaming_active = True
        self._active_response_mode = mode
        self._add_msg(escape_markup(q), role="user")
        self._show_typing()

        self._token_buf.clear()
        if self._token_flush_ev is not None:
            Clock.unschedule(self._token_flush_ev)
            self._token_flush_ev = None

        if mode == CHAT_MODE_DOCUMENT:
            self._active_task_id = self._controller.ask(q, stream_cb=self._on_token, on_done=self._on_done)
        else:
            self._active_task_id = self._controller.chat_direct(
                q,
                history=list(self._history),
                summary=self._history_summary,
                stream_cb=self._on_token,
                on_done=self._on_done,
            )

    def _start_ingest(self, path: str, file_name: str):
        self._hide_empty_state()
        card = IngestStatusCard(file_name, metrics_getter=self._get_metrics)
        self._msgs.add_widget(card)
        self._track_message_widget(card)
        card.set_stage("queued", "Waiting to start")
        self._scroll_to_bottom(force=True)

        def _done(ok: bool, msg: str):
            self._ingest_done(card, ok, msg)

        card.set_stage("ingesting", "Parsing and indexing")
        self._controller.ingest_document(path, on_done=_done)

    @mainthread
    def _ingest_done(self, card: IngestStatusCard, ok: bool, msg: str):
        card.set_done(ok, msg)
        self._refresh_document_inventory()
        if ok:
            self._add_msg("Document indexed. Docs mode is now ready.")
        else:
            self._add_msg(f"[color=ff7777]Document ingest failed:[/color] {escape_markup(msg)}")
        self._scroll_to_bottom()

    def _on_token(self, token: str):
        self._token_buf.append(token)
        if len(self._token_buf) >= 50:
            if self._token_flush_ev is not None:
                Clock.unschedule(self._token_flush_ev)
                self._token_flush_ev = None
            Clock.schedule_once(self._flush_tokens, 0)
            return
        if self._token_flush_ev is None:
            self._token_flush_ev = Clock.schedule_once(self._flush_tokens, 0.35)

    @mainthread
    def _flush_tokens(self, *_):
        self._token_flush_ev = None
        if not self._token_buf:
            return
        batch = "".join(self._token_buf)
        self._token_buf.clear()

        if self._typing:
            self._hide_typing()
            self._current_row = self._add_msg("", role="assistant")

        if self._current_row:
            self._current_row.append(batch)
            self._scroll_to_bottom()

    @mainthread
    def _on_done(self, success: bool, message: str):
        if self._token_buf:
            batch = "".join(self._token_buf)
            self._token_buf.clear()
            if self._typing:
                self._hide_typing()
                self._current_row = self._add_msg("", role="assistant")
            if self._current_row:
                self._current_row.append(batch)

        self._hide_typing()

        if success:
            if self._active_response_mode == CHAT_MODE_GENERAL and self._pending_q and self._current_row:
                import re

                raw_answer = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", self._current_row._label.text).strip()
                self._history.append((self._pending_q, raw_answer))
                if len(self._history) > 6:
                    older = self._history[:-3]
                    self._history = self._history[-3:]
                    for old_q, old_a in older:
                        first_sentence = old_a.split(".")[0].strip()[:120]
                        if first_sentence:
                            self._history_summary += f"- {old_q}: {first_sentence}.\n"
        else:
            if self._current_row:
                self._current_row._label.text = f"[color=ff7777]{escape_markup(message)}[/color]"
            else:
                self._add_msg(f"[color=ff7777]{escape_markup(message)}[/color]")

        self._streaming_active = False
        self._pending_q = ""
        self._active_response_mode = CHAT_MODE_GENERAL
        self._current_row = None
        self._active_task_id = None
        self._scroll_to_bottom()
