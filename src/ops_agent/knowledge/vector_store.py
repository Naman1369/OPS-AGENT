"""ChromaDB-backed semantic search over the IT knowledge base.

The Retrieval Agent talks only to :class:`VectorStore`, so the vector backend
can be swapped (Chroma to FAISS) without touching agent code.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import RetrievalSettings, SETTINGS
from ..state import RetrievedDoc
from .embeddings import Embedder, get_embedder
from .loader import KBDocument, load_knowledge_base

logger = logging.getLogger(__name__)

# How many nearest neighbours are fetched before the deterministic re-rank in
# similarity_search. At or above the collection size the ranking is exact.
CANDIDATE_POOL = 64


class VectorStore:
    """Thin wrapper over a Chroma collection using externally supplied embeddings."""

    def __init__(
        self,
        collection_name: str,
        embedder: Embedder,
        persist_dir: Path | str | None = None,
        rebuild_on_mismatch: bool = False,
    ) -> None:
        import chromadb  # imported lazily so importing the package stays cheap

        self.embedder = embedder
        self.collection_name = collection_name

        if persist_dir is None:
            self._client = chromadb.EphemeralClient()
            self.persist_dir = None
            self._embedder_state_path = None
        else:
            self.persist_dir = Path(persist_dir)
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._embedder_state_path = self.persist_dir / f"{collection_name}.embedder.json"

        self._collection = self._open_collection()

        # A lexical embedder's vectors mean nothing without the vocabulary they
        # were fitted on, so restore it alongside a persisted collection.
        if self._embedder_state_path is not None:
            loader = getattr(self.embedder, "load_state", None)
            if callable(loader) and loader(self._embedder_state_path):
                logger.debug("Restored embedder state from %s", self._embedder_state_path)

        # Vectors from two different embedders are not comparable, and an index
        # of one dimension cannot be queried with vectors of another. A stale
        # persisted index is a cache that no longer matches its source, so it is
        # dropped here and re-ingested by get_store(), with a warning.
        stale = self._stale_reason()
        if stale:
            if not rebuild_on_mismatch:
                raise RuntimeError(f"{stale} Rebuild it: python scripts/ingest_kb.py --rebuild")
            logger.warning("%s Dropping the stale index so it is rebuilt from the knowledge base.", stale)
            self._client.delete_collection(collection_name)
            self._collection = self._open_collection()

    def _open_collection(self):
        # Cosine space so that similarity = 1 - distance lands in a readable range.
        return self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine", "embedder": str(getattr(self.embedder, "name", "unknown"))},
        )

    def _stale_reason(self) -> str | None:
        if self._collection.count() == 0:
            return None
        current = str(getattr(self.embedder, "name", "unknown"))
        built_with = (self._collection.metadata or {}).get("embedder")
        if built_with and built_with != current:
            return f"Collection {self.collection_name!r} was built with embedder {built_with!r}, not {current!r}."
        sample = self._collection.get(limit=1, include=["embeddings"])
        embeddings = sample.get("embeddings")
        stored = len(embeddings[0]) if embeddings is not None and len(embeddings) else 0
        expected = int(getattr(self.embedder, "dimension", 0) or 0)
        if stored and stored != expected:
            return (
                f"Collection {self.collection_name!r} holds {stored}-dimensional vectors but the active "
                f"embedder {current!r} produces {expected or 'unknown'}-dimensional ones."
            )
        return None

    # ------------------------------------------------------------------ #

    def count(self) -> int:
        return int(self._collection.count())

    def add_documents(self, documents: list[KBDocument]) -> int:
        """Embed and upsert articles. Upsert keeps re-ingestion idempotent."""
        if not documents:
            return 0
        texts = [doc.embedding_text() for doc in documents]
        # Lexical embedders (the TF-IDF fallback) need corpus statistics before
        # they can produce vectors; transformer embedders have no fit step.
        fit = getattr(self.embedder, "fit", None)
        if callable(fit):
            fit(texts)
            saver = getattr(self.embedder, "save_state", None)
            if callable(saver) and self._embedder_state_path is not None:
                saver(self._embedder_state_path)
        embeddings = self.embedder.embed(texts)
        self._collection.upsert(
            ids=[doc.doc_id for doc in documents],
            embeddings=embeddings,
            documents=[doc.body for doc in documents],
            metadatas=[doc.to_metadata() for doc in documents],
        )
        return len(documents)

    def similarity_search(self, query: str, top_k: int = 4) -> list[RetrievedDoc]:
        """Semantic similarity search. Returns docs ranked most relevant first."""
        if not query.strip() or self.count() == 0:
            return []

        query_vector = self.embedder.embed_one(query)
        if not query_vector:
            raise RuntimeError(
                "The embedder produced no vector. A lexical embedder must be fitted "
                "before querying; re-run scripts/ingest_kb.py to rebuild the index."
            )

        # Over-fetch a candidate pool and re-rank it with a stable tie-break.
        # Chroma returns equally distant documents in an arbitrary order that can
        # change from one process to the next; with the sparse TF-IDF fallback a
        # query sharing no vocabulary with the knowledge base ties *every* article
        # at similarity 0. Sorting by (distance, doc_id) makes retrieval
        # reproducible run to run (the pool covers the whole collection whenever
        # it holds CANDIDATE_POOL documents or fewer, as the 30-article KB does).
        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=min(max(top_k, CANDIDATE_POOL), self.count()),
            include=["documents", "metadatas", "distances"],
        )

        rows = sorted(
            zip(
                (results.get("ids") or [[]])[0],
                (results.get("documents") or [[]])[0],
                (results.get("metadatas") or [[]])[0],
                (results.get("distances") or [[]])[0],
            ),
            key=lambda row: (round(float(row[3]), 6), str(row[0])),
        )[:top_k]

        retrieved: list[RetrievedDoc] = []
        for rank, (doc_id, content, meta, distance) in enumerate(rows):
            meta = meta or {}
            # Chroma cosine distance is in [0, 2]; map it onto a [0, 1] similarity.
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            retrieved.append(
                RetrievedDoc(
                    doc_id=str(meta.get("doc_id", doc_id)),
                    title=str(meta.get("title", "")),
                    source=str(meta.get("source", "")),
                    category=str(meta.get("category", "")),
                    content=content or "",
                    score=round(similarity, 4),
                    rank=rank + 1,
                )
            )
        return retrieved


# --------------------------------------------------------------------------- #
# Construction helpers
# --------------------------------------------------------------------------- #

_STORE_CACHE: dict[str, VectorStore] = {}
_DEFAULT_STORE: VectorStore | None = None


def build_store(
    settings: RetrievalSettings | None = None,
    *,
    persist: bool = True,
    ingest: bool = False,
    embedder: Embedder | None = None,
    rebuild_on_mismatch: bool = False,
) -> VectorStore:
    """Create a store, optionally ingesting the knowledge base into it."""
    settings = settings or SETTINGS.retrieval
    store = VectorStore(
        collection_name=settings.collection_name,
        embedder=embedder or get_embedder(settings.embedding_model, settings.embedder_backend),
        persist_dir=settings.chroma_dir if persist else None,
        rebuild_on_mismatch=rebuild_on_mismatch,
    )
    if ingest:
        documents = load_knowledge_base(settings.kb_dir)
        added = store.add_documents(documents)
        logger.info("Indexed %d knowledge-base articles into %r.", added, settings.collection_name)
    return store


def set_default_store(store: VectorStore | None) -> None:
    """Install a store that :func:`get_store` returns unconditionally.

    Used by the test suite to run the compiled graph against an in-memory
    collection, so graph tests need neither a persisted index on disk nor a
    model download, and never touch the developer's real index.
    """
    global _DEFAULT_STORE
    _DEFAULT_STORE = store


def get_store(settings: RetrievalSettings | None = None) -> VectorStore:
    """Return the shared persistent store, ingesting on first use if it is empty."""
    if _DEFAULT_STORE is not None:
        return _DEFAULT_STORE
    settings = settings or SETTINGS.retrieval
    cache_key = f"{settings.chroma_dir}::{settings.collection_name}"
    store = _STORE_CACHE.get(cache_key)
    if store is None:
        store = build_store(settings, persist=True, ingest=False, rebuild_on_mismatch=True)
        if store.count() == 0:
            logger.info("Collection %r is empty; ingesting the knowledge base.", settings.collection_name)
            store.add_documents(load_knowledge_base(settings.kb_dir))
        _STORE_CACHE[cache_key] = store
    return store


def reset_store_cache() -> None:
    """Drop the cached store and any override (used by tests)."""
    global _DEFAULT_STORE
    _STORE_CACHE.clear()
    _DEFAULT_STORE = None
