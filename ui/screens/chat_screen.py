"""Compatibility shim for app.ui.chat.chat_screen."""
from __future__ import annotations

import warnings

warnings.warn(
    "`ui.screens.chat_screen` is deprecated; use `app.ui.chat.chat_screen`.",
    DeprecationWarning,
    stacklevel=2,
)

from app.ui.chat.chat_screen import *  # noqa: F401,F403
