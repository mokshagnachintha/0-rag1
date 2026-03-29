"""Compatibility shim for app.rag.pipeline."""
from __future__ import annotations

import warnings

warnings.warn(
    "`rag.pipeline` is deprecated; use `app.rag.pipeline`.",
    DeprecationWarning,
    stacklevel=2,
)

from app.rag.pipeline import *  # noqa: F401,F403
