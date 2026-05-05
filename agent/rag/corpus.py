"""Markdown corpus loader.

Reads `corpus/guidelines/*.md` files, parses YAML-ish frontmatter, and
returns a stable list of `Chunk`s suitable for indexing. The frontmatter
parser is intentionally minimal — we control the corpus, so we don't
need a full YAML lib for five string fields.

Corpus path resolution: defaults to `<repo_root>/corpus/guidelines/`
relative to this file, but the caller can pass an explicit path
(useful in tests + when the package is installed elsewhere).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chunk:
    """One indexable unit. `chunk_id` is the citation primary key — the
    verifier walks `Citation.source_id` against this. Text is body only;
    title + source live as separate fields so the prompt can render
    them as headers."""

    chunk_id: str
    title: str
    source: str
    url: str | None
    text: str

    def for_prompt(self) -> str:
        """Render the chunk for inclusion in the answer pipeline's
        guideline_evidence block."""
        return (
            f"<guideline chunk_id='{self.chunk_id}' title='{self.title}'"
            f" source='{self.source}'>\n{self.text}\n</guideline>"
        )


def _default_corpus_root() -> Path:
    """`<repo_root>/corpus/guidelines/` — agent/rag/corpus.py is two
    directories deep from the repo root."""
    return Path(__file__).resolve().parents[2] / "corpus" / "guidelines"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Tiny frontmatter parser. Expects:
        ---
        key: value
        ---
        body...
    Values are unquoted strings (we control the corpus). Returns
    ({}, full_text) when there is no frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text

    meta: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")

    body = "\n".join(lines[end_idx + 1 :]).strip()
    return meta, body


def load_corpus(root: Path | None = None) -> list[Chunk]:
    """Read every .md file under `root`, parse frontmatter, return
    Chunks in sorted-by-chunk_id order so eval cassettes stay
    deterministic across runs.

    A file without `chunk_id` in its frontmatter is skipped with a
    warning (the chunk_id is the citation primary key — without it the
    verifier has nothing to match on)."""
    root = root or _default_corpus_root()
    if not root.is_dir():
        log.warning("load_corpus: %s is not a directory; returning empty", root)
        return []

    chunks: list[Chunk] = []
    for md_path in sorted(root.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        chunk_id = meta.get("chunk_id")
        if not chunk_id:
            log.warning(
                "load_corpus: %s has no chunk_id in frontmatter; skipping",
                md_path.name,
            )
            continue
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                title=meta.get("title", chunk_id),
                source=meta.get("source", "internal"),
                url=meta.get("url") or None,
                text=body,
            )
        )

    log.info("load_corpus: %d chunks loaded from %s", len(chunks), root)
    return chunks
