"""Compatibility shim for app.rag.downloader."""
from __future__ import annotations

import warnings

warnings.warn(
    "`rag.downloader` is deprecated; use `app.rag.downloader`.",
    DeprecationWarning,
    stacklevel=2,
)

from app.rag.downloader import *  # noqa: F401,F403
