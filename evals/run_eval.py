"""The evaluation harness: compute, report, and gate the spec's metrics.

``evaluate`` turns one ingested store plus the adjudicated labels into an
``EvalReport``; ``threshold_violations`` names every missed threshold; the
CLI prints a human-readable report and exits nonzero when any threshold is
missed. ``tests/test_evals.py`` asserts the same thresholds in CI.

Run standalone: ``python -m evals.run_eval`` (or ``make eval``).
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from evals.dataset import (
    AS_OF,
    assets_by_id,
    build_ingested_store,
    load_labels,
    session_factory,
)
from evals.metrics import (
    AbstentionReport,
    PrecisionRecall,
    StateExpectation,
    abstention_correctness,
    precision_recall,
    primary_hit_at_k,
)
from insmart_api.extractors import (
    DeterministicExtractor,
    ObservationCategory,
    WorkOrderText,
    work_order_text,
)
from insmart_api.models import Observation
from insmart_api.ranker.scoring import fleet_baseline_top_causes

MIN_PRECISION = 0.8
MIN_RECALL = 0.8
HIT_K = 3

# Adjudication states the harness expects, derived from the labels:
# a thin history must abstain; an unresolved contradiction must surface
# as contested (a resolved pair may rank — the conflict was settled).
ABSTAIN_STATE: StateExpectation = "insufficient_evidence"
CONTESTED_STATE: StateExpectation = "contested"


@dataclass(frozen=True)
class DiagnosisMetrics:
    """Hit@k of the physics-aware ranker vs. the frequency-only baseline."""

    k: int
    assets_measured: int
    ranker_hits: int
    baseline_hits: int

    def beats_baseline(self) -> bool:
        return self.ranker_hits > self.baseline_hits


@dataclass(frozen=True)
class EvalReport:
    """Everything the harness measured on one ingested store."""

    extraction: PrecisionRecall
    diagnosis: DiagnosisMetrics
    abstention: AbstentionReport


def extraction_metrics(session: Session, labels: Mapping[str, Any]) -> PrecisionRecall:
    """Defect-extraction precision/recall against the adjudicated evidence.

    Ground truth is the set of work orders the adjudicated
    ``known_failure_causes`` cite as evidence; the prediction is the set the
    deterministic extractor marks DEFECT. Runs over the observations the
    ingestion pipeline actually admitted.
    """
    rows = session.scalars(select(Observation)).all()
    work_orders: list[WorkOrderText] = []
    for observation in rows:
        payload: dict[str, Any] = json.loads(observation.payload)
        completed_at = payload.get("completed_at")
        work_orders.append(
            work_order_text(
                observation.id,
                payload,
                datetime.fromisoformat(payload["created_at"]),
                (
                    datetime.fromisoformat(completed_at)
                    if completed_at
                    else None
                ),
            )
        )

    predicted = {
        finding.work_order_id
        for work_order in work_orders
        for finding in DeterministicExtractor().extract(work_order)
        if finding.category is ObservationCategory.DEFECT
    }
    ingested_ids = {work_order.work_order_id for work_order in work_orders}
    actual = {
        evidence["work_order_id"]
        for asset in labels["assets"]
        for cause in asset["known_failure_causes"]
        for evidence in cause["evidence"]
    } & ingested_ids
    return precision_recall(predicted, actual)


def _diagnose(client: TestClient, asset_id: str) -> dict[str, Any]:
    response = client.get(f"/assets/{asset_id}/diagnosis", params={"as_of": AS_OF})
    assert response.status_code == 200, response.text
    diagnosis: dict[str, Any] = response.json()
    return diagnosis


def diagnosis_metrics(client: TestClient, labels: Mapping[str, Any]) -> DiagnosisMetrics:
    """Hit@3 vs. the frequency baseline, on the assets with adjudicated causes.

    The baseline is ``scoring.fleet_baseline_top_causes``: corpus-wide cause
    frequency built from the ranker's own output (the same support the
    diagnosis tests use) — the naive alternative the ranker must beat.
    """
    catalogue = assets_by_id(labels)
    cause_assets = {
        asset_id: asset
        for asset_id, asset in catalogue.items()
        if asset["known_failure_causes"]
    }

    corpus_support: Counter[str] = Counter()
    for asset_id in cause_assets:
        for cause in _diagnose(client, asset_id).get("causes", []):
            corpus_support[cause["cause"]] += cause["observation_count"]
    baseline_top = fleet_baseline_top_causes(corpus_support, k=HIT_K)

    ranker_hits = 0
    baseline_hits = 0
    for asset_id, asset in cause_assets.items():
        ranked = [
            cause["cause"] for cause in _diagnose(client, asset_id).get("causes", [])
        ]
        primary = (asset["known_failure_causes"][0]["cause"],)
        ranker_hits += int(primary_hit_at_k(ranked, primary, HIT_K))
        baseline_hits += int(primary_hit_at_k(baseline_top, primary, HIT_K))
    return DiagnosisMetrics(
        k=HIT_K,
        assets_measured=len(cause_assets),
        ranker_hits=ranker_hits,
        baseline_hits=baseline_hits,
    )


def abstention_metrics(client: TestClient, labels: Mapping[str, Any]) -> AbstentionReport:
    """Thin-history assets must abstain; unresolved contradictions must contest."""
    catalogue = assets_by_id(labels)
    expected: dict[str, StateExpectation] = {}
    for asset_id, asset in catalogue.items():
        if not asset["evidence_sufficiency"]["sufficient"]:
            expected[asset_id] = ABSTAIN_STATE
        elif any(
            pair["adjudication"] == "unresolved"
            for pair in asset["contradiction_pairs"]
        ):
            expected[asset_id] = CONTESTED_STATE
    actual_states = {
        asset_id: _diagnose(client, asset_id)["state"]
        for asset_id in sorted(expected)
    }
    return abstention_correctness(actual_states, expected)


def evaluate(client: TestClient, labels: Mapping[str, Any]) -> EvalReport:
    """Run all three metric groups against one ingested store."""
    session = session_factory(client)()
    try:
        extraction = extraction_metrics(session, labels)
    finally:
        session.close()
    return EvalReport(
        extraction=extraction,
        diagnosis=diagnosis_metrics(client, labels),
        abstention=abstention_metrics(client, labels),
    )


def threshold_violations(report: EvalReport) -> list[str]:
    """Every missed threshold, as a human-readable string. Empty = all pass."""
    violations: list[str] = []
    extraction = report.extraction
    if extraction.precision < MIN_PRECISION:
        violations.append(
            f"extraction precision {extraction.precision:.3f} < {MIN_PRECISION}"
        )
    if extraction.recall < MIN_RECALL:
        violations.append(f"extraction recall {extraction.recall:.3f} < {MIN_RECALL}")
    if not report.diagnosis.beats_baseline():
        violations.append(
            f"hit@{report.diagnosis.k} {report.diagnosis.ranker_hits}/"
            f"{report.diagnosis.assets_measured} did not beat the frequency "
            f"baseline ({report.diagnosis.baseline_hits}/"
            f"{report.diagnosis.assets_measured})"
        )
    if not report.abstention.correct:
        for asset_id, expected, actual in report.abstention.mismatches:
            violations.append(
                f"abstention mismatch {asset_id}: expected {expected}, got {actual}"
            )
    return violations


def format_report(report: EvalReport) -> str:
    """The human-readable evaluation report."""
    extraction = report.extraction
    diagnosis = report.diagnosis
    abstention_ok = report.abstention.checked - len(report.abstention.mismatches)
    lines = [
        "Insmart AI evaluation — synthetic seed corpus vs. adjudicated labels",
        f"  extraction P/R:      {extraction.precision:.3f} / {extraction.recall:.3f} "
        f"(threshold ≥ {MIN_PRECISION} / {MIN_RECALL}; "
        f"{extraction.true_positives} true positives, "
        f"{extraction.predicted_total} predicted, {extraction.actual_total} adjudicated)",
        f"  diagnosis hit@{diagnosis.k}:        ranker {diagnosis.ranker_hits}/"
        f"{diagnosis.assets_measured} vs. frequency baseline "
        f"{diagnosis.baseline_hits}/{diagnosis.assets_measured}",
        f"  abstention correctness: {abstention_ok}/"
        f"{report.abstention.checked} assets in their adjudicated state",
    ]
    for asset_id, expected, actual in report.abstention.mismatches:
        lines.append(f"    MISMATCH {asset_id}: expected {expected}, got {actual}")
    return "\n".join(lines)


def main() -> int:
    """CLI entry point: report, gate on thresholds, exit 0/1."""
    labels = load_labels()
    with tempfile.TemporaryDirectory() as tmp:
        client = build_ingested_store(Path(tmp) / "eval.db")
        report = evaluate(client, labels)
    print(format_report(report))
    violations = threshold_violations(report)
    if violations:
        print("\nFAILED — missed thresholds:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("\nPASSED — all thresholds met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
