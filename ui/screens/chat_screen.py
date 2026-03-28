"""
chat_screen.py - Unified single-screen chat + document interface.

Design:
  - Header: "Offline RAG" title only - no tabs or mode toggles.
  - Chat area inheriting ChatGPT dark style.
  - Bottom bar: [+] attach  |  [text input pill]  |  [> send]
  - Tap + to pick a PDF/TXT via the native file browser.
    - Document ingestion progress shown inline as a status card.
    - Once any doc is loaded the AI auto-answers from it (RAG mode).
    - With no docs, the AI just chats freely (direct mode).
  - Model download / loading progress shown in the welcome message.
"""
from __future__ import annotations
import time

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout     import BoxLayout
from kivy.uix.anchorlayout  import AnchorLayout
from kivy.uix.scrollview    import ScrollView
from kivy.uix.label         import Label
from kivy.uix.textinput     import TextInput
from kivy.uix.button        import Button
from kivy.uix.widget        import Widget
from kivy.uix.progressbar   import ProgressBar
from kivy.clock             import Clock, mainthread
from kivy.metrics           import dp, sp
from kivy.graphics          import Color, RoundedRectangle, Rectangle
from kivy.animation         import Animation
from kivy.utils             import escape_markup
from kivy.effects.scroll    import ScrollEffect

from rag.debug_logger import debug_log, is_debug_logger_enabled
from ui.screens.debug_logger_overlay import DebugLoggerOverlay

# Palette
_BG        = (0.102, 0.102, 0.102, 1)   # #1a1a1a  page background
_HDR_BG    = (0.078, 0.078, 0.078, 1)   # #141414  header strip
_USER_BG   = (0.184, 0.184, 0.184, 1)   # #2f2f2f  user bubble
_INPUT_BG  = (0.173, 0.173, 0.173, 1)   # #2c2c2c  text-input wrap
_GREEN     = (0.098, 0.761, 0.490, 1)   # #19c37d  ChatGPT green
_ADD_BG    = (0.220, 0.220, 0.220, 1)   # #383838  + button
_WHITE     = (1,    1,    1,    1)
_MUTED     = (0.55, 0.55, 0.58, 1)
_DIVIDER   = (0.20, 0.20, 0.20, 1)
_DOC_CARD  = (0.12, 0.22, 0.17, 1)      # dark teal for doc status card
_ATTACH_BG = (0.165, 0.165, 0.165, 1)   # attachment preview card background
_RED_ICON  = (0.85, 0.18, 0.18, 1)      # PDF icon red


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _paint(widget, color, radius: float = 0):
    """Bind a solid colour background to a widget's canvas.before."""
    with widget.canvas.before:
        Color(*color)
        r = (RoundedRectangle(radius=[dp(radius)]) if radius else Rectangle())
    widget.bind(
        pos =lambda w, _: setattr(r, "pos",  w.pos),
        size=lambda w, _: setattr(r, "size", w.size),
    )
    return r


# ------------------------------------------------------------------ #
#  Avatar circle (letters "U" / "AI")                                 #
# ------------------------------------------------------------------ #

class _Avatar(Widget):
    _COLS = {
        "user":      (0.40, 0.40, 0.90, 1),
        "assistant": _GREEN,
        "system":    (0.80, 0.20, 0.20, 1),
    }

    def __init__(self, role: str, **kw):
        super().__init__(size_hint=(None, None), size=(dp(32), dp(32)), **kw)
        letter = {"user": "U", "assistant": "AI", "system": "!"}.get(role, "?")
        with self.canvas:
            Color(*self._COLS.get(role, (0.5, 0.5, 0.5, 1)))
            self._circ = RoundedRectangle(radius=[dp(16)])
        self.bind(pos=self._upd, size=self._upd)
        self._lbl = Label(text=letter, font_size=sp(11), bold=True, color=_WHITE)
        self.add_widget(self._lbl)

    def _upd(self, *_):
        self._circ.pos  = self.pos
        self._circ.size = self.size
        self._lbl.center = self.center


# ------------------------------------------------------------------ #
#  Message row (user bubble right / assistant text left)              #
# ------------------------------------------------------------------ #

