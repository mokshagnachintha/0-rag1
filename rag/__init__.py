"""Compatibility shim: use app.rag package."""
from __future__ import annotations

import warnings

warnings.warn(
    "`rag` package is deprecated; use `app.rag` instead.",
    DeprecationWarning,
    stacklevel=2,
)

from app.rag.pipeline import (  # noqa: F401
    ask,
    chat_direct,
    clear_all_documents,
    get_available_models,
    ingest_document,
    init,
    is_model_loaded,
    load_model,
    register_auto_download_callbacks,
    retriever,
)
