"""Premium chat screen for explicit General Chat and Document Q&A modes."""
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
from app.ui.theme import MIN_TOUCH, Radius, Space, Theme, TypeScale
from app.ui.widgets import PillButton, SurfaceCard, bind_label_size, paint_background

from kivy.clock import Clock, mainthread
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

    def __init__(self, text: str, role: str = "assistant", **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            padding=[Space.SM, Space.XS, Space.SM, Space.XS],
            spacing=Space.XS,
            **kwargs,
        )
        self.role = role
        self._label = Label(
            text=text,
            markup=True,
            size_hint=(None, None),
            text_size=(dp(220), None),
            halign="left",
            valign="middle",
            color=Theme.TEXT,
            font_size=TypeScale.MD,
        )
        self._label.bind(texture_size=self._on_texture)
        self.bind(width=self._on_width)
        self._build()

    def _build(self) -> None:
        bubble_color = Theme.USER_BUBBLE if self.role == "user" else Theme.ASSISTANT_BUBBLE
        bubble = SurfaceCard(
            radius=Radius.LG,
            color=bubble_color,
            size_hint=(None, None),
            padding=[Space.MD, Space.SM],
            orientation="vertical",
        )
        bubble.add_widget(self._label)
        self._bubble = bubble

        if self.role == "user":
            self.add_widget(Widget(size_hint_x=1))
            self.add_widget(self._role_chip("YOU"))
            self.add_widget(bubble)
        else:
            self.add_widget(bubble)
            self.add_widget(self._role_chip("AI"))
            self.add_widget(Widget(size_hint_x=1))

    def _role_chip(self, text: str) -> Widget:
        holder = AnchorLayout(size_hint=(None, None), size=(dp(36), dp(28)))
        chip = SurfaceCard(
            radius=Radius.SM,
            color=Theme.SURFACE_ALT,
            size_hint=(None, None),
            size=(dp(34), dp(24)),
            padding=[0, 0],
        )
        lbl = Label(text=text, color=Theme.TEXT_MUTED, font_size=TypeScale.XS, bold=True)
        bind_label_size(lbl)
        chip.add_widget(lbl)
        holder.add_widget(chip)
        return holder

    def _on_texture(self, _, texture_size) -> None:
        if not hasattr(self, "_bubble"):
            return
        width = min(texture_size[0] + dp(8), self.width * 0.76)
        self._label.size = (width, texture_size[1] + dp(4))
        self._bubble.size = (width + Space.LG * 2, self._label.height + Space.SM * 2)
        self.height = self._bubble.height + Space.SM

    def _on_width(self, *_):
        max_width = max(dp(160), self.width * 0.72)
        self._label.text_size = (max_width, None)

    def append(self, token: str) -> None:
        self._label.text += escape_markup(token)


class IngestStatusCard(SurfaceCard):
    """Honest ingest stage card; does not imply granular progress."""

    _COLORS = {
        "queued": Theme.TEXT_MUTED,
        "ingesting": Theme.WARNING,
        "indexed": Theme.SUCCESS,
        "failed": Theme.DANGER,
    }

    def __init__(self, filename: str, **kwargs):
        super().__init__(
            radius=Radius.MD,
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=(1, None),
            padding=[Space.MD, Space.SM],
            spacing=Space.XS,
            **kwargs,
        )
        self._file = escape_markup(filename)
        self._title = Label(
            text=f"[b]Document:[/b] {self._file}",
            markup=True,
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(24),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._title)
        self._stage = Label(
            text="Queued",
            color=self._COLORS["queued"],
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(22),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._stage)
        self.add_widget(self._title)
        self.add_widget(self._stage)
        self.height = dp(78)

    def set_stage(self, stage: str, detail: str = "") -> None:
        label = stage.capitalize()
        if detail:
            label = f"{label}: {escape_markup(detail)}"
        self._stage.color = self._COLORS.get(stage, Theme.TEXT_MUTED)
        self._stage.text = label

    def set_done(self, success: bool, message: str) -> None:
        if success:
            self.set_stage("indexed", message)
        else:
            self.set_stage("failed", message)


