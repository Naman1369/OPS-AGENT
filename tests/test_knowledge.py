"""Knowledge base loading, embedding and semantic search tests."""

from __future__ import annotations

from ops_agent.knowledge.embeddings import TfidfEmbedder
from ops_agent.state import CATEGORIES


def test_corpus_loads_with_complete_frontmatter(kb_documents):
    assert len(kb_documents) >= 20
    for doc in kb_documents:
        assert doc.doc_id.startswith("KB-")
        assert doc.title
        assert doc.category in CATEGORIES
        assert doc.tags
        assert doc.body


def test_doc_ids_are_unique(kb_documents):
    ids = [doc.doc_id for doc in kb_documents]
    assert len(ids) == len(set(ids))


def test_every_category_that_matters_is_represented(kb_documents):
    categories = {doc.category for doc in kb_documents}
    assert {"network", "access", "email", "hardware", "software", "security", "data_loss"} <= categories


def test_tfidf_embedder_is_deterministic_and_normalised(kb_documents):
    embedder = TfidfEmbedder().fit([doc.embedding_text() for doc in kb_documents])
    first = embedder.embed_one("vpn error 809")
    assert first == embedder.embed_one("vpn error 809")
    assert len(first) == embedder.dimension > 0
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6


def test_tfidf_ranks_a_matching_article_above_an_unrelated_one(store):
    """The fallback must still rank meaningfully, not return noise."""
    results = store.similarity_search("vpn error 809 cannot connect l2tp", top_k=3)
    assert results[0]["doc_id"] == "KB-0001"


def test_unfitted_tfidf_returns_an_empty_vector():
    assert TfidfEmbedder().embed_one("anything") == []


def test_store_indexes_the_whole_corpus(store, kb_documents):
    assert store.count() == len(kb_documents)


def test_similarity_search_returns_ranked_scored_documents(store):
    results = store.similarity_search("printer print queue spooler stuck", top_k=3)
    assert results
    assert all(0.0 <= doc["score"] <= 1.0 for doc in results)
    assert [doc["rank"] for doc in results] == list(range(1, len(results) + 1))


def test_tied_results_are_broken_deterministically(store, kb_documents):
    """A query sharing no vocabulary ties every article at similarity 0; the order
    must then come from the doc id, not from Chroma's process-dependent tie order."""
    results = store.similarity_search("zxqv blorf quux", top_k=4)
    expected = sorted(doc.doc_id for doc in kb_documents)[:4]
    assert [doc["doc_id"] for doc in results] == expected
    assert all(doc["score"] == 0.0 for doc in results)


def test_ingestion_is_idempotent(store, kb_documents):
    before = store.count()
    store.add_documents(kb_documents)
    assert store.count() == before


def test_empty_query_returns_nothing(store):
    assert store.similarity_search("   ", top_k=3) == []


def test_a_stale_persisted_index_is_detected_and_rebuilt(tmp_path, kb_documents):
    """An index built with one embedder must never be queried with another."""
    import pytest

    from ops_agent.knowledge.vector_store import VectorStore

    first = VectorStore("kb_stale_test", TfidfEmbedder(), persist_dir=tmp_path)
    first.add_documents(kb_documents)

    class OtherEmbedder:
        name, dimension = "other-model", 8

        def embed(self, texts):
            return [[0.1] * 8 for _ in texts]

        def embed_one(self, text):
            return [0.1] * 8

    with pytest.raises(RuntimeError, match="Rebuild"):
        VectorStore("kb_stale_test", OtherEmbedder(), persist_dir=tmp_path)
    rebuilt = VectorStore("kb_stale_test", OtherEmbedder(), persist_dir=tmp_path, rebuild_on_mismatch=True)
    assert rebuilt.count() == 0  # dropped, ready to be re-ingested
