"""Documents screen with list, ingest, and deletion controls."""
from __future__ import annotations

from pathlib import Path

from app.ui.chat.controller import ChatController
from app.ui.theme import MIN_TOUCH, Radius, Space, Theme, TypeScale
from app.ui.widgets import PillButton, SurfaceCard, bind_label_size, paint_background

from kivy.clock import mainthread
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput


class DocumentRow(SurfaceCard):
    def __init__(self, doc: dict, on_delete, **kwargs):
        super().__init__(
            radius=Radius.MD,
            color=Theme.SURFACE,
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(70),
            padding=[Space.MD, Space.SM],
            spacing=Space.SM,
            **kwargs,
        )
        self.doc = doc

        details = BoxLayout(orientation="vertical", spacing=dp(2))
        name = Label(
            text=f"[b]{doc['name']}[/b]",
            markup=True,
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(24),
            font_size=TypeScale.SM,
        )
        bind_label_size(name)

        meta = Label(
            text=f"{doc['num_chunks']} chunks  |  Added {doc['added_at'][:16]}",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(20),
            font_size=TypeScale.XS,
        )
        bind_label_size(meta)

        details.add_widget(name)
        details.add_widget(meta)
        self.add_widget(details)

        delete_btn = PillButton(
            text="Delete",
            bg_color=Theme.DANGER,
            size_hint=(None, None),
            size=(dp(82), MIN_TOUCH),
            font_size=TypeScale.XS,
        )
        delete_btn.bind(on_release=lambda *_: on_delete(doc["id"]))
        self.add_widget(delete_btn)


class DocsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._controller = ChatController()
        self._build_ui()

    def on_pre_enter(self, *_):
        self._refresh_list()

    def _build_ui(self):
        root = BoxLayout(orientation="vertical", spacing=Space.SM, padding=[Space.SM, Space.SM, Space.SM, Space.SM])
        paint_background(root, Theme.BG)

        summary = SurfaceCard(
            radius=Radius.LG,
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=(1, None),
            height=dp(88),
            padding=[Space.MD, Space.SM],
            spacing=dp(2),
        )
        self._summary_title = Label(
            text="[b]Documents Library[/b]",
            markup=True,
            color=Theme.TEXT,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(24),
            font_size=TypeScale.LG,
        )
        bind_label_size(self._summary_title)
        self._summary_meta = Label(
            text="No documents indexed yet.",
            color=Theme.TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(22),
            font_size=TypeScale.SM,
        )
        bind_label_size(self._summary_meta)
        summary.add_widget(self._summary_title)
        summary.add_widget(self._summary_meta)
        root.add_widget(summary)

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
        root.add_widget(self._status)

        self._scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._list = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            spacing=Space.SM,
            padding=[0, Space.XS, 0, Space.XS],
        )
        self._list.bind(minimum_height=self._list.setter("height"))
        self._scroll.add_widget(self._list)
        root.add_widget(self._scroll)

        action_card = SurfaceCard(
            radius=Radius.LG,
            color=Theme.SURFACE,
            orientation="vertical",
            size_hint=(1, None),
            height=dp(142),
            padding=[Space.SM, Space.SM],
            spacing=Space.SM,
        )
        browse_btn = PillButton(
            text="Browse PDF / TXT",
            bg_color=Theme.PRIMARY,
            size_hint=(1, None),
            height=MIN_TOUCH,
            font_size=TypeScale.SM,
        )
        browse_btn.bind(on_release=self._on_browse)
        action_card.add_widget(browse_btn)

        manual = BoxLayout(orientation="horizontal", spacing=Space.SM, size_hint=(1, None), height=MIN_TOUCH)
        shell = SurfaceCard(
            radius=Radius.PILL,
            color=Theme.SURFACE_ALT,
            orientation="horizontal",
            size_hint=(1, 1),
            padding=[Space.MD, Space.XS],
        )
        self._manual_path = TextInput(
            hint_text="Or paste full file path...",
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
            size=(dp(72), MIN_TOUCH),
            font_size=TypeScale.SM,
        )
        add_btn.bind(on_release=self._on_manual_add)

        manual.add_widget(shell)
        manual.add_widget(add_btn)
        action_card.add_widget(manual)

        root.add_widget(action_card)
        self.add_widget(root)

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
        docs = self._controller.list_documents()
        self._list.clear_widgets()

        total_chunks = sum(int(d.get("num_chunks", 0)) for d in docs)
        if docs:
            self._summary_meta.text = f"{len(docs)} indexed documents  |  {total_chunks} chunks"
        else:
            self._summary_meta.text = "No documents indexed yet."

        if not docs:
            empty_card = SurfaceCard(
                radius=Radius.MD,
                color=Theme.SURFACE_ALT,
                orientation="vertical",
                size_hint=(1, None),
                height=dp(80),
                padding=[Space.MD, Space.SM],
            )
            empty_lbl = Label(
                text="Upload a PDF or TXT to power Document Q&A mode.",
                color=Theme.TEXT_MUTED,
                halign="left",
                valign="middle",
                font_size=TypeScale.SM,
            )
            bind_label_size(empty_lbl)
            empty_card.add_widget(empty_lbl)
            self._list.add_widget(empty_card)
            return

        for doc in docs:
            self._list.add_widget(DocumentRow(doc, on_delete=self._on_delete))

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
