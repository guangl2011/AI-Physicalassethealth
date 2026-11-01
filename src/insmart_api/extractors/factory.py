"""Extractor selection: the LLM adapter only when its key is configured.

The single place the fallback switch lives. ``SECRET_LLM_API_KEY`` present
→ LLM-backed extractor (which still degrades to deterministic rules on any
runtime failure); absent → the deterministic extractor outright, so the
whole pipeline — and the entire test suite — runs keyless and offline.
"""

from __future__ import annotations

import os

from insmart_api.extractors.base import Extractor
from insmart_api.extractors.deterministic import DeterministicExtractor
from insmart_api.extractors.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    LLM_ENV_BASE_URL,
    LLM_ENV_KEY,
    LLM_ENV_MODEL,
    LLMExtractor,
)


def llm_configured() -> bool:
    """True when an LLM API key is configured in the environment."""
    return bool(os.environ.get(LLM_ENV_KEY))


def get_extractor() -> Extractor:
    """The extractor for this environment: LLM-backed if a key is set."""
    api_key = os.environ.get(LLM_ENV_KEY)
    if api_key:
        return LLMExtractor(
            api_key=api_key,
            base_url=os.environ.get(LLM_ENV_BASE_URL, DEFAULT_BASE_URL),
            model=os.environ.get(LLM_ENV_MODEL, DEFAULT_MODEL),
        )
    return DeterministicExtractor()
