"""Responsive Documents screen with compact and medium layouts."""
from __future__ import annotations

from pathlib import Path

from app.ui.chat.controller import ChatController
from app.ui.responsive import current_metrics, is_split_class
from app.ui.theme import Theme, TypeScale
from app.ui.widgets import PillButton, SurfaceCard, bind_label_size, paint_background

from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput


class DocumentRow(SurfaceCard):
    def __init__(self, doc: dict, on_delete, metrics_getter, **kwargs):
        self._metrics_getter = metrics_getter
        super().__init__(orientation="horizontal", size_hint=(1, None), color=Theme.SURFACE, **kwargs)
        self.doc = doc

        self._details = BoxLayout(orientation="vertical", spacing=dp(2))
        self._name = Label(
            text=f"[b]{doc['name']}[/b]",
            markup=True,
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._name)

        self._meta = Label(
            text=f"{doc['num_chunks']} chunks  |  Added {doc['added_at'][:16]}",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._meta)

        self._details.add_widget(self._name)
        self._details.add_widget(self._meta)
        self.add_widget(self._details)

        self._delete_btn = PillButton(
            text="Delete",
            bg_color=Theme.DANGER,
            size_hint=(None, None),
            font_size=TypeScale.XS,
            radius=dp(10),
        )
        self._delete_btn.bind(on_release=lambda *_: on_delete(doc["id"]))
        self.add_widget(self._delete_btn)
        self.apply_metrics()

    def apply_metrics(self):
        m = self._metrics_getter()
        self.height = m.control_h + m.gap_md + m.gap_sm
        self.padding = [m.gap_md, m.gap_sm, m.gap_md, m.gap_sm]
        self.spacing = m.gap_sm
        self._name.height = dp(22)
        self._meta.height = dp(18)
        self._delete_btn.size = (dp(76), m.control_h)


class DocsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._controller = ChatController()
        self._metrics = current_metrics()
        self._root = None
        self._list = None
        self._summary_meta = None
        self._status = None
        self._manual_path = None
        self._build_ui()
        Window.bind(size=self._on_window_size)

    def on_pre_enter(self, *_):
        self._refresh_list()

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
        self._refresh_list()

    def _build_ui(self):
        m = self._metrics
        root = BoxLayout(orientation="horizontal" if is_split_class(m.size_class) else "vertical")
        paint_background(root, Theme.BG)
        root.padding = [m.screen_pad_h, m.screen_pad_v, m.screen_pad_h, m.screen_pad_v]
        root.spacing = m.gap_md
        self._root = root

        content_col = BoxLayout(orientation="vertical", spacing=m.gap_sm, size_hint=(m.split_primary_ratio, 1) if is_split_class(m.size_class) else (1, 1))

        self._summary = SurfaceCard(
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=(1, None),
            padding=[m.gap_md, m.gap_sm, m.gap_md, m.gap_sm],
            spacing=dp(2),
        )
        summary_title = Label(
            text="[b]Documents Library[/b]",
            markup=True,
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(22),
            font_size=TypeScale.MD,
        )
        bind_label_size(summary_title)
        self._summary_meta = Label(
            text="No documents indexed yet.",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(18),
            font_size=TypeScale.XS,
        )
        bind_label_size(self._summary_meta)
        self._summary.add_widget(summary_title)
        self._summary.add_widget(self._summary_meta)
        content_col.add_widget(self._summary)

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
        content_col.add_widget(self._status)

        self._scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._list = BoxLayout(orientation="vertical", size_hint=(1, None), spacing=m.gap_sm, padding=[0, m.gap_sm, 0, m.gap_sm])
        self._list.bind(minimum_height=self._list.setter("height"))
        self._scroll.add_widget(self._list)
        content_col.add_widget(self._scroll)

        root.add_widget(content_col)

        self._actions = self._build_actions_panel(
            size_hint=(1 - m.split_primary_ratio, 1) if is_split_class(m.size_class) else (1, None),
        )
        root.add_widget(self._actions)

        self.add_widget(root)
        self._apply_layout_metrics()

    def _build_actions_panel(self, size_hint):
        m = self._metrics
        action_card = SurfaceCard(
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=size_hint,
            padding=[m.gap_sm, m.gap_sm, m.gap_sm, m.gap_sm],
            spacing=m.gap_sm,
        )
        browse_btn = PillButton(
            text="Browse PDF / TXT",
            bg_color=Theme.PRIMARY,
            size_hint=(1, None),
            height=m.control_h,
            font_size=TypeScale.SM,
            radius=m.control_radius,
        )
        browse_btn.bind(on_release=self._on_browse)
        action_card.add_widget(browse_btn)

        manual_row = BoxLayout(orientation="horizontal", spacing=m.gap_sm, size_hint=(1, None), height=m.control_h)
        shell = SurfaceCard(
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(1, 1),
            padding=[m.gap_sm, m.gap_xs, m.gap_sm, m.gap_xs],
        )
        self._manual_path = TextInput(
            hint_text="Paste full file path...",
            multiline=False,
            foreground_color=Theme.TEXT,
            hint_text_color=Theme.TEXT_MUTED,
            background_color=(0, 0, 0, 0),
            cursor_color=Theme.TEXT,
            font_size=TypeScale.SM,
        )
        self._manual_path.bind(on_text_validate=self._on_manual_add)
        shell.add_widget(self._manual_path)

        add_btn = PillButton(
            text="Add",
            bg_color=Theme.PRIMARY_DARK,
            size_hint=(None, None),
            size=(dp(64), m.control_h),
            font_size=TypeScale.SM,
            radius=m.control_radius,
        )
        add_btn.bind(on_release=self._on_manual_add)

        manual_row.add_widget(shell)
        manual_row.add_widget(add_btn)
        action_card.add_widget(manual_row)
        return action_card

    def _apply_layout_metrics(self):
        m = self._metrics
        self._root.padding = [m.screen_pad_h, m.screen_pad_v, m.screen_pad_h, m.screen_pad_v]
        self._root.spacing = m.gap_sm
        self._summary.height = m.docs_summary_h
        if is_split_class(m.size_class):
            self._actions.size_hint = (1 - m.split_primary_ratio, 1)
            self._actions.height = 0
        else:
            self._actions.size_hint = (1, None)
            self._actions.height = (m.control_h * 2) + (m.gap_sm * 3)

    def _set_status(self, text: str, tone="muted"):
        color = Theme.TEXT_MUTED
        if tone == "success":
            color = Theme.SUCCESS
        elif tone == "danger":
            color = Theme.DANGER
        elif tone == "warning":
            color = Theme.WARNING
        self._status.color = color
        self._status.text = text

    def _refresh_list(self):
        try:
            docs = self._controller.list_documents()
        except Exception:
            docs = []

        self._list.clear_widgets()
        total_chunks = sum(int(d.get("num_chunks", 0)) for d in docs)
        self._summary_meta.text = (
            f"{len(docs)} indexed documents  |  {total_chunks} chunks" if docs else "No documents indexed yet."
        )

        if not docs:
            m = self._metrics
            empty = SurfaceCard(
                color=Theme.SURFACE_ALT,
                orientation="vertical",
                size_hint=(1, None),
                height=self._metrics.docs_summary_h,
                padding=[m.gap_md, m.gap_sm, m.gap_md, m.gap_sm],
            )
            lbl = Label(
                text="Upload a PDF or TXT to power Docs mode.",
                color=Theme.TEXT_MUTED,
                halign="left",
                valign="middle",
                font_size=TypeScale.SM,
            )
            bind_label_size(lbl)
            empty.add_widget(lbl)
            self._list.add_widget(empty)
            return

        for doc in docs:
            self._list.add_widget(DocumentRow(doc, on_delete=self._on_delete, metrics_getter=lambda: self._metrics))

    def _on_browse(self, *_):
        try:
            from plyer import filechooser

            filechooser.open_file(
                on_selection=self._on_file_selected,
                filters=[["Documents", "*.pdf", "*.txt", "*.PDF", "*.TXT"]],
                title="Choose a document",
                multiple=False,
            )
        except Exception:
            self._set_status("File picker unavailable. Use manual path input.", tone="warning")

    @mainthread
    def _on_file_selected(self, selection):
        if not selection or selection[0] is None:
            return
        try:
            from app.rag.chunker import resolve_uri

            self._ingest(resolve_uri(selection[0]))
        except Exception as exc:
            self._set_status(f"Could not open file: {exc}", tone="danger")

    def _on_manual_add(self, *_):
        path = self._manual_path.text.strip()
        if not path:
            return
        self._manual_path.text = ""
        self._ingest(path)

    def _ingest(self, path: str):
        name = Path(path).name or path
        self._set_status(f"Indexing {name}...", tone="warning")
        self._controller.ingest_document(path, on_done=self._on_ingest_done)

    @mainthread
    def _on_ingest_done(self, success: bool, message: str):
        self._set_status(message, tone="success" if success else "danger")
        self._refresh_list()

    def _on_delete(self, doc_id: int):
        self._controller.delete_document(doc_id)
        self._set_status("Document removed.", tone="warning")
        self._refresh_list()
