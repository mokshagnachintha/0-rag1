from app.ui.chat.mode_logic import (
    CHAT_MODE_DOCUMENT,
    CHAT_MODE_GENERAL,
    is_quit_rag_alias,
    resolve_send_mode,
)


def test_document_mode_blocks_when_no_docs() -> None:
    mode, can_send, message = resolve_send_mode(CHAT_MODE_DOCUMENT, has_documents=False)

    assert mode == CHAT_MODE_DOCUMENT
    assert can_send is False
    assert "Document mode" in message


def test_document_mode_allows_when_docs_exist() -> None:
    mode, can_send, message = resolve_send_mode(CHAT_MODE_DOCUMENT, has_documents=True)

    assert mode == CHAT_MODE_DOCUMENT
    assert can_send is True
    assert message == ""


def test_unknown_mode_defaults_to_general() -> None:
    mode, can_send, _ = resolve_send_mode("something-else", has_documents=False)

    assert mode == CHAT_MODE_GENERAL
    assert can_send is True


def test_quit_aliases_are_detected_case_insensitive() -> None:
    assert is_quit_rag_alias("QUIT RAG") is True
    assert is_quit_rag_alias("/exit rag") is True
    assert is_quit_rag_alias("exit") is False
