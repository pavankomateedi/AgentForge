"""Live-LLM eval fixtures.

These tests hit the real Anthropic API and are skipped by default. Run them
explicitly with `pytest -m live`. Requires ANTHROPIC_API_KEY in the
environment (the real key, not the test placeholder).
"""

from __future__ import annotations

import os

import anthropic
import pytest


def _have_real_key() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return key.startswith("sk-ant-")


pytestmark = pytest.mark.skipif(
    not _have_real_key(),
    reason="ANTHROPIC_API_KEY not set to a real sk-ant-... value",
)


@pytest.fixture
def anthropic_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


@pytest.fixture
def model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
