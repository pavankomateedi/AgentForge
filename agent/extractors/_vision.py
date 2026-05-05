"""Vision-call surface used by lab_extractor + intake_extractor.

Factored into its own module so tests can monkeypatch `call_vision_pdf`
and `call_vision_image` without touching the extractors that depend on
them. Each function is async, returns a parsed JSON dict, and raises
`VisionExtractionError` on transport/parse failures so the extractor
can decide whether to mark the document `failed` or fall through to a
recovery path.

The Anthropic SDK is the only dependency — no model-specific prompting
lives here, just the wire-format helpers.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import anthropic

log = logging.getLogger(__name__)


class VisionExtractionError(Exception):
    """Raised when the vision call fails or returns un-parseable JSON."""


# Vision JSON output cap. Lab reports + intake forms produce small JSON
# (<2KB typical); 4096 tokens is generous headroom while staying inside
# the cost-per-extraction budget in W2_ARCHITECTURE.md §11.
_MAX_OUTPUT_TOKENS = 4096


def _strip_to_json(text: str) -> str:
    """The model sometimes wraps JSON in ```json ... ``` fences or adds
    a brief preamble. Strip both so json.loads sees a clean payload."""
    text = text.strip()
    if text.startswith("```"):
        # ```json\n{...}\n``` or ```\n{...}\n```
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    # If there's a preamble + JSON object, find the first '{' or '['
    for opener, closer in (("{", "}"), ("[", "]")):
        if (start := text.find(opener)) >= 0:
            end = text.rfind(closer)
            if end > start:
                return text[start : end + 1]
    return text


def _parse_json_response(content: str) -> dict[str, Any]:
    """Tolerant of ``` fences and small preamble. Raises
    VisionExtractionError on malformed JSON so the caller can audit the
    failure with the raw text intact."""
    cleaned = _strip_to_json(content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise VisionExtractionError(
            f"VLM returned non-JSON content (after fence/preamble strip): {e}"
        ) from e


async def call_vision_pdf(
    *,
    client: anthropic.AsyncAnthropic,
    model: str,
    blob: bytes,
    system: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Send a PDF to Claude vision and return the parsed JSON response.

    Tests monkeypatch this function — it's the only place the SDK
    surface is touched for PDFs."""
    b64 = base64.standard_b64encode(blob).decode("ascii")
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
        )
    except Exception as e:
        raise VisionExtractionError(f"Anthropic SDK call failed: {e}") from e

    text_blocks = [
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ]
    if not text_blocks:
        raise VisionExtractionError("VLM response had no text blocks")
    return _parse_json_response("".join(text_blocks))


async def call_vision_image(
    *,
    client: anthropic.AsyncAnthropic,
    model: str,
    blob: bytes,
    media_type: str,
    system: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Send an image (JPEG/PNG/HEIC) to Claude vision."""
    if media_type not in ("image/jpeg", "image/png", "image/heic"):
        raise VisionExtractionError(
            f"Unsupported image media_type: {media_type!r}"
        )
    b64 = base64.standard_b64encode(blob).decode("ascii")
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
        )
    except Exception as e:
        raise VisionExtractionError(f"Anthropic SDK call failed: {e}") from e

    text_blocks = [
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ]
    if not text_blocks:
        raise VisionExtractionError("VLM response had no text blocks")
    return _parse_json_response("".join(text_blocks))


def render_fragment_context(fragments: list, max_per_page: int = 80) -> str:
    """Render fragments as a tab-separated table the VLM can cite by id.

    Format: `fragment_id\ttext` per line, grouped by page with a
    `--- page N ---` header. Capped at `max_per_page` per page so an
    image-only page that pdfplumber accidentally yielded thousands of
    spurious words doesn't blow the context window."""
    from agent.extractors.pdf_fragments import Fragment

    if not fragments:
        return "(no extractable text fragments — work from the page image alone)"

    lines: list[str] = []
    by_page: dict[int, list[Fragment]] = {}
    for f in fragments:
        by_page.setdefault(f.page, []).append(f)

    for page in sorted(by_page.keys()):
        lines.append(f"--- page {page} ---")
        for f in by_page[page][:max_per_page]:
            lines.append(f"{f.fragment_id}\t{f.text}")
        if len(by_page[page]) > max_per_page:
            lines.append(
                f"... ({len(by_page[page]) - max_per_page} more fragments truncated)"
            )
    return "\n".join(lines)
