from app.rag.chunker import CHUNK_OVERLAP, chunk_text, tokenise


def test_chunk_text_deterministic_and_overlapping() -> None:
    text = " ".join(f"w{i}" for i in range(220))

    first = chunk_text(text)
    second = chunk_text(text)

    assert first == second
    assert len(first) >= 3

    left = first[0].split()
    right = first[1].split()
    assert left[-CHUNK_OVERLAP:] == right[:CHUNK_OVERLAP]


def test_tokenise_drops_stopwords_and_short_tokens() -> None:
    tokens = tokenise("This is a tiny test of RAG tokenisation, with AI and data.")

    assert "this" not in tokens
    assert "is" not in tokens
    assert "a" not in tokens
    assert "tiny" in tokens
    assert "tokenisation" in tokens

