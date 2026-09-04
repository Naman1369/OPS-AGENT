"""Knowledge base: document loading, embeddings and the Chroma vector store."""

from .embeddings import Embedder, SentenceTransformerEmbedder, TfidfEmbedder, get_embedder
from .loader import KBDocument, load_knowledge_base
from .vector_store import VectorStore, build_store, get_store, reset_store_cache, set_default_store

__all__ = [
    "Embedder",
    "TfidfEmbedder",
    "SentenceTransformerEmbedder",
    "get_embedder",
    "KBDocument",
    "load_knowledge_base",
    "VectorStore",
    "build_store",
    "get_store",
    "set_default_store",
    "reset_store_cache",
]
