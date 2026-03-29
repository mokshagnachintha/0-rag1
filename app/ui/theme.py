"""Shared design tokens for the Android-first Kivy UI."""
from __future__ import annotations

from kivy.metrics import dp, sp


class Theme:
    BG = (0.070, 0.082, 0.106, 1)           # #12151b
    SURFACE = (0.102, 0.118, 0.153, 1)      # #1a1e27
    SURFACE_ALT = (0.129, 0.149, 0.188, 1)  # #212630
    BORDER = (0.302, 0.341, 0.408, 1)       # #4d5768
    TEXT = (0.949, 0.965, 0.992, 1)         # #f2f6fd
    TEXT_MUTED = (0.667, 0.718, 0.792, 1)   # #aab7ca

    PRIMARY = (0.271, 0.698, 0.949, 1)      # #45b2f2
    PRIMARY_DARK = (0.165, 0.525, 0.745, 1)
    SUCCESS = (0.322, 0.788, 0.529, 1)
    WARNING = (0.933, 0.729, 0.345, 1)
    DANGER = (0.949, 0.369, 0.369, 1)

    USER_BUBBLE = (0.176, 0.208, 0.267, 1)
    ASSISTANT_BUBBLE = (0.106, 0.133, 0.176, 1)


class Radius:
    XS = dp(6)
    SM = dp(8)
    MD = dp(10)
    LG = dp(12)
    PILL = dp(14)


class Space:
    XS = dp(6)
    SM = dp(10)
    MD = dp(14)
    LG = dp(18)


class TypeScale:
    XS = sp(11)
    SM = sp(12)
    MD = sp(14)
    LG = sp(16)
    XL = sp(18)


MIN_TOUCH = dp(44)
