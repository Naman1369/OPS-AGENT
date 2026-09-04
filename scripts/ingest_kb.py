#!/usr/bin/env python3
"""Index the knowledge base into the Chroma vector store.

Usage:
    python scripts/ingest_kb.py                # index data/knowledge_base
    python scripts/ingest_kb.py --rebuild      # drop and rebuild the collection
    python scripts/ingest_kb.py --probe "vpn error 809"
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ops_agent.config import SETTINGS  # noqa: E402
from ops_agent.knowledge import build_store, load_knowledge_base  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest the OPS-AGENT knowledge base.")
    parser.add_argument("--rebuild", action="store_true", help="delete the existing index first")
    parser.add_argument("--probe", default="", help="run a test query after ingestion")
    args = parser.parse_args()

    settings = SETTINGS.retrieval

    if args.rebuild and settings.chroma_dir.exists():
        print(f"Removing existing index at {settings.chroma_dir}")
        shutil.rmtree(settings.chroma_dir)

    documents = load_knowledge_base(settings.kb_dir)
    print(f"Loaded {len(documents)} articles from {settings.kb_dir}")

    store = build_store(settings, persist=True, ingest=False)
    added = store.add_documents(documents)
    print(f"Indexed {added} articles into collection '{settings.collection_name}'")
    print(f"Embedding model : {store.embedder.name} ({store.embedder.dimension} dims)")
    print(f"Persisted at    : {settings.chroma_dir}")
    print(f"Collection size : {store.count()}")

    if args.probe:
        print(f"\nProbe query: {args.probe!r}")
        for doc in store.similarity_search(args.probe, top_k=settings.top_k):
            print(f"  {doc['rank']}. [{doc['score']:.3f}] {doc['doc_id']} - {doc['title']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
