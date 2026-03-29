"""Compatibility shim for app.ui.docs.docs_screen."""
from __future__ import annotations

import importlib
import warnings

warnings.warn(
    "`ui.screens.docs_screen` is deprecated; use `app.ui.docs.docs_screen`.",
    DeprecationWarning,
    stacklevel=2,
)

_TARGET = "app.ui.docs.docs_screen"


def __getattr__(name: str):
    return getattr(importlib.import_module(_TARGET), name)


def __dir__():
    module = importlib.import_module(_TARGET)
    return sorted(set(globals().keys()) | set(dir(module)))
