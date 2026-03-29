"""Pure mode-routing helpers for chat behavior."""
from __future__ import annotations

CHAT_MODE_GENERAL = "general"
CHAT_MODE_DOCUMENT = "document"

QUIT_RAG_ALIASES = {
    "quit rag",
    "exit rag",
    "/quit rag",
    "/exit rag",
}


def normalize_mode(mode: str) -> str:
    if mode == CHAT_MODE_DOCUMENT:
        return CHAT_MODE_DOCUMENT
    return CHAT_MODE_GENERAL


def is_quit_rag_alias(text: str) -> bool:
    return text.strip().lower() in QUIT_RAG_ALIASES


def resolve_send_mode(selected_mode: str, has_documents: bool) -> tuple[str, bool, str]:
    """Return (normalized_mode, can_send, message)."""
    mode = normalize_mode(selected_mode)
    if mode == CHAT_MODE_DOCUMENT and not has_documents:
        return (
            mode,
            False,
            "Document mode needs at least one indexed PDF or TXT. Open Documents tab to add one.",
        )
    return mode, True, ""


def mode_title(mode: str) -> str:
    mode = normalize_mode(mode)
    return "Document Q&A" if mode == CHAT_MODE_DOCUMENT else "General Chat"
