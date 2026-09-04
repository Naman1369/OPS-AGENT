"""Retrieval Agent node tests -- semantic search and the grounding decision."""

from __future__ import annotations

from ops_agent.agents.retrieval import retrieval_node
from ops_agent.config import RetrievalSettings
from ops_agent.state import new_state


def _state(query: str) -> dict:
    state = new_state("ticket body")
    state["retrieval_query"] = query
    state["keywords"] = query.split()
    return state


def test_context_documents_are_appended_to_state(store, retrieval_settings):
    update = retrieval_node(_state("vpn error 809 l2tp ipsec nat"), store=store, settings=retrieval_settings)
    assert update["retrieved_docs"]
    assert update["grounded"] is True
    assert update["top_relevance"] > 0.0


def test_documents_carry_the_fields_the_resolution_agent_needs(store, retrieval_settings):
    update = retrieval_node(_state("printer spooler print queue stuck"), store=store, settings=retrieval_settings)
    doc = update["retrieved_docs"][0]
    for field in ("doc_id", "title", "content", "score", "rank"):
        assert field in doc
    assert doc["rank"] == 1


def test_results_are_ranked_by_descending_relevance(store, retrieval_settings):
    update = retrieval_node(_state("outlook ost profile corruption"), store=store, settings=retrieval_settings)
    scores = [doc["score"] for doc in update["retrieved_docs"]]
    assert scores == sorted(scores, reverse=True)
    assert [doc["rank"] for doc in update["retrieved_docs"]] == list(range(1, len(scores) + 1))


def test_top_k_is_respected(store):
    settings = RetrievalSettings()
    object.__setattr__(settings, "top_k", 2)
    update = retrieval_node(_state("vpn connection failure"), store=store, settings=settings)
    assert len(update["retrieved_docs"]) <= 2


def test_relevance_threshold_filters_weak_matches(store):
    """A threshold of 1.0 admits nothing, so grounding must be False."""
    settings = RetrievalSettings()
    object.__setattr__(settings, "min_relevance", 1.01)
    update = retrieval_node(_state("vpn error 809"), store=store, settings=settings)
    assert update["retrieved_docs"] == []
    assert update["grounded"] is False


def test_empty_query_is_not_grounded(store, retrieval_settings):
    state = new_state("")
    state["retrieval_query"] = ""
    state["keywords"] = []
    update = retrieval_node(state, store=store, settings=retrieval_settings)
    assert update["grounded"] is False
    assert update["errors"]


def test_store_failure_degrades_instead_of_raising(retrieval_settings):
    class BrokenStore:
        def similarity_search(self, query, top_k=4):
            raise RuntimeError("index unreadable")

    update = retrieval_node(_state("vpn"), store=BrokenStore(), settings=retrieval_settings)
    assert update["grounded"] is False
    assert update["errors"]
    assert update["agent_trace"][0]["error"]
