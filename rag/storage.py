"""Compatibility shim for app.rag.storage."""
from __future__ import annotations

import warnings

warnings.warn(
    "`rag.storage` is deprecated; use `app.rag.storage`.",
    DeprecationWarning,
    stacklevel=2,
)

from app.rag.storage import *  # noqa: F401,F403
