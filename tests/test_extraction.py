"""Extraction unit tests: interface conformance, rules, and the fallback switch.

No test here (or anywhere in the suite) requires network or an API key —
the LLM adapter is exercised through an injected fake transport, and the
factory falls back to the deterministic extractor when no key is set.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pytest

from insmart_api.extractors import (
    DeterministicExtractor,
    EvidenceKind,
    ExtractedObservation,
    Extractor,
    LLMError,
    LLMExtractor,
    ObservationCategory,
    WorkOrderText,
    get_extractor,
    llm_configured,
    work_order_text,
)
from insmart_api.integrity import parse_source_ref

CREATED = datetime(2024, 4, 4, 13, 36, 25)
COMPLETED = datetime(2024, 4, 4, 21, 53, 2)


def make_work_order(
    work_order_id: str = "WO-0099",
    summary: str = "AHU-1 scheduled service",
    notes: str = "Inspected unit, checked filters.",
    resolution: str = "No defects found, unit performing to spec.",
    completed_at: datetime | None = COMPLETED,
) -> WorkOrderText:
    """One synthetic work order, benign by default."""
    return work_order_text(
        work_order_id,
        {"summary": summary, "notes": notes, "resolution": resolution},
        CREATED,
        completed_at,
    )


DEFECT_NOTES = (
    "Unit hard starting, compressor drawing locked-rotor amps on restart. "
    "Compressor winding resistance out of range, confirm with megger."
)


class TestInterfaceConformance:
    def test_both_extractors_satisfy_the_interface(self) -> None:
        for extractor in (DeterministicExtractor(), _llm_extractor()):
            assert isinstance(extractor, Extractor)
            extracted = extractor.extract(make_work_order())
            assert isinstance(extracted, list)
            assert all(isinstance(item, ExtractedObservation) for item in extracted)

    def test_deterministic_extractor_is_deterministic(self) -> None:
        extractor = DeterministicExtractor()
        work_order = make_work_order(notes=DEFECT_NOTES)
        assert extractor.extract(work_order) == extractor.extract(work_order)

    def test_observed_output_carries_no_inference_fields(self) -> None:
        extracted = DeterministicExtractor().extract(make_work_order())
        assert extracted
        for observation in extracted:
            assert observation.kind is EvidenceKind.OBSERVED
            assert observation.evidence_ids == ()
            assert observation.confidence is None

    def test_every_observation_source_ref_is_parseable(self) -> None:
        extracted = DeterministicExtractor().extract(
            make_work_order(notes=DEFECT_NOTES)
        )
        for observation in extracted:
            parsed = parse_source_ref(observation.source_ref)
            assert parsed is not None
            scheme, record_id = parsed
            assert scheme == "work-order"
            assert record_id == observation.work_order_id


class TestDeterministicRules:
    def test_defect_language_is_extracted_as_defect(self) -> None:
        extracted = DeterministicExtractor().extract(
            make_work_order(notes=DEFECT_NOTES)
        )
        defects = [o for o in extracted if o.category is ObservationCategory.DEFECT]
        spans = {o.text.lower() for o in defects}
        assert "locked-rotor" in spans
        assert "winding resistance out of range" in spans
        assert all(o.field == "notes" for o in defects)

    def test_reported_noise_is_symptom_not_defect(self) -> None:
        extracted = DeterministicExtractor().extract(
            make_work_order(
                notes="Tenant reports unit noisy during occupied hours."
            )
        )
        assert any(o.category is ObservationCategory.SYMPTOM for o in extracted)
        assert not any(o.category is ObservationCategory.DEFECT for o in extracted)

    def test_actions_come_from_the_resolution_field(self) -> None:
        extracted = DeterministicExtractor().extract(
            make_work_order(resolution="Replaced igniter, cleaned flame sensor.")
        )
        resolution_spans = {
            o.text.lower()
            for o in extracted
            if o.category is ObservationCategory.ACTION and o.field == "resolution"
        }
        assert {"replaced", "cleaned"} <= resolution_spans

    def test_dates_are_exact_and_complete(self) -> None:
        extracted = DeterministicExtractor().extract(make_work_order())
        dates = {(o.field, o.text) for o in extracted if o.category is ObservationCategory.DATE}
        assert dates == {
            ("created_at", CREATED.isoformat()),
            ("completed_at", COMPLETED.isoformat()),
        }

    def test_missing_completed_at_emits_only_created_date(self) -> None:
        extracted = DeterministicExtractor().extract(make_work_order(completed_at=None))
        dates = [o for o in extracted if o.category is ObservationCategory.DATE]
        assert [(o.field, o.text) for o in dates] == [("created_at", CREATED.isoformat())]

    def test_benign_work_order_emits_no_defect(self) -> None:
        extracted = DeterministicExtractor().extract(make_work_order())
        assert not any(o.category is ObservationCategory.DEFECT for o in extracted)


def _llm_extractor(transport: Any = None) -> LLMExtractor:
    kwargs: dict[str, Any] = {}
    if transport is not None:
        kwargs["transport"] = transport
    return LLMExtractor(api_key="test-key", **kwargs)


def _fake_llm_payload(observations: list[dict[str, Any]]) -> dict[str, Any]:
    content = json.dumps({"observations": observations})
    return {"choices": [{"message": {"content": content}}]}


class TestLLMFallback:
    def test_no_key_selects_the_deterministic_extractor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SECRET_LLM_API_KEY", raising=False)
        assert llm_configured() is False
        assert type(get_extractor()) is DeterministicExtractor

    def test_key_present_selects_the_llm_extractor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECRET_LLM_API_KEY", "test-key")
        assert llm_configured() is True
        assert isinstance(get_extractor(), LLMExtractor)

    def test_llm_output_is_inferred_with_evidence_ids(self) -> None:
        transport_calls: list[tuple[str, bytes]] = []

        def transport(
            url: str, body: bytes, headers: Mapping[str, str]
        ) -> dict[str, Any]:
            transport_calls.append((url, body))
            assert headers["Authorization"] == "Bearer test-key"
            return _fake_llm_payload(
                [
                    {
                        "category": "defect",
                        "text": "compressor winding resistance out of range",
                        "field": "notes",
                        "confidence": 0.9,
                    }
                ]
            )

        extracted = _llm_extractor(transport).extract(make_work_order(notes=DEFECT_NOTES))
        assert len(extracted) == 1
        observation = extracted[0]
        assert observation.kind is EvidenceKind.INFERRED
        assert observation.category is ObservationCategory.DEFECT
        assert observation.confidence == 0.9
        assert observation.evidence_ids == ("WO-0099",)
        assert observation.source_ref == "work-order:WO-0099"
        assert transport_calls[0][0].endswith("/chat/completions")

    def test_transport_failure_falls_back_to_deterministic(self) -> None:
        def failing_transport(
            url: str, body: bytes, headers: Mapping[str, str]
        ) -> dict[str, Any]:
            raise LLMError("connection refused")

        work_order = make_work_order(notes=DEFECT_NOTES)
        deterministic = DeterministicExtractor().extract(work_order)
        assert _llm_extractor(failing_transport).extract(work_order) == deterministic

    def test_malformed_llm_reply_falls_back_to_deterministic(self) -> None:
        def garbage_transport(
            url: str, body: bytes, headers: Mapping[str, str]
        ) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "not json"}}]}

        work_order = make_work_order(notes=DEFECT_NOTES)
        deterministic = DeterministicExtractor().extract(work_order)
        assert _llm_extractor(garbage_transport).extract(work_order) == deterministic

    def test_unknown_category_falls_back_to_deterministic(self) -> None:
        def hallucinating_transport(
            url: str, body: bytes, headers: Mapping[str, str]
        ) -> dict[str, Any]:
            return _fake_llm_payload(
                [{"category": "vibration", "text": "made up", "field": "notes"}]
            )

        work_order = make_work_order(notes=DEFECT_NOTES)
        deterministic = DeterministicExtractor().extract(work_order)
        assert _llm_extractor(hallucinating_transport).extract(work_order) == deterministic
