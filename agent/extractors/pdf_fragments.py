"""pdfplumber wrapper: PDF bytes -> stable list of text fragments.

Each fragment carries a `fragment_id` (stable per document, deterministic
under re-extraction) and a `BBox` in pdfplumber's top-left coordinate
space — `(x0, y0)` is the top-left corner of the fragment, `(x1, y1)`
is the bottom-right. The UI overlay flips y when rendering on top of
the rasterized page if it uses bottom-left convention.

Fragments are line-level (collapsed adjacent words on the same y-band)
so the VLM sees fewer, more semantically meaningful chunks to cite. A
two-line lab-result row "HbA1c    8.5%" becomes ONE fragment, not two.

The function works on any PDF that pdfplumber can open. Image-only PDFs
return zero fragments — that's the documented signal that the caller
should fall back to the page-image-only vision path.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import pdfplumber

from agent.schemas.citation import BBox

log = logging.getLogger(__name__)


# y-band tolerance: words within this many points of each other on the
# y-axis are treated as the same line. 3 pts is roughly half a typical
# 12pt line height — tight enough to keep adjacent rows separate, loose
# enough to absorb tiny baseline jitter from scanned PDFs.
_LINE_BAND_TOLERANCE = 3.0


@dataclass(frozen=True)
class Fragment:
    """One unit the VLM can cite. fragment_id is stable per document so
    re-extraction with a refined prompt produces matchable citations."""

    fragment_id: str
    page: int  # 1-indexed
    text: str
    bbox: BBox


def _collapse_words_to_lines(
    words: list[dict], page: int
) -> list[Fragment]:
    """Group same-line words into one Fragment per visual line.

    Words come from pdfplumber's extract_words() in left-to-right,
    top-to-bottom order. We bucket by y-midpoint so a word's vertical
    center decides its line — robust to slight per-character ascender/
    descender variance.
    """
    if not words:
        return []

    sorted_words = sorted(
        words, key=lambda w: (round(float(w["top"]), 1), float(w["x0"]))
    )

    lines: list[list[dict]] = []
    for w in sorted_words:
        w_top = float(w["top"])
        if lines:
            last_line_top = float(lines[-1][0]["top"])
            if abs(w_top - last_line_top) <= _LINE_BAND_TOLERANCE:
                lines[-1].append(w)
                continue
        lines.append([w])

    fragments: list[Fragment] = []
    for line_idx, line in enumerate(lines):
        if not line:
            continue
        x0 = min(float(w["x0"]) for w in line)
        x1 = max(float(w["x1"]) for w in line)
        y0 = min(float(w["top"]) for w in line)
        y1 = max(float(w["bottom"]) for w in line)

        # Guard against pathological zero-width / zero-height fragments
        # (rare, but breaks BBox.x1 > x0 invariant).
        if x1 <= x0:
            x1 = x0 + 0.5
        if y1 <= y0:
            y1 = y0 + 0.5

        text = " ".join(str(w["text"]) for w in line).strip()
        if not text:
            continue

        frag_id = f"p{page}-l{line_idx:03d}"
        fragments.append(
            Fragment(
                fragment_id=frag_id,
                page=page,
                text=text,
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
            )
        )
    return fragments


def extract_fragments(blob: bytes) -> list[Fragment]:
    """Open the PDF, return line-level fragments across all pages.

    Returns an empty list (not an error) for image-only PDFs or
    pdfplumber-unparseable input — the caller decides whether to fall
    back to a vision-only path or surface a `failed` extraction.
    Logs the page count + total fragment count at INFO; never logs the
    fragment text (PHI)."""
    try:
        with pdfplumber.open(io.BytesIO(blob)) as pdf:
            all_fragments: list[Fragment] = []
            for page_idx, page in enumerate(pdf.pages, start=1):
                try:
                    words = page.extract_words(
                        keep_blank_chars=False,
                        use_text_flow=True,
                    )
                except Exception as e:
                    log.warning(
                        "pdf_fragments: page %d extract_words failed: %s",
                        page_idx, e,
                    )
                    continue
                page_frags = _collapse_words_to_lines(words, page_idx)
                all_fragments.extend(page_frags)
        log.info(
            "pdf_fragments: extracted %d fragments across %d pages",
            len(all_fragments),
            page_idx if all_fragments else 0,
        )
        return all_fragments
    except Exception as e:
        log.warning("pdf_fragments: pdfplumber.open failed: %s", e)
        return []
