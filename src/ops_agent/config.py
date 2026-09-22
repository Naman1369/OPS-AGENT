"""Central configuration for OPS-AGENT.

Every tunable knob lives here so that agents, the graph and the tests all read
the same values.  Values are sourced from environment variables (optionally via
a local ``.env`` file) and fall back to safe, offline-friendly defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional dependency -- absence must not break the pipeline
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - trivial fallback
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(key: str, default: str) -> str:
    value = os.getenv(key)
    return default if value is None or value == "" else value


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else (PROJECT_ROOT / path)


@dataclass(frozen=True)
class LLMSettings:
    """Which language model backend the reasoning agents talk to."""

    provider: str = field(default_factory=lambda: _env("OPS_LLM_PROVIDER", ""))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY", ""))
    # gemini-1.5-* models are retired. gemini-2.5-flash is a stable model that
    # still accepts temperature=0 and a zero thinking budget, which is what a
    # reproducible evaluation needs. Any current model ID can be set in .env.
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash"))
    gemini_thinking_budget: int = field(default_factory=lambda: _env_int("OPS_GEMINI_THINKING_BUDGET", 0))
    gemini_thinking_level: str = field(default_factory=lambda: _env("OPS_GEMINI_THINKING_LEVEL", "low"))
    ollama_base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.1:8b"))
    temperature: float = field(default_factory=lambda: _env_float("OPS_LLM_TEMPERATURE", 0.0))
    max_output_tokens: int = field(default_factory=lambda: _env_int("OPS_LLM_MAX_TOKENS", 1536))

    def resolved_provider(self) -> str:
        """Explicit selection wins; otherwise prefer Gemini only if a key exists."""
        if self.provider:
            return self.provider.strip().lower()
        if self.gemini_api_key:
            return "gemini"
        return "mock"


@dataclass(frozen=True)
class RetrievalSettings:
    """Knowledge base and semantic search configuration."""

    kb_dir: Path = field(default_factory=lambda: _resolve(_env("OPS_KB_DIR", "data/knowledge_base")))
    chroma_dir: Path = field(default_factory=lambda: _resolve(_env("OPS_CHROMA_DIR", "data/chroma")))
    collection_name: str = field(default_factory=lambda: _env("OPS_COLLECTION_NAME", "ops_agent_kb"))
    embedding_model: str = field(
        default_factory=lambda: _env("OPS_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    # Optional local directory holding a copy of the embedding model, for
    # air-gapped machines. The model's identity is still ``embedding_model``.
    embedding_model_path: str = field(default_factory=lambda: _env("OPS_EMBEDDING_MODEL_PATH", ""))
    # "auto" (transformer, else TF-IDF), "minilm" (transformer only) or "tfidf".
    embedder_backend: str = field(default_factory=lambda: _env("OPS_EMBEDDER", "auto"))
    top_k: int = field(default_factory=lambda: _env_int("OPS_RETRIEVAL_TOP_K", 4))
    # A document below this cosine similarity is not trustworthy grounding evidence.
    min_relevance: float = field(default_factory=lambda: _env_float("OPS_MIN_RELEVANCE", 0.25))


@dataclass(frozen=True)
class GovernanceSettings:
    """Deterministic governance thresholds.

    ``confidence_threshold`` is the NAIVE threshold applied to the raw
    confidence (the Week 5-7 behaviour, kept as the naively-governed baseline).
    In calibrated mode check G3 instead reads the temperature-scaled confidence
    and the threshold selected on the calibration split, both stored in the
    calibration profile at ``calibration_path``. Every other check is identical
    in both modes.
    """

    # "auto": calibrated when a profile exists and matches the running
    # configuration, raw otherwise. "calibrated" / "raw" force a mode.
    mode: str = field(default_factory=lambda: _env("OPS_GOVERNANCE_MODE", "auto").strip().lower())
    # A profile file, or a directory of profiles (one per configuration); the
    # pipeline applies the profile whose fingerprint matches what is running.
    calibration_path: Path = field(
        default_factory=lambda: _resolve(_env("OPS_CALIBRATION_PATH", "artifacts/calibration"))
    )
    # Target Unsafe Resolution Rate (alpha: the fraction of all tickets that may
    # be resolved autonomously AND unsafely) and the tolerated probability that
    # the guarantee fails (delta), used when selecting the G3 threshold.
    risk_alpha: float = field(default_factory=lambda: _env_float("OPS_RISK_ALPHA", 0.05))
    risk_delta: float = field(default_factory=lambda: _env_float("OPS_RISK_DELTA", 0.10))
    confidence_threshold: float = field(default_factory=lambda: _env_float("OPS_CONFIDENCE_THRESHOLD", 0.70))
    min_citations: int = field(default_factory=lambda: _env_int("OPS_MIN_CITATIONS", 1))
    min_evidence_score: float = field(default_factory=lambda: _env_float("OPS_MIN_EVIDENCE_SCORE", 0.25))
    # Priorities that a human must always sign off on, whatever the confidence.
    always_escalate_priorities: tuple[str, ...] = ("P1",)
    # Categories with blast radius / compliance exposure always go to a human.
    always_escalate_categories: tuple[str, ...] = ("security", "data_loss")


@dataclass(frozen=True)
class AuditSettings:
    """Where the append-only, hash-chained audit trail lives (Week 10-12)."""

    db_path: Path = field(default_factory=lambda: _resolve(_env("OPS_AUDIT_DB", "data/audit/audit.sqlite3")))
    enabled: bool = field(
        default_factory=lambda: _env("OPS_AUDIT_ENABLED", "true").strip().lower() in ("1", "true", "yes")
    )


@dataclass(frozen=True)
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    governance: GovernanceSettings = field(default_factory=GovernanceSettings)
    audit: AuditSettings = field(default_factory=AuditSettings)


def get_settings() -> Settings:
    """Build a fresh Settings object (re-reads the environment)."""
    return Settings()


SETTINGS = get_settings()
