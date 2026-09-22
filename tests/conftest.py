"""Shared pytest fixtures.

Every test runs against the deterministic MockProvider and an in-memory Chroma
collection, so the suite needs no API key, no network and no pre-built index.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Hermetic by construction: settings are read when ops_agent is imported, so
# these must be set first. A developer's .env (a Gemini key, a calibration
# profile) must never change what the unit suite exercises. Tests that need
# calibrated governance or another provider pass them in explicitly.
os.environ["OPS_LLM_PROVIDER"] = "mock"
os.environ["OPS_GOVERNANCE_MODE"] = "raw"
os.environ["OPS_EMBEDDER"] = "tfidf"
os.environ["OPS_AUDIT_ENABLED"] = "false"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ops_agent.config import GovernanceSettings, RetrievalSettings, SETTINGS  # noqa: E402
from ops_agent.knowledge.embeddings import TfidfEmbedder  # noqa: E402
from ops_agent.knowledge.loader import load_knowledge_base  # noqa: E402
from ops_agent.knowledge.vector_store import (  # noqa: E402
    VectorStore,
    reset_store_cache,
    set_default_store,
)
from ops_agent.llm import MockProvider  # noqa: E402
from ops_agent.state import new_state  # noqa: E402

VPN_TICKET = "User cannot connect to the VPN, error code 809"


@pytest.fixture(scope="session")
def provider() -> MockProvider:
    return MockProvider()


@pytest.fixture(scope="session")
def kb_documents():
    return load_knowledge_base(SETTINGS.retrieval.kb_dir)


@pytest.fixture(scope="session")
def store(kb_documents) -> VectorStore:
    """Ephemeral in-memory Chroma collection seeded with the real corpus.

    The TF-IDF embedder is used deliberately: it needs no model download, so
    the unit suite stays fast and hermetic. The transformer embedder is
    exercised by scripts/verify_pipeline.py on a developer machine.
    """
    vector_store = VectorStore(
        collection_name="ops_agent_kb_test",
        embedder=TfidfEmbedder(),
        persist_dir=None,
    )
    vector_store.add_documents(kb_documents)
    return vector_store


@pytest.fixture
def retrieval_settings() -> RetrievalSettings:
    return RetrievalSettings()


@pytest.fixture
def governance_settings() -> GovernanceSettings:
    return GovernanceSettings()


@pytest.fixture
def vpn_state():
    return new_state(VPN_TICKET, ticket_id="TCK-TEST-VPN")


def merge(state: dict, update: dict) -> dict:
    """Mimic LangGraph's channel merge for tests that chain nodes by hand."""
    merged = {**state, **update}
    merged["agent_trace"] = list(state.get("agent_trace", [])) + list(update.get("agent_trace", []))
    merged["errors"] = list(state.get("errors", [])) + list(update.get("errors", []))
    return merged


@pytest.fixture(scope="session", autouse=True)
def _use_in_memory_store(store):
    """Make the compiled graph resolve to the in-memory test collection.

    Graph tests must not depend on a persisted index existing on disk, and must
    never read or write the developer's real one.
    """
    set_default_store(store)
    yield
    reset_store_cache()
