from app.rag.retriever import HybridRetriever


def _base_chunks() -> list[dict]:
    return [
        {
            "id": 1,
            "doc_id": 1,
            "chunk_idx": 0,
            "text": "chunk one",
            "tokens": ["apple", "banana"],
            "tfidf_vec": {"apple": 1.0, "banana": 0.5},
        },
        {
            "id": 2,
            "doc_id": 1,
            "chunk_idx": 1,
            "text": "chunk two",
            "tokens": ["apple", "banana"],
            "tfidf_vec": {"apple": 1.0, "banana": 0.5},
        },
    ]


def test_query_falls_back_when_semantic_missing() -> None:
    retriever = HybridRetriever(alpha=0.5)
    retriever._chunks = _base_chunks()
    retriever._avg_dl = 2.0
    retriever._semantic_scores = lambda _text: None  # type: ignore[method-assign]

    results = retriever.query("apple", top_k=1)

    assert len(results) == 1
    assert results[0][0] in {"chunk one", "chunk two"}


def test_query_uses_semantic_scores_when_available() -> None:
    retriever = HybridRetriever(alpha=0.5)
    retriever._chunks = _base_chunks()
    retriever._avg_dl = 2.0
    retriever._semantic_scores = lambda _text: [0.0, 1.0]  # type: ignore[method-assign]

    results = retriever.query("apple", top_k=1)

    assert len(results) == 1
    assert results[0][0] == "chunk two"
