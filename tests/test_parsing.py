"""Parser and entity-resolution tests over the seed corpus's malformed variants."""

from __future__ import annotations

from datetime import datetime

import pytest

from insmart_api.ingestion.parsing import (
    COLUMNS,
    HeaderError,
    ParseFailure,
    WorkOrderRow,
    column_index,
    compose_observation_text,
    parse_row,
    split_csv,
    validate_header,
)
from insmart_api.ingestion.resolution import (
    Ambiguous,
    AssetDescriptor,
    AssetIndex,
    Resolved,
    Unresolvable,
)

# The known-ambiguous corpus inventory: AHU-3 and RTU-3 share unit number 3.
CORPUS_LIKE_INDEX = AssetIndex.build(
    [
        AssetDescriptor(asset_id="AHU-3", equipment_type="Rooftop Unit"),
        AssetDescriptor(asset_id="RTU-3", equipment_type="Rooftop Unit"),
        AssetDescriptor(asset_id="AHU-1", equipment_type="Air Handler"),
    ]
)


def _row(work_order_id: str = "WO-1", **overrides: str) -> list[str]:
    """A fully valid corpus row, with per-field overrides."""
    fields = {
        "work_order_id": work_order_id,
        "created_at": "2025-01-15T08:30:00",
        "completed_at": "2025-01-15T11:45:00",
        "site": "Harborview",
        "asset_tag": "AHU-1",
        "summary": "No cooling",
        "technician": "J. Rivera",
        "notes": "Compressor draws high amps.",
        "resolution": "Replaced capacitor",
        "labor_hours": "2.5",
        "priority": "P2",
    }
    fields.update(overrides)
    return [fields[column] for column in COLUMNS]


def _parse(cells: list[str]) -> object:
    return parse_row(1, column_index(COLUMNS), cells)


# --- row parsing ---------------------------------------------------------------


def test_valid_row_parses_with_normalized_fields() -> None:
    outcome = _parse(_row(asset_tag="  ahu-1 "))
    assert isinstance(outcome, WorkOrderRow)
    assert outcome.row_number == 1
    assert outcome.work_order_id == "WO-1"
    # Parsing strips whitespace but keeps the raw spelling — case
    # normalization to a registered asset happens at entity resolution.
    assert outcome.asset_tag == "ahu-1"
    assert outcome.created_at == datetime(2025, 1, 15, 8, 30)
    assert outcome.completed_at == datetime(2025, 1, 15, 11, 45)
    assert outcome.labor_hours == 2.5
    assert outcome.fields["summary"] == "No cooling"


def test_ragged_row_fails_with_human_readable_reason() -> None:
    outcome = _parse(_row()[:-1])
    assert isinstance(outcome, ParseFailure)
    assert "columns" in outcome.reason


def test_ragged_row_keeps_the_raw_work_order_id() -> None:
    outcome = _parse(_row(work_order_id="WO-77")[:-1])
    assert isinstance(outcome, ParseFailure)
    assert outcome.external_id == "WO-77"


def test_missing_created_at_fails() -> None:
    outcome = _parse(_row(created_at=""))
    assert isinstance(outcome, ParseFailure)
    assert "created_at" in outcome.reason


@pytest.mark.parametrize(
    "bad", ["2026-13-45T09:00:00", "not-a-date", "31/02/2024 10:00:00"]
)
def test_invalid_created_at_fails(bad: str) -> None:
    outcome = _parse(_row(created_at=bad))
    assert isinstance(outcome, ParseFailure)
    assert "ISO-8601" in outcome.reason


def test_missing_work_order_id_fails() -> None:
    outcome = _parse(_row(work_order_id="  "))
    assert isinstance(outcome, ParseFailure)
    assert "work_order_id" in outcome.reason


def test_missing_asset_tag_fails() -> None:
    outcome = _parse(_row(asset_tag=""))
    assert isinstance(outcome, ParseFailure)
    assert "asset_tag" in outcome.reason


def test_validate_header_rejects_missing_columns() -> None:
    with pytest.raises(HeaderError) as excinfo:
        validate_header(COLUMNS[1:])
    assert "missing required columns" in str(excinfo.value)


def test_validate_header_accepts_column_reordering() -> None:
    validate_header(list(reversed(COLUMNS)))


def test_split_csv_respects_quoted_commas() -> None:
    assert split_csv('a,"b,c"\n"d",e') == [["a", "b,c"], ["d", "e"]]


def test_composed_observation_text_carries_the_fields() -> None:
    row = _row()
    outcome = _parse(row)
    assert isinstance(outcome, WorkOrderRow)
    text = compose_observation_text(outcome.fields)
    assert "No cooling" in text
    assert "Replaced capacitor" in text


# --- entity resolution ---------------------------------------------------------


def test_exact_id_resolves() -> None:
    resolution = CORPUS_LIKE_INDEX.resolve("AHU-1")
    assert isinstance(resolution, Resolved)
    assert resolution.asset_id == "AHU-1"


def test_case_and_whitespace_are_normalized() -> None:
    resolution = CORPUS_LIKE_INDEX.resolve("  ahu-1 ")
    assert isinstance(resolution, Resolved)
    assert resolution.asset_id == "AHU-1"


def test_equipment_alias_resolves() -> None:
    resolution = CORPUS_LIKE_INDEX.resolve("Air Handler 1")
    assert isinstance(resolution, Resolved)
    assert resolution.asset_id == "AHU-1"


def test_unit_number_resolves_when_unambiguous() -> None:
    index = AssetIndex.build(
        [
            AssetDescriptor(asset_id="AHU-1", equipment_type="Air Handler"),
            AssetDescriptor(asset_id="CHWS-5", equipment_type="Chiller"),
        ]
    )
    resolution = index.resolve("1")
    assert isinstance(resolution, Resolved)
    assert resolution.asset_id == "AHU-1"


def test_shared_unit_number_is_ambiguous() -> None:
    resolution = CORPUS_LIKE_INDEX.resolve("3")
    assert isinstance(resolution, Ambiguous)
    assert "AHU-3" in resolution.reason
    assert "RTU-3" in resolution.reason


@pytest.mark.parametrize("tag", ["Unit 3", "unit 3", "bldg 2 unit 3", "RTU/AHU 3"])
def test_corpus_ambiguity_variants_route_to_review(tag: str) -> None:
    resolution = CORPUS_LIKE_INDEX.resolve(tag)
    assert isinstance(resolution, Ambiguous)
    assert "ambiguous" in resolution.reason


def test_unknown_but_wellformed_tag_is_unresolvable() -> None:
    resolution = CORPUS_LIKE_INDEX.resolve("CHILLER-99")
    assert isinstance(resolution, Unresolvable)


def test_garbage_tag_is_unresolvable() -> None:
    resolution = CORPUS_LIKE_INDEX.resolve("RTU-???")
    assert isinstance(resolution, Unresolvable)


def test_empty_tag_is_unresolvable() -> None:
    resolution = CORPUS_LIKE_INDEX.resolve("")
    assert isinstance(resolution, Unresolvable)
