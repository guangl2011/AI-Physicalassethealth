"""The evaluation harness as CI gates — the D3 acceptance thresholds.

These tests run the same ``evals.run_eval`` harness the CLI reports, against
the adjudicated seed labels (synthetic corpus — see ``docs/testing-plan.md``
§0). A regression in extraction, ranking, or abstention breaks the build
here first.

``threshold_violations`` is the single gate the CLI exits on; the per-metric
tests below exist so a failure names the broken layer directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from evals.dataset import AS_OF, build_ingested_store, session_factory
from evals.metrics import primary_hit_at_k
from evals.run_eval import (
    HIT_K,
    MIN_PRECISION,
    MIN_RECALL,
    abstention_metrics,
    diagnosis_metrics,
    evaluate,
    extraction_metrics,
    threshold_violations,
)
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def eval_store(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    """One ingested seed store shared by the harness tests in this module."""
    return build_ingested_store(tmp_path_factory.mktemp("eval-store") / "eval.db")


def test_extraction_precision_and_recall_meet_threshold(
    eval_store: TestClient, labels: Mapping[str, Any]
) -> None:
    """Extraction P/R ≥ 0.8 against the adjudicated defect evidence."""
    session = session_factory(eval_store)()
    try:
        extraction = extraction_metrics(session, labels)
    finally:
        session.close()
    assert extraction.precision >= MIN_PRECISION, extraction
    assert extraction.recall >= MIN_RECALL, extraction


def test_ranker_hit3_beats_frequency_baseline(
    eval_store: TestClient, labels: Mapping[str, Any]
) -> None:
    """The physics-aware ranker's hit@3 strictly beats the frequency baseline."""
    metrics = diagnosis_metrics(eval_store, labels)
    assert metrics.assets_measured > 0, "no adjudicated-cause assets found"
    assert metrics.ranker_hits > metrics.baseline_hits, metrics


def test_primary_adjudicated_cause_is_in_top3(
    eval_store: TestClient, labels: Mapping[str, Any]
) -> None:
    """The spec's literal metric: each asset's primary cause in the top-3."""
    catalogue = {
        asset["asset_id"]: asset
        for asset in labels["assets"]
        if asset["known_failure_causes"]
    }
    for asset_id, asset in catalogue.items():
        diagnosis = eval_store.get(
            f"/assets/{asset_id}/diagnosis", params={"as_of": AS_OF}
        )
        assert diagnosis.status_code == 200, diagnosis.text
        ranked = [cause["cause"] for cause in diagnosis.json()["causes"]]
        primary = (asset["known_failure_causes"][0]["cause"],)
        assert primary_hit_at_k(ranked, primary, HIT_K), (asset_id, ranked)


def test_abstention_cases_abstain(
    eval_store: TestClient, labels: Mapping[str, Any]
) -> None:
    """Thin histories abstain and unresolved contradictions contest — no misses."""
    report = abstention_metrics(eval_store, labels)
    assert report.checked == 18, report  # 16 thin assets + 2 unresolved pairs
    assert report.mismatches == (), report.mismatches


def test_harness_reports_zero_threshold_violations(
    eval_store: TestClient, labels: Mapping[str, Any]
) -> None:
    """The single gate the CLI exits on: no threshold is missed."""
    assert threshold_violations(evaluate(eval_store, labels)) == []
