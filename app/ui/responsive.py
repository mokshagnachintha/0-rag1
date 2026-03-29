"""Responsive width-class helpers for phone + tablet layouts."""
from __future__ import annotations

from dataclasses import dataclass

from kivy.core.window import Window
from kivy.metrics import dp

SIZE_COMPACT = "compact"
SIZE_MEDIUM = "medium"


@dataclass(frozen=True)
class UIMetrics:
    size_class: str
    screen_pad_h: float
    screen_pad_v: float
    gap_sm: float
    gap_md: float
    shell_height: float
    shell_title_h: float
    shell_tabs_h: float
    shell_tab_btn_h: float
    card_radius: float
    section_radius: float
    control_radius: float
    chip_radius: float
    bubble_ratio: float
    bubble_min: float
    engine_collapsed_h: float
    engine_expanded_h: float
    input_zone_h: float
    attach_strip_h: float
    docs_summary_h: float


def width_class(width_px: float | None = None) -> str:
    width = Window.width if width_px is None else width_px
    return SIZE_MEDIUM if width >= dp(600) else SIZE_COMPACT


def metrics_for_class(size_class: str) -> UIMetrics:
    if size_class == SIZE_MEDIUM:
        return UIMetrics(
            size_class=SIZE_MEDIUM,
            screen_pad_h=dp(16),
            screen_pad_v=dp(12),
            gap_sm=dp(8),
            gap_md=dp(12),
            shell_height=dp(98),
            shell_title_h=dp(26),
            shell_tabs_h=dp(48),
            shell_tab_btn_h=dp(42),
            card_radius=dp(12),
            section_radius=dp(10),
            control_radius=dp(12),
            chip_radius=dp(10),
            bubble_ratio=0.70,
            bubble_min=dp(200),
            engine_collapsed_h=dp(48),
            engine_expanded_h=dp(94),
            input_zone_h=dp(78),
            attach_strip_h=dp(66),
            docs_summary_h=dp(84),
        )

    return UIMetrics(
        size_class=SIZE_COMPACT,
        screen_pad_h=dp(10),
        screen_pad_v=dp(8),
        gap_sm=dp(6),
        gap_md=dp(10),
        shell_height=dp(82),
        shell_title_h=dp(22),
        shell_tabs_h=dp(42),
        shell_tab_btn_h=dp(38),
        card_radius=dp(10),
        section_radius=dp(8),
        control_radius=dp(10),
        chip_radius=dp(8),
        bubble_ratio=0.78,
        bubble_min=dp(148),
        engine_collapsed_h=dp(42),
        engine_expanded_h=dp(84),
        input_zone_h=dp(72),
        attach_strip_h=dp(62),
        docs_summary_h=dp(72),
    )


def current_metrics() -> UIMetrics:
    return metrics_for_class(width_class())
