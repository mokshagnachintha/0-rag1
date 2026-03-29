"""Reusable widget helpers for painted surfaces and common controls."""
from __future__ import annotations

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from app.ui.theme import Radius, Theme, TypeScale


def paint_background(widget, color, radius: float = 0):
    """Bind a background shape to widget canvas.before."""
    with widget.canvas.before:
        color_ref = Color(*color)
        shape = RoundedRectangle(radius=[dp(radius)]) if radius else Rectangle()

    def _sync_pos(w, _):
        shape.pos = w.pos

    def _sync_size(w, _):
        shape.size = w.size

    widget.bind(pos=_sync_pos, size=_sync_size)
    return color_ref, shape


def bind_label_size(label: Label, use_height: bool = True) -> None:
    """Keep label text_size in sync with widget bounds for wrapping/alignment."""

    def _sync(w, _):
        if use_height:
            w.text_size = (w.width, w.height)
        else:
            w.text_size = (w.width, None)

    label.bind(size=_sync)


class SurfaceCard(BoxLayout):
    def __init__(self, radius: float = Radius.MD, color=Theme.SURFACE, **kwargs):
        super().__init__(**kwargs)
        self._bg_color_ref, _ = paint_background(self, color, radius=radius)

    def set_color(self, color) -> None:
        self._bg_color_ref.rgba = color


class PillButton(Button):
    def __init__(
        self,
        text: str,
        bg_color,
        text_color=Theme.TEXT,
        font_size=TypeScale.SM,
        radius: float | None = None,
        **kwargs,
    ):
        super().__init__(
            text=text,
            color=text_color,
            font_size=font_size,
            background_normal="",
            background_color=(0, 0, 0, 0),
            **kwargs,
        )
        self._bg_color_ref, _ = paint_background(self, bg_color, radius=radius or Radius.PILL)

    def set_bg(self, color) -> None:
        self._bg_color_ref.rgba = color
