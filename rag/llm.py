"""Compatibility shim for app.rag.llm."""
from __future__ import annotations

import warnings

warnings.warn(
    "`rag.llm` is deprecated; use `app.rag.llm`.",
    DeprecationWarning,
    stacklevel=2,
)

from app.rag.llm import *  # noqa: F401,F403