class MessageRow(BoxLayout):
    def __init__(self, text: str, role: str = "assistant", **kw):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            spacing=dp(10),
            **kw,
        )
        self.role = role
        self._lbl = Label(
            text=text, markup=True,
            size_hint_y=None, text_size=(None, None),
            halign="left", valign="top",
            color=_WHITE, font_size=sp(14.5),
        )
        self._lbl.bind(texture_size=self._on_tex)
        self.bind(width=self._on_w)
        _paint(self, _BG)

        if role == "user":
            self._build_user()
        else:
            self._build_asst()

    def _build_user(self):
        self.add_widget(Widget(size_hint_x=1))           # push right
        bub = BoxLayout(size_hint=(None, None), padding=[dp(12), dp(10)])
        _paint(bub, _USER_BG, radius=18)
        bub.add_widget(self._lbl)
        self._bub = bub
        self.add_widget(bub)
        self.add_widget(_Avatar("user"))

    def _build_asst(self):
        self.add_widget(_Avatar("assistant"))
        self.add_widget(self._lbl)

    def _on_tex(self, lbl, ts):
        new_lbl_h = ts[1] + dp(4)
        if abs(lbl.height - new_lbl_h) > 0.5:
            lbl.height = new_lbl_h

        if self.role == "user" and hasattr(self, "_bub"):
            new_bub_w = min(ts[0] + dp(28), self.width * 0.82)
            new_bub_h = lbl.height + dp(20)
            if abs(self._bub.width - new_bub_w) > 0.5:
                self._bub.width = new_bub_w
            if abs(self._bub.height - new_bub_h) > 0.5:
                self._bub.height = new_bub_h

        new_row_h = max(lbl.height + dp(20), dp(52))
        if abs(self.height - new_row_h) > 0.5:
            self.height = new_row_h

    def _on_w(self, *_):
        avail = max(1, self.width - dp(72))
        if self.role == "user":
            target = (avail * 0.82, None)
        else:
            target = (avail, None)
        if self._lbl.text_size != target:
            self._lbl.text_size = target

    def append(self, token: str):
        # Streamed model tokens can contain markup-like fragments (e.g. "[" / "]")
        # that make Kivy re-parse text repeatedly and cause visual glitches.
        self._lbl.text += escape_markup(token)


# ------------------------------------------------------------------ #
#  Attachment preview card (ChatGPT-style, shown above input bar)     #
# ------------------------------------------------------------------ #

class AttachmentPreviewCard(BoxLayout):
    """
    Shows a PDF/TXT attachment thumbnail above the message input,
    matching the ChatGPT attachment card style.
    """
    def __init__(self, filepath: str, on_remove, **kw):
        import os
        super().__init__(
            orientation="horizontal",
            size_hint=(None, None),
            size=(dp(220), dp(68)),
            padding=[dp(10), dp(8), dp(8), dp(8)],
            spacing=dp(10),
            **kw,
        )
        _paint(self, _ATTACH_BG, radius=14)

        fname = os.path.basename(filepath)
        ext   = os.path.splitext(fname)[1].upper().lstrip(".") or "FILE"
        try:
            sz_kb = os.path.getsize(filepath) // 1024
            size_txt = f"{sz_kb} KB" if sz_kb < 1024 else f"{sz_kb//1024} MB"
        except Exception:
            size_txt = ""

        # PDF/TXT icon box
        icon_box = BoxLayout(
            size_hint=(None, None), size=(dp(42), dp(42)),
        )
        _paint(icon_box, _RED_ICON, radius=8)
        icon_lbl = Label(
            text=f"[b]{ext[:4]}[/b]", markup=True,
            font_size=sp(10), color=_WHITE,
            halign="center", valign="middle",
        )
        icon_lbl.bind(size=lambda w, _: setattr(w, "text_size", w.size))
        icon_box.add_widget(icon_lbl)
        self.add_widget(icon_box)

        # Filename + size
        info = BoxLayout(
            orientation="vertical", size_hint=(1, 1), spacing=dp(2),
        )
        # Truncate long filenames
        display = fname if len(fname) <= 22 else fname[:19] + "..."
        display = escape_markup(display)
        name_lbl = Label(
            text=f"[b]{display}[/b]", markup=True,
            font_size=sp(12), color=_WHITE,
            halign="left", valign="middle",
            size_hint_y=None, height=dp(22),
        )
        name_lbl.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))

        type_lbl = Label(
            text=f"{ext} - {size_txt}" if size_txt else ext,
            font_size=sp(10.5), color=_MUTED,
            halign="left", valign="middle",
            size_hint_y=None, height=dp(18),
        )
        type_lbl.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))

        info.add_widget(name_lbl)
        info.add_widget(type_lbl)
        self.add_widget(info)

        # x remove button
        x_btn = Button(
            text="x", font_size=sp(13),
            size_hint=(None, None), size=(dp(24), dp(24)),
            background_normal="", background_color=(0, 0, 0, 0),
            color=_MUTED,
        )
        x_btn.bind(on_release=lambda *_: on_remove())
        anc = AnchorLayout(
            size_hint=(None, 1), width=dp(28),
            anchor_x="center", anchor_y="center",
        )
        anc.add_widget(x_btn)
        self.add_widget(anc)


# ------------------------------------------------------------------ #
#  Document ingestion status card                                      #
# ------------------------------------------------------------------ #

