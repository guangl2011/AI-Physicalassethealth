"""CSV row parsing and validation for work-order ingestion.

Pure stage: raw CSV cells in, either a prepared work-order record or a
parse failure with a human-readable reason. Nothing here touches the
database — failures are surfaced, never dropped.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

COLUMNS: tuple[str, ...] = (
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
)


class HeaderError(ValueError):
    """The CSV header does not carry the required columns."""


class RowValidationError(ValueError):
    """A field-level parse failure for one CSV row; str() is the reason."""


@dataclass(frozen=True)
class WorkOrderRow:
    """A validated work-order row: width and required fields hold."""

    row_number: int
    work_order_id: str
    created_at: datetime
    completed_at: datetime | None
    asset_tag: str
    labor_hours: float | None
    fields: dict[str, str]  # stripped raw text of every column, by name


@dataclass(frozen=True)
class ParseFailure:
    """A row that could not be parsed, with the human-readable why."""

    row_number: int
    external_id: str | None
    reason: str


RowOutcome = WorkOrderRow | ParseFailure


def split_csv(text: str) -> list[list[str]]:
    """Parse CSV text into rows of raw cells, skipping blank lines."""
    return [row for row in csv.reader(io.StringIO(text, newline="")) if any(row)]


def validate_header(header: list[str]) -> None:
    """Raise ``HeaderError`` if any required column is missing."""
    missing = [column for column in COLUMNS if column not in header]
    if missing:
        raise HeaderError(
            f"CSV header is missing required columns: {', '.join(missing)}"
        )


def column_index(header: list[str]) -> dict[str, int]:
    """Map column names to their positions in the header row."""
    return {name: position for position, name in enumerate(header)}


def compose_observation_text(fields: dict[str, str]) -> str:
    """Compose the observation's textual content from the free-text fields."""
    parts = (fields.get("summary"), fields.get("notes"), fields.get("resolution"))
    return " | ".join(part for part in parts if part)


def _require_timestamp(value: str, column: str) -> datetime:
    if not value:
        raise RowValidationError(f"{column} is missing")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise RowValidationError(
            f"{column} is not a valid ISO-8601 timestamp: '{value}'"
        ) from error


def _optional_timestamp(value: str, column: str) -> datetime | None:
    if not value:
        return None
    return _require_timestamp(value, column)


def _optional_number(value: str, column: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise RowValidationError(f"{column} is not a valid number: '{value}'") from error


def _validate_fields(
    fields: dict[str, str],
) -> tuple[datetime, datetime | None, float | None]:
    """Validate required/optional fields; raise ``RowValidationError`` on failure."""
    if not fields["work_order_id"]:
        raise RowValidationError("work_order_id is missing")
    created_at = _require_timestamp(fields["created_at"], "created_at")
    completed_at = _optional_timestamp(fields["completed_at"], "completed_at")
    labor_hours = _optional_number(fields["labor_hours"], "labor_hours")
    if not fields["asset_tag"]:
        raise RowValidationError("asset_tag is missing")
    if not compose_observation_text(fields):
        raise RowValidationError(
            "observation text is empty (summary, notes and resolution are all blank)"
        )
    return created_at, completed_at, labor_hours


def parse_row(row_number: int, index: dict[str, int], cells: list[str]) -> RowOutcome:
    """Validate and prepare one CSV row, or explain why it cannot be parsed."""
    external_id = (cells[0].strip() or None) if cells else None
    if len(cells) != len(index):
        return ParseFailure(
            row_number=row_number,
            external_id=external_id,
            reason=f"row has {len(cells)} columns, expected {len(index)}",
        )
    fields = {name: cells[position].strip() for name, position in index.items()}
    try:
        created_at, completed_at, labor_hours = _validate_fields(fields)
    except RowValidationError as error:
        return ParseFailure(row_number, fields["work_order_id"] or None, str(error))

    return WorkOrderRow(
        row_number=row_number,
        work_order_id=fields["work_order_id"],
        created_at=created_at,
        completed_at=completed_at,
        asset_tag=fields["asset_tag"],
        labor_hours=labor_hours,
        fields=fields,
    )
