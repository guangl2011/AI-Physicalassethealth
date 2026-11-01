"""Tests for the seed corpus generator and the adjudicated label schema."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = REPO_ROOT / "seed"
GENERATOR = SEED_DIR / "generate_corpus.py"


def _generate(out_dir: Path, seed: int = 42) -> None:
    subprocess.run(
        [sys.executable, str(GENERATOR), "--out-dir", str(out_dir), "--seed", str(seed)],
        check=True,
        capture_output=True,
    )


def _read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def _read_labels(directory: Path) -> dict[str, object]:
    return json.loads((directory / "labels.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("seed-corpus")
    _generate(out)
    return out


@pytest.fixture(scope="module")
def header(corpus_dir: Path) -> list[str]:
    header_row, _ = _read_rows(corpus_dir / "corpus.csv")
    return header_row


@pytest.fixture(scope="module")
def data_rows(corpus_dir: Path) -> list[list[str]]:
    _, rows = _read_rows(corpus_dir / "corpus.csv")
    return rows


@pytest.fixture(scope="module")
def labels(corpus_dir: Path) -> dict[str, object]:
    return _read_labels(corpus_dir)


# --- reproducibility ---------------------------------------------------------


def test_generator_is_reproducible(tmp_path: Path) -> None:
    _generate(tmp_path / "a")
    _generate(tmp_path / "b")
    for name in ("corpus.csv", "labels.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_committed_artifacts_match_generator(tmp_path: Path) -> None:
    _generate(tmp_path)
    for name in ("corpus.csv", "labels.json"):
        committed = (SEED_DIR / name).read_bytes()
        assert committed == (tmp_path / name).read_bytes(), (
            f"committed seed/{name} is stale — rerun "
            f"'python seed/generate_corpus.py' and commit the output"
        )


def test_different_seed_produces_different_corpus(tmp_path: Path) -> None:
    _generate(tmp_path, seed=7)
    assert (tmp_path / "corpus.csv").read_bytes() != (SEED_DIR / "corpus.csv").read_bytes()


# --- corpus shape and counts -------------------------------------------------


def test_work_order_count_is_about_150(data_rows: list[list[str]]) -> None:
    assert 140 <= len(data_rows) <= 160


def test_asset_count_is_about_20(labels: dict[str, object]) -> None:
    assets = labels["assets"]
    assert isinstance(assets, list)
    assert 18 <= len(assets) <= 22  # type: ignore[arg-type]


def test_row_widths_and_header(
    header: list[str], data_rows: list[list[str]]
) -> None:
    assert header == [
        "work_order_id",
        "created_at",
        "completed_at",
        "site",
        "asset_tag",
        "summary",
        "technician",
        "notes",
        "resolution",
        "labor_hours",
        "priority",
    ]
    widths = {len(row) for row in data_rows}
    assert widths == {len(header), len(header) - 1}  # exactly one ragged row


# --- malformed rows ----------------------------------------------------------


def _column(header: list[str], row: list[str], name: str) -> str:
    return row[header.index(name)]


def test_invalid_dates_present(header: list[str], data_rows: list[list[str]]) -> None:
    bad = []
    for row in data_rows:
        if len(row) != len(header):
            continue
        value = _column(header, row, "created_at")
        if not value:
            bad.append(value)
            continue
        try:
            datetime.fromisoformat(value)
        except ValueError:
            bad.append(value)
    assert len(bad) >= 3


def test_duplicate_work_order_ids_present(data_rows: list[list[str]]) -> None:
    ids = [row[0] for row in data_rows]
    duplicated = {wo_id for wo_id in ids if ids.count(wo_id) > 1}
    assert len(duplicated) >= 2


def test_unresolvable_asset_tags_present(
    header: list[str], data_rows: list[list[str]]
) -> None:
    tags = {_column(header, row, "asset_tag") for row in data_rows if len(row) == len(header)}
    assert {"CHILLER-99", "RTU-???"} <= tags


def test_ambiguous_asset_tags_present(
    header: list[str], data_rows: list[list[str]]
) -> None:
    tags = {_column(header, row, "asset_tag") for row in data_rows if len(row) == len(header)}
    assert "Unit 3" in tags


# --- label schema ------------------------------------------------------------


def test_label_top_level_schema(labels: dict[str, object]) -> None:
    assert labels["schema_version"] == "1.0.0"
    assert labels["generator_seed"] == 42
    corpus = labels["corpus"]
    assert isinstance(corpus, dict)
    assert corpus["work_order_count"] == 150  # type: ignore[union-attr,index]
    assert corpus["asset_count"] == 20  # type: ignore[union-attr,index]
    assert corpus["malformed_row_count"] == 9  # type: ignore[union-attr,index]


REQUIRED_ASSET_KEYS = {
    "asset_id",
    "site",
    "equipment_type",
    "installed_year",
    "work_order_count",
    "known_failure_causes",
    "evidence_sufficiency",
    "contradiction_pairs",
    "provenance",
}


def test_label_asset_schema(labels: dict[str, object]) -> None:
    assets = labels["assets"]
    assert isinstance(assets, list)
    seen: set[str] = set()
    for asset in assets:  # type: ignore[union-attr]
        assert REQUIRED_ASSET_KEYS <= set(asset)
        assert asset["asset_id"] not in seen, "duplicate asset in labels"
        seen.add(str(asset["asset_id"]))
        assert isinstance(asset["work_order_count"], int)
        sufficiency = asset["evidence_sufficiency"]
        assert isinstance(sufficiency["sufficient"], bool)
        assert isinstance(sufficiency["reason"], str) and sufficiency["reason"]
        assert isinstance(asset["provenance"]["work_order_ids"], list)
        for pair in asset["contradiction_pairs"]:
            assert {"claim_a", "claim_b", "adjudication"} <= set(pair)
            assert pair["adjudication"]
        for cause in asset["known_failure_causes"]:
            assert {"cause", "work_order_ids", "evidence", "first_observed",
                    "last_observed"} <= set(cause)
            assert cause["work_order_ids"], "cause without evidence work orders"
            for item in cause["evidence"]:
                assert {"work_order_id", "field", "quote"} <= set(item)
                assert item["quote"]
            assert cause["first_observed"] <= cause["last_observed"]


def test_label_provenance_resolves_into_corpus(
    header: list[str], data_rows: list[list[str]], labels: dict[str, object]
) -> None:
    corpus_ids = {row[0] for row in data_rows}
    assets = labels["assets"]
    assert isinstance(assets, list)
    for asset in assets:  # type: ignore[union-attr]
        provenance = asset["provenance"]["work_order_ids"]
        assert set(provenance) <= corpus_ids  # type: ignore[arg-type]
        assert len(provenance) == asset["work_order_count"]
        for cause in asset["known_failure_causes"]:
            assert set(cause["work_order_ids"]) <= set(provenance)  # type: ignore[arg-type]
        for pair in asset["contradiction_pairs"]:
            claim_ids = {pair["claim_a"].split(":")[0], pair["claim_b"].split(":")[0]}
            assert claim_ids <= corpus_ids


def test_evidence_quotes_appear_in_corpus(
    header: list[str], data_rows: list[list[str]], labels: dict[str, object]
) -> None:
    by_id: dict[str, dict[int, str]] = {}
    for row in data_rows:
        if len(row) == len(header):
            by_id[row[0]] = dict(enumerate(row))
    assets = labels["assets"]
    assert isinstance(assets, list)
    for asset in assets:  # type: ignore[union-attr]
        for cause in asset["known_failure_causes"]:
            for item in cause["evidence"]:
                row = by_id[item["work_order_id"]]
                col = header.index(item["field"])
                assert item["quote"] in row[col]


def test_sufficiency_flags_consistent(labels: dict[str, object]) -> None:
    assets = labels["assets"]
    assert isinstance(assets, list)
    threshold = labels["sufficiency_threshold_resolvable_orders"]
    for asset in assets:  # type: ignore[union-attr]
        expected = asset["work_order_count"] >= threshold
        assert asset["evidence_sufficiency"]["sufficient"] is expected


def test_thin_history_assets_exist_for_abstention(labels: dict[str, object]) -> None:
    assets = labels["assets"]
    assert isinstance(assets, list)
    thin = [a for a in assets if not a["evidence_sufficiency"]["sufficient"]]  # type: ignore[union-attr]
    assert len(thin) >= 3
    # thin-history assets carry no failure-cause labels — abstention has nothing to rank
    assert all(not a["known_failure_causes"] for a in thin)  # type: ignore[union-attr]


def test_contradiction_pairs_exist_with_both_adjudication_kinds(
    labels: dict[str, object],
) -> None:
    assets = labels["assets"]
    assert isinstance(assets, list)
    pairs = [
        pair
        for asset in assets  # type: ignore[union-attr]
        for pair in asset["contradiction_pairs"]
    ]
    assert len(pairs) >= 2
    assert any(p["adjudication"] == "unresolved" for p in pairs)
    assert any(p["adjudication"].startswith("resolved") for p in pairs)
