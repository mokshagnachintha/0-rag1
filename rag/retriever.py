"""Compatibility shim for app.rag.retriever."""
from __future__ import annotations

import warnings

warnings.warn(
    "`rag.retriever` is deprecated; use `app.rag.retriever`.",
    DeprecationWarning,
    stacklevel=2,
)

from app.rag.retriever import *  # noqa: F401,F403
