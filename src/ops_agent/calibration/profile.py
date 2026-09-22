"""The calibration profile: everything calibrated governance needs, in one file.

A profile holds the fitted temperature, the risk-controlled G3 threshold, the
metrics that justified them, and a FINGERPRINT of the configuration they were
fitted for. Calibration is specific to the model that produced the scores, the
retrieval stack that shaped them and the prompts that elicited them; a profile
fitted for one configuration says nothing about another. So a profile is only
applied when the running configuration matches its fingerprint. Otherwise the
pipeline falls back to raw governance and records why.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .temperature import TemperatureScaler

PROFILE_SCHEMA_VERSION = 1

# Fingerprint keys that must match for a profile to apply.
FINGERPRINT_KEYS = (
    "provider",
    "model",
    "embedder",
    "intake_prompt",
    "resolution_prompt",
    "kb_hash",
    "top_k",
    "min_relevance",
)


def _plain(value: Any) -> Any:
    """JSON fallback for numpy scalars that reach the profile metrics."""
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def kb_fingerprint(kb_dir: Path | str) -> str:
    """Stable hash of the knowledge base contents (file names and bytes)."""
    digest = hashlib.sha256()
    for path in sorted(Path(kb_dir).glob("*.md")):
        digest.update(path.name.encode("utf-8"))
        # Normalise line endings so a Windows checkout hashes the same.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]


def pipeline_fingerprint(
    provider_name: str,
    provider_model: str,
    embedder_name: str,
    kb_dir: Path | str,
    top_k: int,
    min_relevance: float,
) -> dict[str, Any]:
    """Describe the configuration whose confidence scores are being calibrated."""
    from ..prompts import intake, resolution

    return {
        "provider": provider_name,
        "model": provider_model,
        "embedder": embedder_name,
        "intake_prompt": intake.PROMPT_VERSION,
        "resolution_prompt": resolution.PROMPT_VERSION,
        "kb_hash": kb_fingerprint(kb_dir),
        "top_k": int(top_k),
        "min_relevance": float(min_relevance),
    }


@dataclass
class CalibrationProfile:
    temperature: float
    threshold: float
    alpha: float
    delta: float
    feasible: bool
    fingerprint: dict[str, Any]
    method: str = "temperature-scaling"
    threshold_method: str = "ltt"
    metrics: dict[str, Any] = field(default_factory=dict)
    split: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    schema_version: int = PROFILE_SCHEMA_VERSION

    # ------------------------------------------------------------------ #

    @property
    def profile_id(self) -> str:
        """Content hash of the parameters that change decisions."""
        core = json.dumps(
            {
                "temperature": round(self.temperature, 10),
                "threshold": round(self.threshold, 10),
                "fingerprint": self.fingerprint,
            },
            sort_keys=True,
        )
        return hashlib.sha256(core.encode("utf-8")).hexdigest()[:12]

    def transform(self, raw_confidence: float) -> float:
        return float(TemperatureScaler(temperature=self.temperature, fitted=True).transform(float(raw_confidence)))

    def matches(self, fingerprint: dict[str, Any]) -> tuple[bool, list[str]]:
        mismatched = [
            key
            for key in FINGERPRINT_KEYS
            if str(self.fingerprint.get(key)) != str(fingerprint.get(key))
        ]
        return (not mismatched), mismatched

    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["profile_id"] = self.profile_id
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CalibrationProfile":
        data = dict(payload)
        data.pop("profile_id", None)
        return cls(**data)

    def save(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, default=_plain) + "\n", encoding="utf-8")
        return target


def load_profile(path: Path | str) -> CalibrationProfile | None:
    """Read one profile file; ``None`` when absent or unreadable."""
    source = Path(path)
    if not source.is_file():
        return None
    try:
        return CalibrationProfile.from_dict(json.loads(source.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        return None


def load_profiles(path: Path | str) -> list[CalibrationProfile]:
    """All profiles at ``path``: a single JSON file, or every ``*.json`` in a directory.

    Several profiles can coexist - one per configuration (for example one for
    the MiniLM embedder and one for the TF-IDF fallback used in the container
    image) - and the pipeline applies the one whose fingerprint matches.
    """
    source = Path(path)
    files = sorted(source.glob("*.json")) if source.is_dir() else [source]
    profiles = [load_profile(file) for file in files]
    return [profile for profile in profiles if profile is not None]


def select_profile(
    profiles: list[CalibrationProfile], fingerprint: dict[str, Any]
) -> tuple[CalibrationProfile | None, dict[str, list[str]]]:
    """The first profile matching ``fingerprint``, plus why the others did not."""
    mismatches: dict[str, list[str]] = {}
    for profile in profiles:
        matches, mismatched = profile.matches(fingerprint)
        if matches:
            return profile, mismatches
        mismatches[profile.profile_id] = mismatched
    return None, mismatches
