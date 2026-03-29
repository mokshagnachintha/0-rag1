"""Responsive width-class helpers for phone + tablet layouts."""
from __future__ import annotations

from dataclasses import dataclass

from kivy.core.window import Window
from kivy.metrics import dp

SIZE_COMPACT = "compact"
SIZE_MEDIUM = "medium"
SIZE_EXPANDED = "expanded"


@dataclass(frozen=True)
class UIMetrics:
    size_class: str
    screen_pad_h: float
    screen_pad_v: float
    gap_xs: float
    gap_sm: float
    gap_md: float
    gap_lg: float
    font_scale: float
    shell_height: float
    shell_title_h: float
    shell_tabs_h: float
    shell_tab_btn_h: float
    card_radius: float
    section_radius: float
    tab_radius: float
    control_radius: float
    chip_radius: float
    icon_radius: float
    bubble_ratio: float
    bubble_min: float
    engine_collapsed_h: float
    engine_expanded_h: float
    input_zone_h: float
    attach_strip_h: float
    docs_summary_h: float
    control_h: float
    icon_button_h: float
    send_button_h: float
    mode_button_h: float
    mode_toggle_w: float
    split_primary_ratio: float


def width_class(width_px: float | None = None) -> str:
    width = Window.width if width_px is None else width_px
    if width >= dp(900):
        return SIZE_EXPANDED
    if width >= dp(600):
        return SIZE_MEDIUM
    return SIZE_COMPACT


def is_split_class(size_class: str) -> bool:
    return size_class in (SIZE_MEDIUM, SIZE_EXPANDED)


def metrics_for_class(size_class: str) -> UIMetrics:
    if size_class == SIZE_EXPANDED:
        return UIMetrics(
            size_class=SIZE_EXPANDED,
            screen_pad_h=dp(20),
            screen_pad_v=dp(14),
            gap_xs=dp(4),
            gap_sm=dp(8),
            gap_md=dp(14),
            gap_lg=dp(18),
            font_scale=1.06,
            shell_height=dp(94),
            shell_title_h=dp(24),
            shell_tabs_h=dp(44),
            shell_tab_btn_h=dp(36),
            card_radius=dp(13),
            section_radius=dp(12),
            tab_radius=dp(11),
            control_radius=dp(10),
            chip_radius=dp(9),
            icon_radius=dp(10),
            bubble_ratio=0.64,
            bubble_min=dp(220),
            engine_collapsed_h=dp(28),
            engine_expanded_h=dp(78),
            input_zone_h=dp(72),
            attach_strip_h=dp(62),
            docs_summary_h=dp(82),
            control_h=dp(40),
            icon_button_h=dp(40),
            send_button_h=dp(32),
            mode_button_h=dp(32),
            mode_toggle_w=dp(146),
            split_primary_ratio=0.7,
        )

    if size_class == SIZE_MEDIUM:
        return UIMetrics(
            size_class=SIZE_MEDIUM,
            screen_pad_h=dp(14),
            screen_pad_v=dp(10),
            gap_xs=dp(4),
            gap_sm=dp(8),
            gap_md=dp(12),
            gap_lg=dp(16),
            font_scale=1.0,
            shell_height=dp(86),
            shell_title_h=dp(22),
            shell_tabs_h=dp(42),
            shell_tab_btn_h=dp(34),
            card_radius=dp(12),
            section_radius=dp(10),
            tab_radius=dp(10),
            control_radius=dp(9),
            chip_radius=dp(8),
            icon_radius=dp(9),
            bubble_ratio=0.72,
            bubble_min=dp(184),
            engine_collapsed_h=dp(26),
            engine_expanded_h=dp(72),
            input_zone_h=dp(68),
            attach_strip_h=dp(60),
            docs_summary_h=dp(76),
            control_h=dp(38),
            icon_button_h=dp(38),
            send_button_h=dp(30),
            mode_button_h=dp(30),
            mode_toggle_w=dp(136),
            split_primary_ratio=0.67,
        )

    return UIMetrics(
        size_class=SIZE_COMPACT,
        screen_pad_h=dp(8),
        screen_pad_v=dp(8),
        gap_xs=dp(3),
        gap_sm=dp(6),
        gap_md=dp(10),
        gap_lg=dp(12),
        font_scale=0.96,
        shell_height=dp(78),
        shell_title_h=dp(20),
        shell_tabs_h=dp(40),
        shell_tab_btn_h=dp(32),
        card_radius=dp(10),
        section_radius=dp(8),
        tab_radius=dp(9),
        control_radius=dp(8),
        chip_radius=dp(7),
        icon_radius=dp(8),
        bubble_ratio=0.82,
        bubble_min=dp(152),
        engine_collapsed_h=dp(24),
        engine_expanded_h=dp(64),
        input_zone_h=dp(64),
        attach_strip_h=dp(54),
        docs_summary_h=dp(68),
        control_h=dp(36),
        icon_button_h=dp(36),
        send_button_h=dp(30),
        mode_button_h=dp(28),
        mode_toggle_w=dp(124),
        split_primary_ratio=1.0,
    )


def current_metrics() -> UIMetrics:
    return metrics_for_class(width_class())
