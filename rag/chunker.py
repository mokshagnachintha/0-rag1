"""Compatibility shim for app.rag.chunker."""
from __future__ import annotations

import warnings

warnings.warn(
    "`rag.chunker` is deprecated; use `app.rag.chunker`.",
    DeprecationWarning,
    stacklevel=2,
)

from app.rag.chunker import *  # noqa: F401,F403
