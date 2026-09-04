"""Retrieval Agent -- semantic similarity search over the knowledge base.

This node owns the grounding decision. It sets ``grounded``, and the graph uses
that flag to keep the Resolution Agent away from tickets with no evidence behind
them (CLAUDE.md: never generate an answer without grounding it in retrieved
context).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import RetrievalSettings, SETTINGS
from ..state import OpsAgentState, RetrievedDoc, trace_event

logger = logging.getLogger(__name__)

AGENT_NAME = "retrieval"


def retrieval_node(
    state: OpsAgentState,
    store: Any | None = None,
    settings: RetrievalSettings | None = None,
) -> dict[str, Any]:
    """LangGraph node: fetch and rank supporting evidence for the ticket."""
    started = time.perf_counter()
    settings = settings or SETTINGS.retrieval

    query = (state.get("retrieval_query") or "").strip()
    if not query:
        query = " ".join(state.get("keywords") or []) or (state.get("raw_text") or "")

    if not query.strip():
        return _empty(
            "retrieval: no usable query could be built from the triaged ticket",
            started,
            query,
        )

    if store is None:
        from ..knowledge import get_store

        try:
            store = get_store(settings)
        except Exception as exc:  # index missing or unreadable
            logger.error("Vector store unavailable: %s", exc)
            return _empty(f"retrieval: vector store unavailable ({exc})", started, query)

    try:
        candidates: list[RetrievedDoc] = store.similarity_search(query, top_k=settings.top_k)
    except Exception as exc:  # pragma: no cover - backend dependent
        logger.error("Similarity search failed: %s", exc)
        return _empty(f"retrieval: similarity search failed ({exc})", started, query)

    # Relevance filter: weak matches are worse than no matches, because they
    # give the Resolution Agent something plausible-looking to anchor on.
    usable = [doc for doc in candidates if float(doc.get("score", 0.0)) >= settings.min_relevance]
    for rank, doc in enumerate(usable, start=1):
        doc["rank"] = rank

    top_relevance = max((float(doc.get("score", 0.0)) for doc in candidates), default=0.0)
    grounded = bool(usable)

    latency_ms = (time.perf_counter() - started) * 1000.0
    return {
        "current_agent": AGENT_NAME,
        "retrieved_docs": usable,
        "top_relevance": round(top_relevance, 4),
        "grounded": grounded,
        "errors": [],
        "agent_trace": [
            trace_event(
                AGENT_NAME,
                "retrieved" if grounded else "no_usable_evidence",
                {
                    "query": query,
                    "top_k": settings.top_k,
                    "min_relevance": settings.min_relevance,
                    "candidates_returned": len(candidates),
                    "usable_documents": len(usable),
                    "doc_ids": [doc.get("doc_id") for doc in usable],
                    "scores": [doc.get("score") for doc in usable],
                    "top_relevance": round(top_relevance, 4),
                    "grounded": grounded,
                },
                latency_ms=latency_ms,
            )
        ],
    }


def _empty(reason: str, started: float, query: str) -> dict[str, Any]:
    latency_ms = (time.perf_counter() - started) * 1000.0
    return {
        "current_agent": AGENT_NAME,
        "retrieved_docs": [],
        "top_relevance": 0.0,
        "grounded": False,
        "errors": [reason],
        "agent_trace": [
            trace_event(
                AGENT_NAME,
                "no_usable_evidence",
                {"query": query, "grounded": False},
                latency_ms=latency_ms,
                error=reason,
            )
        ],
    }
