"""Extraction evaluation against the adjudicated seed corpus.

Ground truth comes from the adjudicated labels, not from hand-labeling: a
work order is defect-positive exactly when the asset's adjudicated
``known_failure_causes`` cite it as evidence (spec art_N0ARICWR —
extraction precision/recall ≥ 0.8 for the deterministic extractor). The
evaluation runs over the work orders the ingestion pipeline actually
admitted, the same records extraction sees downstream. A second test
asserts every emitted observation carries a ``source_ref`` that resolves
to a real ingested record — provenance never dangles.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from insmart_api.extractors import (
    DeterministicExtractor,
    ObservationCategory,
    WorkOrderText,
    work_order_text,
)
from insmart_api.integrity import parse_source_ref
from insmart_api.models import Observation

MIN_PRECISION = 0.8
MIN_RECALL = 0.8


def _work_orders_from_store(session: Session) -> list[WorkOrderText]:
    """Rebuild extractor inputs from the ingested observations' payloads."""
    rows = session.scalars(select(Observation)).all()
    work_orders: list[WorkOrderText] = []
    for observation in rows:
        payload: dict[str, Any] = json.loads(observation.payload)
        work_orders.append(
            work_order_text(
                observation.id,
                payload,
                datetime.fromisoformat(payload["created_at"]),
                (
                    datetime.fromisoformat(payload["completed_at"])
                    if payload.get("completed_at")
                    else None
                ),
            )
        )
    return work_orders


def _adjudicated_defect_work_orders(labels: dict[str, Any]) -> set[str]:
    """Work orders the adjudication cites as defect evidence."""
    cited: set[str] = set()
    for asset in labels["assets"]:
        for cause in asset["known_failure_causes"]:
            for evidence in cause["evidence"]:
                cited.add(evidence["work_order_id"])
    return cited


def test_deterministic_extraction_precision_and_recall(
    db_session: Session, labels: dict[str, Any]
) -> None:
    work_orders = _work_orders_from_store(db_session)
    extracted = DeterministicExtractor().extract_all(work_orders)

    predicted = {
        o.work_order_id for o in extracted if o.category is ObservationCategory.DEFECT
    }
    actual = _adjudicated_defect_work_orders(labels) & {w.work_order_id for w in work_orders}

    true_positives = len(predicted & actual)
    precision = true_positives / len(predicted) if predicted else 0.0
    recall = true_positives / len(actual) if actual else 0.0

    diagnostics = (
        f"precision {precision:.3f} recall {recall:.3f} — "
        f"false positives: {sorted(predicted - actual)}, "
        f"false negatives: {sorted(actual - predicted)}"
    )
    assert precision >= MIN_PRECISION, diagnostics
    assert recall >= MIN_RECALL, diagnostics


def test_every_extracted_source_ref_resolves(
    db_session: Session, labels: dict[str, Any]
) -> None:
    work_orders = _work_orders_from_store(db_session)
    extracted = DeterministicExtractor().extract_all(work_orders)

    ingested_ids = {w.work_order_id for w in work_orders}
    assert extracted, "extraction produced nothing to check"
    for observation in extracted:
        parsed = parse_source_ref(observation.source_ref)
        assert parsed is not None, f"unparseable source_ref {observation.source_ref!r}"
        _, record_id = parsed
        assert record_id in ingested_ids, (
            f"source_ref {observation.source_ref!r} does not resolve to an ingested record"
        )


def test_extracted_dates_match_the_source_records(
    db_session: Session, labels: dict[str, Any]
) -> None:
    work_orders = _work_orders_from_store(db_session)
    extracted = DeterministicExtractor().extract_all(work_orders)

    dates: dict[str, set[tuple[str, str]]] = {}
    for observation in extracted:
        if observation.category is ObservationCategory.DATE:
            dates.setdefault(observation.work_order_id, set()).add(
                (observation.field, observation.text)
            )

    for work_order in work_orders:
        actual = dates.get(work_order.work_order_id, set())
        expected_dates = {("created_at", work_order.created_at.isoformat())}
        if work_order.completed_at is not None:
            expected_dates.add(("completed_at", work_order.completed_at.isoformat()))
        assert actual == expected_dates, (
            f"{work_order.work_order_id}: {actual} != {expected_dates}"
        )
