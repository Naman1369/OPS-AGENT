"""Load knowledge-base articles from markdown files with YAML-style frontmatter.

Kept deliberately dependency-free so the corpus can be swapped for the real
Week 3-4 dataset without touching the retrieval path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class KBDocument:
    """One knowledge-base article ready to be embedded and indexed."""

    doc_id: str
    title: str
    category: str
    source: str
    tags: list[str] = field(default_factory=list)
    body: str = ""
    path: str = ""

    def embedding_text(self) -> str:
        """The text actually embedded: title and tags weighted alongside the body."""
        tag_line = ", ".join(self.tags)
        return f"{self.title}\n{tag_line}\n{self.body}".strip()

    def to_metadata(self) -> dict[str, Any]:
        """Chroma metadata values must be scalars, so tags are joined."""
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "category": self.category,
            "source": self.source,
            "tags": ", ".join(self.tags),
            "path": self.path,
        }


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    return value.strip("'\"")


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = _parse_scalar(value)
    return meta, text[match.end():]


def load_knowledge_base(kb_dir: Path | str) -> list[KBDocument]:
    """Read every markdown article in ``kb_dir``, sorted for reproducibility."""
    kb_path = Path(kb_dir)
    if not kb_path.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_path}")

    documents: list[KBDocument] = []
    for file_path in sorted(kb_path.glob("*.md")):
        raw = file_path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        documents.append(
            KBDocument(
                doc_id=str(meta.get("doc_id") or file_path.stem),
                title=str(meta.get("title") or file_path.stem),
                category=str(meta.get("category") or "other"),
                source=str(meta.get("source") or "knowledge-base"),
                tags=list(tags),
                body=body.strip(),
                path=str(file_path),
            )
        )

    if not documents:
        raise ValueError(f"No markdown articles found in {kb_path}")
    return documents