class DocStatusCard(BoxLayout):
    """
    Inline card that shows file name + progress indicator while a
    document is being chunked and indexed.
    """
    def __init__(self, filename: str, **kw):
        super().__init__(
            orientation="vertical",
            size_hint=(1, None),
            padding=[dp(14), dp(8), dp(14), dp(8)],
            spacing=dp(4),
            **kw,
        )
        _paint(self, _BG)

        inner = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            padding=[dp(14), dp(12)],
            spacing=dp(6),
        )
        _paint(inner, _DOC_CARD, radius=14)

        self._title = Label(
            text=f"[b]DOC  {escape_markup(filename)}[/b]",
            markup=True,
            color=_WHITE, font_size=sp(13),
            size_hint_y=None, height=dp(22),
            halign="left", valign="middle",
        )
        self._title.bind(size=lambda w, _: setattr(w, "text_size", (w.width, None)))

        self._status = Label(
            text="Indexing...",
            color=_GREEN, font_size=sp(12),
            size_hint_y=None, height=dp(18),
            halign="left", valign="middle",
        )
        self._status.bind(size=lambda w, _: setattr(w, "text_size", (w.width, None)))

        self._bar = ProgressBar(
            max=100, value=10,
            size_hint=(1, None), height=dp(5),
        )

        inner.add_widget(self._title)
        inner.add_widget(self._status)
        inner.add_widget(self._bar)
        inner.bind(minimum_height=inner.setter("height"))

        self.add_widget(inner)
        self.bind(minimum_height=self.setter("height"))

    def set_done(self, success: bool, message: str):
        self._bar.value = 100 if success else 0
        col  = "00cc66" if success else "ff5555"
        self._status.text   = f"[color={col}]{message}[/color]"
        self._status.markup = True


class _ModelProgressRow(BoxLayout):
    def __init__(self, title: str, **kw):
        super().__init__(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(62),
            spacing=dp(4),
            **kw,
        )
        top = BoxLayout(size_hint=(1, None), height=dp(18))
        self._title = Label(
            text=title,
            size_hint=(1, 1),
            color=(0.9, 0.9, 0.9, 1),
            font_size=sp(12),
            halign="left",
            valign="middle",
        )
        self._title.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        self._pct = Label(
            text="0%",
            size_hint=(None, 1),
            width=dp(44),
            color=(0.7, 0.7, 0.72, 1),
            font_size=sp(11),
            halign="right",
            valign="middle",
        )
        self._pct.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        top.add_widget(self._title)
        top.add_widget(self._pct)
        self.add_widget(top)

        self._bar = ProgressBar(max=100, value=0, size_hint=(1, None), height=dp(8))
        self.add_widget(self._bar)

        self._detail = Label(
            text="Pending",
            size_hint=(1, None),
            height=dp(18),
            color=(0.65, 0.65, 0.68, 1),
            font_size=sp(10.5),
            halign="left",
            valign="middle",
        )
        self._detail.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        self.add_widget(self._detail)

    def set_progress(self, fraction: float, status: str):
        f = max(0.0, min(1.0, float(fraction)))
        self._bar.value = int(f * 100)
        self._pct.text = f"{int(f * 100)}%"
        self._detail.text = status or "Pending"


class BootstrapStatusCard(BoxLayout):
    def __init__(self, on_retry, **kw):
        super().__init__(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(182),
            padding=[dp(12), dp(10), dp(12), dp(10)],
            spacing=dp(8),
            **kw,
        )
        _paint(self, (0.12, 0.13, 0.15, 1), radius=14)

        self._title = Label(
            text="[b]Model setup in progress[/b]",
            markup=True,
            size_hint=(1, None),
            height=dp(22),
            color=_WHITE,
            font_size=sp(13),
            halign="left",
            valign="middle",
        )
        self._title.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        self.add_widget(self._title)

        self._overall = Label(
            text="Preparing AI models...",
            size_hint=(1, None),
            height=dp(20),
            color=(0.73, 0.77, 0.82, 1),
            font_size=sp(11.5),
            halign="left",
            valign="middle",
        )
        self._overall.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        self.add_widget(self._overall)

        self._qwen = _ModelProgressRow("Qwen model")
        self._nomic = _ModelProgressRow("Nomic embeddings")
        self.add_widget(self._qwen)
        self.add_widget(self._nomic)

        self._retry_btn = Button(
            text="Retry engine startup",
            size_hint=(None, None),
            size=(dp(176), dp(34)),
            background_normal="",
            background_color=(0.24, 0.47, 0.72, 1),
            color=_WHITE,
            font_size=sp(11.5),
            opacity=0.0,
            disabled=True,
        )
        self._retry_btn.bind(on_release=on_retry)
        retry_row = BoxLayout(size_hint=(1, None), height=dp(36))
        retry_row.add_widget(Widget())
        retry_row.add_widget(self._retry_btn)
        self.add_widget(retry_row)

    def update_state(self, state: dict):
        self._overall.text = state.get("overall_text", "Preparing AI models...")
        models = state.get("models", {})
        qwen = models.get("qwen", {})
        nomic = models.get("nomic", {})
        self._qwen.set_progress(qwen.get("fraction", 0.0), qwen.get("status", "Pending"))
        self._nomic.set_progress(nomic.get("fraction", 0.0), nomic.get("status", "Pending"))

    def set_ready(self):
        self._overall.text = "Offline ready."
        self._qwen.set_progress(1.0, "Ready")
        self._nomic.set_progress(1.0, "Ready")
        self._retry_btn.opacity = 0.0
        self._retry_btn.disabled = True

    def set_overall_text(self, text: str):
        self._overall.text = text

    def set_error(self, message: str):
        self._overall.text = message
        self._retry_btn.opacity = 1.0
        self._retry_btn.disabled = False

    def set_retrying(self):
        self._overall.text = "Retrying AI engine startup..."
        self._retry_btn.opacity = 0.0
        self._retry_btn.disabled = True


