"""Embedding backends for semantic similarity search.

Primary backend is a local sentence-transformers model (all-MiniLM-L6-v2).
It runs offline once the model is cached, costs nothing, and returns identical
vectors on every run -- which is what makes execution traces replayable in the
later evaluation phases.

``TfidfEmbedder`` is the dependency-free fallback used when
sentence-transformers (or its model download) is unavailable, for example in a
locked-down CI container or an air-gapped machine. It is a classical lexical
vector model: weaker than a transformer on paraphrase, but it keeps ranking
meaningful so the pipeline degrades gracefully instead of returning noise.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_.]*")

_STOPWORDS = frozenset(
    """a an and are as at be been but by can cannot could did do does for from had has have
    if in into is it its of on or that the their then there these they this to was were what
    when which who will with would you your not no""".split()
)


@runtime_checkable
class Embedder(Protocol):
    """Anything that turns text into a fixed-length vector."""

    name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]: ...


def _tokenize(text: str) -> list[str]:
    """Unigrams plus adjacent bigrams, so phrases like 'error 809' carry weight."""
    words = [
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOPWORDS and len(token) > 1
    ]
    bigrams = [f"{first}_{second}" for first, second in zip(words, words[1:])]
    return words + bigrams


class SentenceTransformerEmbedder:
    """Local transformer embeddings (default: all-MiniLM-L6-v2, 384 dimensions).

    ``model_path`` optionally points at a local copy of the same model (for an
    air-gapped machine). The embedder's ``name`` stays the model identity, so a
    calibration profile fitted with the downloaded model still matches.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        model_path: str | None = None,
    ) -> None:
        from sentence_transformers import SentenceTransformer  # imported lazily

        self._model = SentenceTransformer(str(model_path or model_name), device="cpu")
        self.name = model_name
        dimension = getattr(self._model, "get_embedding_dimension", None) or getattr(
            self._model, "get_sentence_embedding_dimension"
        )
        self.dimension = int(dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        return [vector.tolist() for vector in vectors]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class TfidfEmbedder:
    """Deterministic TF-IDF vectoriser over a fitted vocabulary.

    Vectors are L2-normalised, so the cosine distance Chroma computes is a
    genuine cosine similarity. ``fit`` is called automatically by the vector
    store when documents are indexed; querying before fitting degrades to plain
    term frequency rather than failing.
    """

    def __init__(self, max_features: int = 4096) -> None:
        self.name = "tfidf-fallback"
        self.max_features = max_features
        self.dimension = 0
        self._vocabulary: dict[str, int] = {}
        self._idf: list[float] = []

    @property
    def is_fitted(self) -> bool:
        return bool(self._vocabulary)

    def fit(self, corpus: Iterable[str]) -> "TfidfEmbedder":
        """Learn the vocabulary and inverse document frequencies."""
        documents = [_tokenize(text) for text in corpus]
        if not documents:
            return self

        document_frequency: Counter[str] = Counter()
        for tokens in documents:
            document_frequency.update(set(tokens))

        # Drop terms appearing in a single document only when the corpus is large
        # enough for that to be meaningful; small corpora need every signal.
        minimum_df = 2 if len(documents) >= 25 else 1
        selected = [
            term
            for term, count in document_frequency.most_common(self.max_features)
            if count >= minimum_df
        ]
        selected.sort()

        total_documents = len(documents)
        self._vocabulary = {term: index for index, term in enumerate(selected)}
        self._idf = [
            math.log((1 + total_documents) / (1 + document_frequency[term])) + 1.0
            for term in selected
        ]
        self.dimension = len(selected)
        return self

    def embed_one(self, text: str) -> list[float]:
        if not self.is_fitted:
            return []
        vector = [0.0] * self.dimension
        counts = Counter(_tokenize(text))
        for term, count in counts.items():
            index = self._vocabulary.get(term)
            if index is None:
                continue
            # Sublinear term frequency keeps repeated words from dominating.
            vector[index] = (1.0 + math.log(count)) * self._idf[index]

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]

    # -- persistence -------------------------------------------------------- #
    # A TF-IDF vector is only meaningful against the vocabulary it was fitted
    # on, so an index persisted to disk is unusable unless that vocabulary is
    # persisted with it. These two methods keep the pair in step.

    def save_state(self, path: Path | str) -> None:
        if not self.is_fitted:
            return
        Path(path).write_text(
            json.dumps({"vocabulary": self._vocabulary, "idf": self._idf}),
            encoding="utf-8",
        )

    def load_state(self, path: Path | str) -> bool:
        """Restore a previously fitted vocabulary. Returns True on success."""
        state_path = Path(path)
        if not state_path.exists():
            return False
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            vocabulary = payload["vocabulary"]
            idf = payload["idf"]
        except (json.JSONDecodeError, KeyError, OSError):
            return False
        if not vocabulary or len(idf) != len(vocabulary):
            return False
        self._vocabulary = {term: int(index) for term, index in vocabulary.items()}
        self._idf = [float(value) for value in idf]
        self.dimension = len(self._idf)
        return True


def get_embedder(model_name: str | None = None, backend: str | None = None) -> Embedder:
    """Return the configured embedder.

    ``backend`` is ``"auto"`` (transformer, else the TF-IDF fallback),
    ``"minilm"`` (transformer only; raises if it cannot load) or ``"tfidf"``.
    """
    from ..config import SETTINGS

    settings = SETTINGS.retrieval
    model_name = model_name or settings.embedding_model
    backend = (backend or settings.embedder_backend or "auto").strip().lower()

    if backend == "tfidf":
        return TfidfEmbedder()
    try:
        return SentenceTransformerEmbedder(model_name, settings.embedding_model_path or None)
    except Exception as exc:  # pragma: no cover - depends on the environment
        if backend in ("minilm", "transformer", "sentence-transformers"):
            raise RuntimeError(f"The transformer embedder could not be loaded: {exc}") from exc
        logger.warning(
            "sentence-transformers unavailable (%s); using the TF-IDF fallback. "
            "Retrieval quality will be lower than the transformer model.",
            str(exc)[:160],
        )
        return TfidfEmbedder()
