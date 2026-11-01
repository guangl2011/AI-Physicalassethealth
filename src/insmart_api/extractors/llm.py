"""OpenAI-compatible LLM adapter — the same Extractor interface, never required.

Activated only when ``SECRET_LLM_API_KEY`` is configured. LLM output is
marked ``inferred`` with evidence ids citing the work order it was derived
from, matching the evidence graph's no-inference-without-evidence rule.
Any adapter failure — missing key, transport error, malformed response —
falls back to the deterministic extractor, so the product degrades to a
weaker but always-available answer rather than an error.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol

from insmart_api.extractors.base import (
    ExtractedObservation,
    Extractor,
    ObservationCategory,
    WorkOrderText,
    inferred_observation,
)
from insmart_api.extractors.deterministic import DeterministicExtractor

LLM_ENV_KEY = "SECRET_LLM_API_KEY"
LLM_ENV_BASE_URL = "SECRET_LLM_BASE_URL"
LLM_ENV_MODEL = "SECRET_LLM_MODEL"

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

_TIMEOUT_SECONDS = 30

_SYSTEM_PROMPT = (
    "You extract structured maintenance findings from commercial-HVAC work "
    "orders. Answer ONLY with JSON: {\"observations\": [{\"category\": one of "
    "\"defect\"|\"symptom\"|\"action\", \"text\": \"the exact finding phrase\", "
    "\"field\": one of \"summary\"|\"notes\"|\"resolution\"}]}. A defect names a "
    "failure cause or repair evidence; a symptom is an observable indication; "
    "an action is work performed. Never invent findings."
)


class LLMError(RuntimeError):
    """The LLM adapter could not produce a valid extraction."""


class LLMTransport(Protocol):
    """How the adapter reaches an OpenAI-compatible endpoint (injectable)."""

    def __call__(
        self, url: str, body: bytes, headers: Mapping[str, str]
    ) -> dict[str, Any]: ...


def _http_transport(
    url: str, body: bytes, headers: Mapping[str, str]
) -> dict[str, Any]:
    """Post one chat-completions request; return the parsed JSON reply."""
    request = urllib.request.Request(url, data=body, headers=dict(headers))
    payload: Any
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as reply:
            payload = json.loads(reply.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise LLMError(f"LLM transport failed: {error}") from error
    if not isinstance(payload, dict):
        raise LLMError("LLM reply is not a JSON object")
    return payload


def _parse_response(payload: dict[str, Any], work_order_id: str) -> list[ExtractedObservation]:
    """Map an LLM reply onto inferred observations; LLMError on anything off."""
    try:
        content: str = payload["choices"][0]["message"]["content"]
        raw_items: list[dict[str, Any]] = json.loads(content)["observations"]
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise LLMError(f"malformed LLM response: {error}") from error
    if not isinstance(raw_items, list):
        raise LLMError("LLM response 'observations' is not a list")

    observations: list[ExtractedObservation] = []
    for item in raw_items:
        try:
            category = ObservationCategory(item["category"])
            text = item["text"]
            field = item["field"]
            confidence = item.get("confidence")
        except (KeyError, TypeError, ValueError) as error:
            raise LLMError(f"malformed LLM observation item: {error}") from error
        if confidence is not None and not (
            isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0
        ):
            raise LLMError(f"LLM confidence out of range: {confidence!r}")
        observations.append(
            inferred_observation(
                category, str(text), work_order_id, str(field), confidence
            )
        )
    return observations


class LLMExtractor(Extractor):
    """LLM-backed extractor with graceful fallback to the deterministic rules."""

    name = "llm"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        fallback: Extractor | None = None,
        transport: LLMTransport | None = None,
    ) -> None:
        """``transport`` is injectable so tests never touch the network."""
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._fallback = fallback or DeterministicExtractor()
        self._transport: LLMTransport = transport or _http_transport

    def extract(self, work_order: WorkOrderText) -> list[ExtractedObservation]:
        try:
            return self._extract_via_llm(work_order)
        except LLMError:
            # Designed degradation, not a swallowed bug: no key, an
            # unreachable endpoint, or a malformed reply all fall back to the
            # deterministic extractor. Deterministic output is observed, not
            # inferred — the caller still learns which path ran via extractor name.
            return self._fallback.extract(work_order)

    def _extract_via_llm(self, work_order: WorkOrderText) -> list[ExtractedObservation]:
        body = json.dumps(
            {
                "model": self._model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "work_order_id": work_order.work_order_id,
                                "summary": work_order.text_of("summary"),
                                "notes": work_order.text_of("notes"),
                                "resolution": work_order.text_of("resolution"),
                            }
                        ),
                    },
                ],
            }
        ).encode("utf-8")
        payload = self._transport(
            f"{self._base_url}/chat/completions",
            body,
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        return _parse_response(payload, work_order.work_order_id)
