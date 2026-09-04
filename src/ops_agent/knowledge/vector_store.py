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


class VectorStore:
    """Thin wrapper over a Chroma collection using externally supplied embeddings."""

    def __init__(
        self,
        collection_name: str,
        embedder: Embedder,
        persist_dir: Path | str | None = None,
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

        # Cosine space so that similarity = 1 - distance lands in a readable range.
        self._collection = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

        # A lexical embedder's vectors mean nothing without the vocabulary they
        # were fitted on, so restore it alongside a persisted collection.
        if self._embedder_state_path is not None:
            loader = getattr(self.embedder, "load_state", None)
            if callable(loader) and loader(self._embedder_state_path):
                logger.debug("Restored embedder state from %s", self._embedder_state_path)

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

        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )

        ids = (results.get("ids") or [[]])[0]
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        retrieved: list[RetrievedDoc] = []
        for rank, doc_id in enumerate(ids):
            meta = metas[rank] or {}
            # Chroma cosine distance is in [0, 2]; map it onto a [0, 1] similarity.
            similarity = max(0.0, min(1.0, 1.0 - float(distances[rank])))
            retrieved.append(
                RetrievedDoc(
                    doc_id=str(meta.get("doc_id", doc_id)),
                    title=str(meta.get("title", "")),
                    source=str(meta.get("source", "")),
                    category=str(meta.get("category", "")),
                    content=docs[rank] or "",
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
) -> VectorStore:
    """Create a store, optionally ingesting the knowledge base into it."""
    settings = settings or SETTINGS.retrieval
    store = VectorStore(
        collection_name=settings.collection_name,
        embedder=embedder or get_embedder(settings.embedding_model),
        persist_dir=settings.chroma_dir if persist else None,
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
        store = build_store(settings, persist=True, ingest=False)
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