class AttachmentPreviewCard(SurfaceCard):
    def __init__(self, filepath: str, on_remove, **kwargs):
        super().__init__(
            radius=Radius.MD,
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(None, None),
            size=(dp(250), dp(66)),
            padding=[Space.SM, Space.SM],
            spacing=Space.SM,
            **kwargs,
        )

        name = Path(filepath).name
        ext = Path(filepath).suffix.upper().replace(".", "") or "FILE"
        title = name if len(name) <= 28 else f"{name[:25]}..."

        icon = SurfaceCard(
            radius=Radius.SM,
            color=Theme.PRIMARY_DARK,
            size_hint=(None, None),
            size=(dp(42), dp(42)),
        )
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
            height=dp(22),
        )
        bind_label_size(name_lbl)
        type_lbl = Label(
            text=f"{ext} attachment",
            color=Theme.TEXT_MUTED,
            font_size=TypeScale.XS,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
        )
        bind_label_size(type_lbl)
        info.add_widget(name_lbl)
        info.add_widget(type_lbl)
        self.add_widget(info)

        remove_btn = Button(
            text="X",
            size_hint=(None, None),
            size=(dp(24), dp(24)),
            background_normal="",
            background_color=(0, 0, 0, 0),
            color=Theme.TEXT_MUTED,
            font_size=TypeScale.SM,
        )
        remove_btn.bind(on_release=lambda *_: on_remove())
        self.add_widget(remove_btn)


class TypingIndicator(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            spacing=dp(5),
            size_hint=(1, None),
            height=dp(28),
            padding=[Space.MD, 0],
            **kwargs,
        )
        self._dots: list[Label] = []
        self._tick = 0
        for _ in range(3):
            dot = Label(text=".", color=Theme.TEXT_MUTED, font_size=TypeScale.MD, size_hint=(None, 1), width=dp(12))
            self._dots.append(dot)
            self.add_widget(dot)
        Clock.schedule_interval(self._pulse, 0.36)

    def _pulse(self, *_):
        for index, dot in enumerate(self._dots):
            dot.color = Theme.TEXT if index == self._tick % 3 else Theme.TEXT_MUTED
        self._tick += 1

    def stop(self) -> None:
        Clock.unschedule(self._pulse)