# ------------------------------------------------------------------ #
#  Typing indicator  . . .                                            #
# ------------------------------------------------------------------ #

class _TypingIndicator(BoxLayout):
    def __init__(self, **kw):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None), height=dp(40),
            padding=[dp(56), dp(4)], spacing=dp(6),
            **kw,
        )
        self._dots: list[Label] = []
        for _ in range(3):
            d = Label(
                text=".", font_size=sp(10), color=_MUTED,
                size_hint=(None, None), size=(dp(14), dp(14)),
            )
            self._dots.append(d)
            self.add_widget(d)
        self._tick = 0
        Clock.schedule_interval(self._anim, 0.42)

    def _anim(self, *_):
        for i, d in enumerate(self._dots):
            d.color = _WHITE if i == self._tick % 3 else _MUTED
        self._tick += 1

    def stop(self):
        Clock.unschedule(self._anim)


# ================================================================== #
#  ChatScreen                                                         #
# ================================================================== #

class ChatScreen(Screen):
    """
    Single-screen UI.  No tab bar.
    Internal mode tracked automatically:
      _has_docs=True  ->  RAG (answer from indexed document chunks)
      _has_docs=False ->  direct LLM chat with rolling history
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self._history:        list                    = []
        self._history_summary: str                    = ""  # compressed older turns
        self._token_buf:      list                    = []  # token batch buffer
        self._token_flush_ev  = None                        # pending Clock event
        self._pending_q:      str                     = ""
        self._current_row:    MessageRow | None       = None
        self._typing:         _TypingIndicator | None = None
        self._has_docs:       bool                    = False
        self._rag_doc_name:   str                     = ""
        self._pending_attach: str | None              = None
        self._attach_card:    AttachmentPreviewCard | None = None
        self._scroll_pending: bool                   = False
        self._streaming_active: bool                 = False
        self._service_started: bool                  = False
        self._model_ready:    bool                   = False   # True once LLM is loaded
        self._send_btn:       Button | None          = None    # ref for dimming
        self._composer:       BoxLayout | None       = None
        self._bootstrap_wrap: BoxLayout | None       = None
        self._bootstrap_card: BootstrapStatusCard | None = None
        self._welcome_sent:   bool                   = False
        self._perm_requested: bool                   = False
        self._last_model_update_at: float            = 0.0
        self._debug_enabled: bool                    = is_debug_logger_enabled()
        self._debug_overlay: DebugLoggerOverlay | None = None
        debug_log("ui.chat", f"ChatScreen init (debug_logger={self._debug_enabled})")
        self._build_ui()

    # ---------------------------------------------------------------- #
    #  Layout                                                           #
    # ---------------------------------------------------------------- #

    def _build_ui(self):
        root = BoxLayout(orientation="vertical")
        _paint(root, _BG)

        # Header
        hdr = BoxLayout(
            size_hint=(1, None), height=dp(54),
            padding=[dp(10), dp(0), dp(10), dp(0)],
            spacing=dp(8),
        )
        _paint(hdr, _HDR_BG)
        hdr.add_widget(Widget(size_hint=(None, 1), width=dp(56)))
        hdr_lbl = Label(
            text="[b]O-RAG[/b]", markup=True,
            color=_WHITE, font_size=sp(16),
            halign="center", valign="middle",
        )
        hdr_lbl.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        hdr.add_widget(hdr_lbl)

        right = AnchorLayout(
            size_hint=(None, 1),
            width=dp(56),
            anchor_x="right",
            anchor_y="center",
        )
        if self._debug_enabled:
            log_btn = Button(
                text="LOG",
                size_hint=(None, None),
                size=(dp(50), dp(30)),
                font_size=sp(11),
                bold=True,
                background_normal="",
                background_color=(0.24, 0.29, 0.37, 1),
                color=_WHITE,
            )
            log_btn.bind(on_release=self._open_debug_logger)
            right.add_widget(log_btn)
        else:
            right.add_widget(Widget())
        hdr.add_widget(right)
        root.add_widget(hdr)

        sep = Widget(size_hint=(1, None), height=dp(1))
        _paint(sep, _DIVIDER)
        root.add_widget(sep)

        self._bootstrap_wrap = BoxLayout(
            size_hint=(1, None),
            height=dp(198),
            padding=[dp(12), dp(8), dp(12), dp(8)],
        )
        _paint(self._bootstrap_wrap, _BG)
        self._bootstrap_card = BootstrapStatusCard(on_retry=self._on_retry_engine_start)
        self._bootstrap_wrap.add_widget(self._bootstrap_card)
        root.add_widget(self._bootstrap_wrap)

        # Message list
        self._scroll = ScrollView(
            size_hint=(1, 1), do_scroll_x=False, bar_width=dp(3),
            effect_cls=ScrollEffect,
        )
        _paint(self._scroll, _BG)
        self._msgs = BoxLayout(orientation="vertical", size_hint=(1, None), spacing=0)
        self._msgs.bind(minimum_height=self._msgs.setter("height"))
        self._msgs.bind(height=lambda *_: self._on_msgs_height_changed())
        self._scroll.add_widget(self._msgs)
        root.add_widget(self._scroll)

        # Composer area
        composer = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(88),
            padding=[dp(0), dp(0), dp(0), dp(0)],
        )
        self._composer = composer
        _paint(composer, _HDR_BG)

        # Attachment preview strip - hidden until a file is picked
        self._attach_strip = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=0,
            padding=[dp(12), dp(6), dp(12), dp(0)],
        )
        _paint(self._attach_strip, _HDR_BG)
        composer.add_widget(self._attach_strip)

        rail = BoxLayout(
            size_hint=(1, None),
            height=dp(88),
            padding=[dp(12), dp(12), dp(12), dp(12)],
        )
        rail_row = BoxLayout(size_hint=(1, None), height=dp(50), spacing=dp(10))

        add_btn = Button(
            text="+",
            size_hint=(None, None),
            size=(dp(44), dp(44)),
            font_size=sp(24),
            background_normal="",
            background_color=(0, 0, 0, 0),
            color=_WHITE,
            bold=True,
        )
        _paint(add_btn, _ADD_BG, radius=22)
        add_btn.bind(on_release=self._on_attach)
        rail_row.add_widget(add_btn)

        pill = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(44),
            padding=[dp(14), dp(6), dp(14), dp(6)],
        )
        _paint(pill, _INPUT_BG, radius=22)

        self._input = TextInput(
            hint_text="Message...",
            multiline=False,
            size_hint=(1, 1),
            font_size=sp(14),
            foreground_color=_WHITE,
            hint_text_color=_MUTED,
            background_color=(0, 0, 0, 0),
            cursor_color=_WHITE,
            padding=[0, dp(10)],
        )
        self._input.bind(on_text_validate=self._on_send)
        pill.add_widget(self._input)
        rail_row.add_widget(pill)

        send_btn = Button(
            text=">",
            size_hint=(None, None),
            size=(dp(44), dp(44)),
            font_size=sp(20),
            background_normal="",
            background_color=(0, 0, 0, 0),
            color=_WHITE,
            bold=True,
            disabled=True,
            opacity=0.45,
        )
        _paint(send_btn, _GREEN, radius=22)
        send_btn.bind(on_release=self._on_send)
        self._send_btn = send_btn
        rail_row.add_widget(send_btn)

        rail.add_widget(rail_row)
        composer.add_widget(rail)
        root.add_widget(composer)

        self.add_widget(root)

        # Register model-ready callbacks immediately (before init() fires)
        # so we never miss the done event due to a timing race.
        Clock.schedule_once(self._register_pipeline_callbacks, 0)

    # ---------------------------------------------------------------- #
    #  Model progress / ready callbacks                                 #
    # ---------------------------------------------------------------- #

    def _register_pipeline_callbacks(self, *_):
        debug_log("ui.chat", "Registering pipeline bootstrap callbacks")
        from rag.pipeline import register_auto_download_callbacks
        register_auto_download_callbacks(
            on_progress=self._on_model_progress,
            on_done    =self._on_model_ready,
            on_state   =self._on_bootstrap_state,
        )

    def _open_debug_logger(self, *_):
        if not self._debug_enabled:
            return
        if self._debug_overlay is None:
            self._debug_overlay = DebugLoggerOverlay()
        debug_log("ui.chat", "Opening debug logger overlay")
        self._debug_overlay.open()

    @mainthread
    def _on_model_progress(self, frac: float, text: str):
        now = time.monotonic()
        if (now - self._last_model_update_at) < 0.4:
            return
        self._last_model_update_at = now
        if self._bootstrap_card:
            self._bootstrap_card.set_overall_text(text)

    @mainthread
    def _on_bootstrap_state(self, state: dict):
        now = time.monotonic()
        if (now - self._last_model_update_at) < 0.15:
            return
        self._last_model_update_at = now
        if self._bootstrap_card:
            self._bootstrap_card.update_state(state)

    def _on_retry_engine_start(self, *_):
        debug_log("ui.chat", "Retry engine startup tapped")
        if self._bootstrap_card:
            self._bootstrap_card.set_retrying()
        self._start_android_service_once(force=True)
        try:
            from rag.pipeline import retry_engine_probe
            retry_engine_probe()
        except Exception as exc:
            self._on_model_ready(False, f"Could not restart engine probe: {exc}")

    @mainthread
    def _on_model_ready(self, success: bool, message: str):
        debug_log("ui.chat", f"Model ready callback: success={success} message={message}")
        if success:
            self._model_ready = True
            if self._send_btn:
                self._send_btn.color = _WHITE
                self._send_btn.opacity = 1.0
                self._send_btn.disabled = False
            if self._bootstrap_card:
                self._bootstrap_card.set_ready()
            if self._bootstrap_wrap:
                Animation.stop_all(self._bootstrap_wrap, "height")
                Animation(height=0, duration=0.2, t="out_quad").start(self._bootstrap_wrap)
            if not self._welcome_sent:
                self._welcome_sent = True
                self._add_msg(
                    "[b]Offline ready.[/b]\n"
                    "Send a message to chat, or tap + to attach a PDF/TXT for RAG.",
                    role="assistant",
                )
        else:
            self._model_ready = False
            if self._send_btn:
                self._send_btn.disabled = True
                self._send_btn.opacity = 0.45
            if self._bootstrap_wrap:
                self._bootstrap_wrap.height = dp(198)
            if self._bootstrap_card:
                self._bootstrap_card.set_error(message)

    # ---------------------------------------------------------------- #
    #  Storage permission request                                       #
    # ---------------------------------------------------------------- #

    def _request_storage_permissions(self, *_):
        """Ask for storage permissions on Android before opening picker."""
        import os
        if not os.environ.get("ANDROID_PRIVATE"):
            return  # desktop - no-op
        if self._perm_requested:
            return
        self._perm_requested = True
        try:
            from android.permissions import request_permissions, Permission  # type: ignore
            sdk = 0
            try:
                from jnius import autoclass  # type: ignore
                sdk = autoclass("android.os.Build$VERSION").SDK_INT
            except Exception:
                pass
            if sdk >= 33:
                # Android 13+ - READ_MEDIA_IMAGES covers images;
                # documents/PDFs still come through SAF so no extra perm needed.
                request_permissions([
                    Permission.READ_MEDIA_IMAGES,
                    Permission.READ_MEDIA_VIDEO,
                ])
            else:
                request_permissions([
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                ])
        except Exception as e:
            print(f"[permissions] Could not request: {e}")

    def _start_android_service_once(self, force: bool = False):
        """Start Android foreground service helper (no-op on desktop)."""
        if self._service_started and not force:
            debug_log("ui.chat.service", "Service start skipped (already started)")
            return
        debug_log("ui.chat.service", f"Service start requested (force={force})")
        try:
            from android import AndroidService  # type: ignore
            svc = AndroidService("O-RAG AI Engine", "AI engine running in background")
            svc.start("start")
            self._service_started = True
            print("[chat] Android foreground service started.")
            debug_log("ui.chat.service", "Service start call issued")
        except Exception as e:
            # Desktop or unavailable android APIs.
            print(f"[chat] Service start skipped: {e}")
            debug_log("ui.chat.service", f"Service start skipped: {e}", level="WARN")

    # ---------------------------------------------------------------- #
    #  Attach document via file picker                                  #
    # ---------------------------------------------------------------- #

    # Unique request code for startActivityForResult
    _PICK_REQ = 0x4F52   # "OR"

    def _on_attach(self, *_):
        # Guard: prevent double-open if picker is already visible
        if getattr(self, "_picker_open", False):
            return
        self._picker_open = True
        import os
        if os.environ.get("ANDROID_PRIVATE"):
            # On-demand permission request instead of model-ready prompt.
            self._request_storage_permissions()
            self._android_pick_file()
        else:
            self._desktop_pick_file()

    # -- Android path: native startActivityForResult ------------------

    def _android_pick_file(self):
        try:
            from jnius import autoclass          # type: ignore
            from android.activity import bind as activity_bind  # type: ignore

            # Register result handler before launching intent
            activity_bind(on_activity_result=self._on_activity_result)

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent         = autoclass("android.content.Intent")

            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("*/*")               # show all; filtered by MIME below
            intent.addCategory(Intent.CATEGORY_OPENABLE)

            # Restrict picker to PDF + plain-text via EXTRA_MIME_TYPES
            try:
                ArrayList = autoclass("java.util.ArrayList")
                mimes = ArrayList()
                mimes.add("application/pdf")
                mimes.add("text/plain")
                intent.putExtra("android.intent.extra.MIME_TYPES",
                                mimes.toArray())
            except Exception:
                # Fallback: accept everything; resolve_uri will validate ext
                pass

            PythonActivity.mActivity.startActivityForResult(
                intent, self._PICK_REQ
            )
        except Exception as e:
            import traceback; traceback.print_exc()
            self._picker_open = False
            self._add_msg(
                f"[color=ff5555]Could not open file picker:[/color]\n{e}",
                role="assistant",
            )

    def _on_activity_result(self, request_code, result_code, data):
        # Unregister immediately so we don't receive stale callbacks
        try:
            from android.activity import unbind as activity_unbind  # type: ignore
            activity_unbind(on_activity_result=self._on_activity_result)
        except Exception:
            pass

        self._picker_open = False

        if request_code != self._PICK_REQ:
            return
        RESULT_OK = -1   # android.app.Activity.RESULT_OK
        if result_code != RESULT_OK or data is None:
            return

        try:
            uri = data.getData()
            if uri is None:
                return
            uri_str = uri.toString()
            Clock.schedule_once(lambda *_: self._process_picked_uri(uri_str), 0)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._add_msg(
                f"[color=ff5555]Could not read file URI:[/color]\n{e}",
                role="assistant",
            )

    @mainthread
    def _process_picked_uri(self, uri_str: str):
        try:
            from rag.chunker import resolve_uri
            path = resolve_uri(uri_str)
            self._stage_attachment(path)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._add_msg(
                f"[color=ff5555]Could not open file:[/color]\n{e}",
                role="assistant",
            )

    # -- Desktop path: plyer fallback ---------------------------------

    def _desktop_pick_file(self):
        try:
            from plyer import filechooser
            filechooser.open_file(
                on_selection=self._on_file_chosen,
                filters=[["Documents", "*.pdf", "*.txt", "*.PDF", "*.TXT"]],
                title="Pick a document",
                multiple=False,
            )
        except Exception as e:
            self._picker_open = False
            self._add_msg(
                "File picker unavailable on this device.\n"
                "Type the [b]full path[/b] to your file and send it - "
                f"e.g. [i]/sdcard/Download/report.pdf[/i]",
                role="assistant",
            )

    @mainthread
    def _on_file_chosen(self, selection):
        self._picker_open = False
        if not selection or selection[0] is None:
            return
        try:
            from rag.chunker import resolve_uri
            path = resolve_uri(selection[0])
            self._stage_attachment(path)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._add_msg(
                f"[color=ff5555]Could not open file:[/color]\n{e}",
                role="assistant",
            )

    def _stage_attachment(self, path: str):
        """Show the attachment preview card above the input bar."""
        import os
        self._pending_attach = path

        # Remove any existing card
        self._attach_strip.clear_widgets()

        card = AttachmentPreviewCard(
            filepath=path,
            on_remove=self._remove_attachment,
        )
        self._attach_card = card
        self._attach_strip.add_widget(card)

        # Expand the strip to show the card
        self._attach_strip.height = dp(76)
        # Grow the whole composer area
        if self._composer:
            self._composer.height = dp(164)

    @mainthread
    def _remove_attachment(self):
        """Dismiss the staged attachment card."""
        self._pending_attach = None
        self._attach_card    = None
        self._attach_strip.clear_widgets()
        self._attach_strip.height = 0
        if self._composer:
            self._composer.height = dp(88)

    def _start_ingest(self, path: str, fname: str):
        card = DocStatusCard(fname)
        self._msgs.add_widget(card)
        self._scroll_down()
        from rag.pipeline import ingest_document
        ingest_document(
            path,
            on_done=lambda ok, msg: self._ingest_done(card, ok, msg, fname),
        )

    @mainthread
    def _ingest_done(self, card: DocStatusCard, ok: bool, msg: str, fname: str = ""):
        card.set_done(ok, msg)
        if ok:
            self._has_docs = True
            self._rag_doc_name = fname
            safe_name = escape_markup(fname)
            self._add_msg(
                f"[b]RAG mode active[/b] - {safe_name}\n"
                "I'll answer all your questions using this document.\n"
                "[color=888888][size=12sp]"
                "Type [b]quit rag[/b] to return to normal chat."
                "[/size][/color]",
                role="assistant",
            )
        else:
            self._add_msg(
                f"[color=ff5555]Could not load document:[/color]\n{msg}",
                role="assistant",
            )
        self._scroll_down()

    # ---------------------------------------------------------------- #
    #  Handle plain file-path typed into chat                           #
    # ---------------------------------------------------------------- #

    def _maybe_load_path(self, text: str) -> bool:
        """If user pastes a file path, stage it as an attachment."""
        import os
        s = text.strip()
        is_path = (s.startswith("/") or (len(s) > 2 and s[1] == ":")) \
                  and os.path.isfile(s)
        if is_path:
            self._stage_attachment(s)
            return True
        return False

    # ---------------------------------------------------------------- #
    #  Send / receive                                                   #
    # ---------------------------------------------------------------- #

    def _on_send(self, *_):
        q    = self._input.text.strip()
        path = self._pending_attach

        # Nothing to do if both empty
        if not q and not path:
            return

        # Avoid overlapping requests while a streamed response is active.
        if self._streaming_active and not path:
            self._add_msg(
                "[color=bbbbbb]Please wait for the current response to finish.[/color]",
                role="assistant",
            )
            return

        # "quit rag" command - exit RAG mode and reset docs
        if q.lower() in ("quit rag", "exit rag", "/quit rag", "/exit rag"):
            self._input.text = ""
            self._add_msg(escape_markup(q), role="user")
            if self._has_docs:
                from rag.pipeline import clear_all_documents
                clear_all_documents()
                self._has_docs     = False
                doc = escape_markup(self._rag_doc_name)
                self._rag_doc_name = ""
                self._add_msg(
                    f"[b]RAG mode off[/b] - {doc} removed.\n"
                    "Back to normal chat. Your conversation history is preserved.",
                    role="assistant",
                )
            else:
                self._add_msg(
                    "Not in RAG mode. Upload a PDF or TXT to activate it.",
                    role="assistant",
                )
            return

        # Block sends until the LLM is ready
        if not self._model_ready:
            self._add_msg(
                "[b]AI engine is still starting up...[/b]\n"
                "[color=888888][size=12sp]"
                "You can watch the progress in the welcome panel above. "
                "Please send your message once it's ready."
                "[/size][/color]",
                role="assistant",
            )
            return

        self._input.text = ""

        # If there is a staged file, ingest it first
        if path:
            import os
            fname = os.path.basename(path)
            self._remove_attachment()
            # Show a user bubble with the attachment + any typed text
            bubble_text = f"[b]{escape_markup(fname)}[/b]"
            if q:
                bubble_text += f"\n{escape_markup(q)}"
            self._add_msg(bubble_text, role="user")
            self._start_ingest(path, fname)
            return

        # Plain text path typed into the input box
        if self._maybe_load_path(q):
            return

        self._pending_q = q
        self._streaming_active = True
        self._add_msg(escape_markup(q), role="user")
        # Reset token buffer for new response
        self._token_buf.clear()
        if self._token_flush_ev is not None:
            Clock.unschedule(self._token_flush_ev)
            self._token_flush_ev = None
        self._show_typing()

        if self._has_docs:
            from rag.pipeline import ask
            ask(q, stream_cb=self._on_token, on_done=self._on_done)
        else:
            from rag.pipeline import chat_direct
            chat_direct(
                q,
                history  =list(self._history),
                summary  =self._history_summary,
                stream_cb=self._on_token,
                on_done  =self._on_done,
            )

    def _on_token(self, token: str):
        """Called from background thread for every streamed token.
        Buffers tokens and flushes to UI every 80 ms to reduce
        mainthread event overhead (~200 tokens -> ~10 flushes).
        """
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
            self._scroll_to_bottom_instant()

    @mainthread
    def _on_done(self, success: bool, message: str):
        # Flush any remaining buffered tokens first
        if self._token_buf:
            batch = "".join(self._token_buf)
            self._token_buf.clear()
            if self._token_flush_ev is not None:
                Clock.unschedule(self._token_flush_ev)
                self._token_flush_ev = None
            if self._typing:
                self._hide_typing()
                self._current_row = self._add_msg("", role="assistant")
            if self._current_row:
                self._current_row.append(batch)
        self._hide_typing()
        if success:
            if not self._has_docs and self._pending_q and self._current_row:
                # Strip Kivy markup tags before storing in history so the
                # raw text is sent to the model (markup tokens corrupt prompts)
                import re
                raw_ans = re.sub(r'\[/?[a-zA-Z][^\]]*\]', '',
                                 self._current_row._lbl.text).strip()
                self._history.append((self._pending_q, raw_ans))
                # Keep last 3 turns verbatim; compress older ones into a
                # one-line summary (no LLM call - just first sentence of reply).
                if len(self._history) > 6:
                    old = self._history[:-3]          # turns to compress
                    keep = self._history[-3:]         # most recent 3 verbatim
                    for _q, _a in old:
                        first_sent = _a.split(".")[0].strip()[:120]
                        if first_sent:
                            self._history_summary += f"- {_q}: {first_sent}.\n"
                    self._history = keep
        else:
            if self._current_row:
                self._current_row._lbl.text = (
                    f"[color=ff5555]{message}[/color]"
                )
            else:
                self._add_msg(message, role="assistant")
        self._streaming_active = False
        self._scroll_down()
        self._pending_q   = ""
        self._current_row = None

    # ---------------------------------------------------------------- #
    #  Helpers                                                          #
    # ---------------------------------------------------------------- #

    def _add_msg(self, text: str, role: str = "assistant") -> MessageRow:
        row = MessageRow(text, role=role)
        self._msgs.add_widget(row)
        if self._streaming_active:
            Clock.schedule_once(lambda *_: self._scroll_to_bottom_instant(), 0.0)
        else:
            Clock.schedule_once(lambda *_: self._scroll_down(), 0.05)
        return row

    def _show_typing(self):
        self._typing = _TypingIndicator()
        self._msgs.add_widget(self._typing)
        if self._streaming_active:
            Clock.schedule_once(lambda *_: self._scroll_to_bottom_instant(), 0.0)
        else:
            Clock.schedule_once(lambda *_: self._scroll_down(), 0.05)

    def _hide_typing(self):
        if self._typing:
            self._typing.stop()
            self._msgs.remove_widget(self._typing)
            self._typing = None

    def _do_scroll(self, *_):
        """Debounced scroll during streaming (snap to bottom, no animation)."""
        self._scroll_pending = False
        self._scroll_to_bottom_instant()

    def _on_msgs_height_changed(self):
        if self._streaming_active:
            self._scroll_to_bottom_instant()

    def _scroll_to_bottom_instant(self):
        Animation.stop_all(self._scroll, "scroll_y")
        self._scroll.scroll_y = 0

    def _scroll_down(self):
        """Smoothly animate to bottom of chat."""
        Animation.stop_all(self._scroll, "scroll_y")
        Animation(scroll_y=0, duration=0.15, t="out_quad").start(self._scroll)