class ChatScreen(Screen):
    """Single chat screen with explicit interaction mode and state banners."""

    _PICK_REQ = 0x4F52

    def __init__(self, open_docs_tab=None, **kwargs):
        super().__init__(**kwargs)
        self._open_docs_tab = open_docs_tab
        self._controller = ChatController()

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

        self._last_model_stage = ""
        self._last_model_pct = -1
        self._last_model_update_at = 0.0

        self._build_ui()

    def on_pre_enter(self, *_):
        self._refresh_document_inventory()

    def _build_ui(self) -> None:
        root = BoxLayout(orientation="vertical", spacing=Space.SM, padding=[Space.SM, Space.SM, Space.SM, Space.SM])
        paint_background(root, Theme.BG)

        self._engine_card = SurfaceCard(
            radius=Radius.LG,
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=(1, None),
            height=dp(102),
            padding=[Space.MD, Space.SM],
            spacing=dp(2),
        )
        self._engine_state = Label(
            text="[b]ENGINE:[/b] Starting",
            markup=True,
            color=Theme.WARNING,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(22),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._engine_state)
        self._engine_title = Label(
            text="Bootstrapping offline AI model",
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(24),
            font_size=TypeScale.LG,
            bold=True,
        )
        bind_label_size(self._engine_title)
        self._engine_detail = Label(
            text="Preparing assets and service.",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(22),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._engine_detail)
        self._engine_card.add_widget(self._engine_state)
        self._engine_card.add_widget(self._engine_title)
        self._engine_card.add_widget(self._engine_detail)
        root.add_widget(self._engine_card)

        mode_row = SurfaceCard(
            radius=Radius.MD,
            color=Theme.SURFACE,
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(56),
            spacing=Space.SM,
            padding=[Space.SM, Space.XS],
        )
        self._btn_general = PillButton(
            text="General Chat",
            bg_color=Theme.PRIMARY,
            size_hint=(0.5, None),
            height=MIN_TOUCH,
            font_size=TypeScale.SM,
        )
        self._btn_general.bind(on_release=lambda *_: self._set_mode(CHAT_MODE_GENERAL))

        self._btn_document = PillButton(
            text="Document Q&A",
            bg_color=Theme.SURFACE_ALT,
            size_hint=(0.5, None),
            height=MIN_TOUCH,
            font_size=TypeScale.SM,
        )
        self._btn_document.bind(on_release=lambda *_: self._set_mode(CHAT_MODE_DOCUMENT))

        mode_row.add_widget(self._btn_general)
        mode_row.add_widget(self._btn_document)
        root.add_widget(mode_row)

        self._mode_caption = Label(
            text="",
            color=Theme.TEXT_MUTED,
            font_size=TypeScale.XS,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
        )
        bind_label_size(self._mode_caption)
        root.add_widget(self._mode_caption)

        self._docs_notice = SurfaceCard(
            radius=Radius.MD,
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(1, None),
            height=0,
            spacing=Space.SM,
            padding=[Space.SM, Space.XS],
        )
        notice_lbl = Label(
            text="Document mode is empty. Add a file from Documents tab.",
            color=Theme.TEXT_MUTED,
            font_size=TypeScale.XS,
            halign="left",
            valign="middle",
        )
        bind_label_size(notice_lbl)
        open_docs = PillButton(
            text="Open Documents",
            bg_color=Theme.PRIMARY_DARK,
            size_hint=(None, None),
            size=(dp(132), MIN_TOUCH),
            font_size=TypeScale.XS,
        )
        open_docs.bind(on_release=lambda *_: self._go_to_docs())
        self._docs_notice.add_widget(notice_lbl)
        self._docs_notice.add_widget(open_docs)
        root.add_widget(self._docs_notice)

        self._scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._msgs = BoxLayout(orientation="vertical", size_hint=(1, None), spacing=dp(2))
        self._msgs.bind(minimum_height=self._msgs.setter("height"))
        self._msgs.bind(height=lambda *_: self._scroll_to_bottom())
        self._scroll.add_widget(self._msgs)
        paint_background(self._scroll, Theme.BG)
        root.add_widget(self._scroll)

        self._add_msg(
            "[b]Welcome to O-RAG.[/b]\nChoose [b]General Chat[/b] for standard conversation or [b]Document Q&A[/b] for grounded answers.",
            role="assistant",
        )

        input_zone = SurfaceCard(
            radius=Radius.MD,
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=(1, None),
            height=dp(86),
            spacing=0,
        )

        self._attach_strip = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=0,
            padding=[Space.SM, Space.XS, Space.SM, 0],
        )
        input_zone.add_widget(self._attach_strip)

        input_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(78),
            padding=[Space.SM, Space.SM, Space.SM, Space.SM],
            spacing=Space.SM,
        )

        attach_btn = PillButton(
            text="+",
            bg_color=Theme.SURFACE_ALT,
            size_hint=(None, None),
            size=(MIN_TOUCH, MIN_TOUCH),
            font_size=TypeScale.XL,
        )
        attach_btn.bind(on_release=self._on_attach)
        input_row.add_widget(attach_btn)

        input_shell = SurfaceCard(
            radius=Radius.PILL,
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(1, None),
            height=MIN_TOUCH,
            padding=[Space.MD, Space.XS],
            spacing=Space.SM,
        )

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
        input_shell.add_widget(self._input)

        self._send_btn = PillButton(
            text=">",
            bg_color=Theme.PRIMARY,
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            font_size=TypeScale.LG,
        )
        self._send_btn.bind(on_release=self._on_send)
        input_shell.add_widget(self._send_btn)
        input_row.add_widget(input_shell)

        input_zone.add_widget(input_row)
        root.add_widget(input_zone)

        self.add_widget(root)

        self._set_send_enabled(False)
        self._set_mode(CHAT_MODE_GENERAL)
        Clock.schedule_once(self._register_pipeline_callbacks, 0)

    def _register_pipeline_callbacks(self, *_):
        self._controller.register_bootstrap_callbacks(
            on_progress=self._on_model_progress,
            on_done=self._on_model_ready,
        )
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

        txt = text.lower()
        if "download" in txt or "hugging" in txt:
            stage = "Downloading"
        elif "loading" in txt or "start" in txt or "engine" in txt:
            stage = "Starting"
        else:
            stage = "Preparing"

        self._engine_state.text = f"[b]ENGINE:[/b] {stage}"
        self._engine_state.color = Theme.WARNING
        self._engine_title.text = f"Bootstrapping offline AI ({pct}%)"
        self._engine_detail.text = text or "Preparing local runtime"

    @mainthread
    def _on_model_ready(self, success: bool, message: str):
        if success:
            self._model_ready = True
            self._set_send_enabled(True)
            self._engine_state.text = "[b]ENGINE:[/b] Ready"
            self._engine_state.color = Theme.SUCCESS
            self._engine_title.text = "Offline model is ready"
            self._engine_detail.text = "You can chat now, or ask from indexed documents."
            Clock.schedule_once(lambda *_: self._controller.start_service_once(), 0.05)
        else:
            self._model_ready = False
            self._set_send_enabled(False)
            self._engine_state.text = "[b]ENGINE:[/b] Error"
            self._engine_state.color = Theme.DANGER
            self._engine_title.text = "Model startup failed"
            self._engine_detail.text = message or "Check first-run download connectivity and retry."

    def _set_send_enabled(self, enabled: bool) -> None:
        self._send_btn.disabled = not enabled
        self._send_btn.opacity = 1.0 if enabled else 0.45

    def _set_mode(self, mode: str) -> None:
        self._selected_mode = CHAT_MODE_DOCUMENT if mode == CHAT_MODE_DOCUMENT else CHAT_MODE_GENERAL

        if self._selected_mode == CHAT_MODE_GENERAL:
            self._btn_general.set_bg(Theme.PRIMARY)
            self._btn_document.set_bg(Theme.SURFACE_ALT)
        else:
            self._btn_general.set_bg(Theme.SURFACE_ALT)
            self._btn_document.set_bg(Theme.PRIMARY)

        self._refresh_document_inventory()

    def _refresh_document_inventory(self) -> None:
        docs = self._safe_list_documents()
        self._doc_count = len(docs)

        mode_name = mode_title(self._selected_mode)
        self._mode_caption.text = f"Mode: {mode_name}  |  Indexed docs: {self._doc_count}"

        if self._selected_mode == CHAT_MODE_DOCUMENT and self._doc_count == 0:
            self._docs_notice.height = dp(58)
        else:
            self._docs_notice.height = 0

    def _safe_list_documents(self) -> list[dict]:
        try:
            return self._controller.list_documents()
        except Exception:
            return []

    def _go_to_docs(self):
        if callable(self._open_docs_tab):
            self._open_docs_tab()

    def _show_typing(self):
        self._typing = TypingIndicator()
        self._msgs.add_widget(self._typing)
        self._scroll_to_bottom()

    def _hide_typing(self):
        if self._typing:
            self._typing.stop()
            self._msgs.remove_widget(self._typing)
            self._typing = None

    def _add_msg(self, text: str, role: str = "assistant") -> RoleBubble:
        row = RoleBubble(text=text, role=role)
        self._msgs.add_widget(row)
        Clock.schedule_once(lambda *_: self._scroll_to_bottom(), 0)
        return row

    def _scroll_to_bottom(self, *_):
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
        self._attach_strip.add_widget(AttachmentPreviewCard(path, on_remove=self._clear_attachment))
        self._attach_strip.height = dp(78)
        self._attach_strip.parent.height = dp(158)

    @mainthread
    def _clear_attachment(self):
        self._pending_attach = None
        self._attach_strip.clear_widgets()
        self._attach_strip.height = 0
        self._attach_strip.parent.height = dp(86)

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
            self._add_msg("AI engine is still starting. Please wait for the ready state.")
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
            self._controller.ask(q, stream_cb=self._on_token, on_done=self._on_done)
        else:
            self._controller.chat_direct(
                q,
                history=list(self._history),
                summary=self._history_summary,
                stream_cb=self._on_token,
                on_done=self._on_done,
            )

    def _start_ingest(self, path: str, file_name: str):
        card = IngestStatusCard(file_name)
        self._msgs.add_widget(card)
        card.set_stage("queued", "Waiting to start")
        self._scroll_to_bottom()

        def _done(ok: bool, msg: str):
            self._ingest_done(card, ok, msg)

        card.set_stage("ingesting", "Parsing and indexing")
        self._controller.ingest_document(path, on_done=_done)

    @mainthread
    def _ingest_done(self, card: IngestStatusCard, ok: bool, msg: str):
        card.set_done(ok, msg)
        self._refresh_document_inventory()
        if ok:
            self._add_msg("Document indexed. Switch to Document Q&A mode to ground answers.")
        else:
            self._add_msg(f"[color=ff7777]Document ingest failed:[/color] {escape_markup(msg)}")
        self._scroll_to_bottom()

    def _on_token(self, token: str):
        self._token_buf.append(token)
        if self._token_flush_ev is None:
            self._token_flush_ev = Clock.schedule_once(self._flush_tokens, 0.12)

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
        self._scroll_to_bottom()





