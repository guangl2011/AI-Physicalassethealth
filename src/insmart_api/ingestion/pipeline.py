"""Ingestion pipeline: parse → extract-prepare → entity-resolve → dedup → persist.

The pipeline is the only writer of observations and review items. Every
input row ends in exactly one of three buckets — an observation, a
dedup collapse, or a review item with a human-readable reason — and the
counts are persisted on the run so zero-silent-drops stays checkable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from insmart_api.ingestion.dedup import (
    DuplicateDetector,
    content_fingerprint,
    row_content,
    stored_content_from_payload,
)
from insmart_api.ingestion.parsing import (
    ParseFailure,
    WorkOrderRow,
    column_index,
    compose_observation_text,
    parse_row,
    split_csv,
    validate_header,
)
from insmart_api.ingestion.resolution import (
    AssetDescriptor,
    AssetIndex,
    Resolved,
)
from insmart_api.integrity import make_source_ref
from insmart_api.models import Asset, IngestRun, Observation, ReviewItem

_CANONICAL_ASSET_ID = re.compile(r"^[A-Z]{1,8}-[0-9]{1,6}$")


class IngestionError(ValueError):
    """A bulk-ingestion request that cannot be processed at all."""


class AssetRegistrationError(ValueError):
    """An asset-inventory registration failure (validation or conflict)."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ReviewEntry:
    """One row routed to the review list, with the human-readable why."""

    row_number: int
    external_id: str | None
    reason: str
    raw_row: list[str]


@dataclass(frozen=True)
class IngestReport:
    """Outcome of one bulk-ingestion run (also persisted as IngestRun)."""

    run_id: int
    source_name: str
    rows_total: int
    rows_ingested: int
    rows_deduplicated: int
    rows_reviewed: int
    review: list[ReviewEntry]


def build_asset_index(session: Session) -> AssetIndex:
    """Build the entity-resolution index over the registered asset inventory."""
    rows = session.execute(select(Asset.id, Asset.equipment_type)).all()
    return AssetIndex.build(
        AssetDescriptor(asset_id=asset_id, equipment_type=equipment_type)
        for asset_id, equipment_type in rows
    )


def register_assets(
    session: Session, entries: Iterable[Mapping[str, Any]]
) -> list[str]:
    """Validate and insert asset-inventory rows; return the registered ids.

    Accepts the canonical field names (``asset_id``/``site_id``) and also the
    ``site`` key used by the adjudicated labels. Raises
    ``AssetRegistrationError`` (with an HTTP status) on invalid rows or on
    duplicates — within the batch or against the database.
    """
    registered: list[str] = []
    for entry in entries:
        asset_id = str(entry.get("asset_id", "")).strip().upper()
        site_id = str(entry.get("site_id") or entry.get("site") or "").strip()
        equipment_type = str(entry.get("equipment_type", "")).strip()
        installed_year = entry.get("installed_year")
        if not _CANONICAL_ASSET_ID.match(asset_id):
            raise AssetRegistrationError(
                f"invalid asset id {asset_id!r} — expected the form 'AHU-3'"
            )
        if not site_id:
            raise AssetRegistrationError(f"asset {asset_id}: site_id is missing")
        if not equipment_type:
            raise AssetRegistrationError(
                f"asset {asset_id}: equipment_type is missing"
            )
        if installed_year is not None:
            if not isinstance(installed_year, int) or not 1800 <= installed_year <= 2100:
                raise AssetRegistrationError(
                    f"asset {asset_id}: installed_year must be a plausible year"
                )
        if session.get(Asset, asset_id) is not None:
            raise AssetRegistrationError(
                f"asset {asset_id} is already registered", status_code=409
            )
        session.add(
            Asset(
                id=asset_id,
                site_id=site_id,
                equipment_type=equipment_type,
                installed_year=installed_year,
            )
        )
        registered.append(asset_id)
    return registered


def _build_observation(row: WorkOrderRow, asset_id: str, source_name: str) -> Observation:
    """Extract-prepare: an observed observation with full provenance.

    Ingestion stops here — text and structured fields are stored for the
    downstream extraction task; no extraction or diagnosis happens yet.
    """
    content = row_content(row)
    payload = {**content, "source_file": source_name, "source_row": row.row_number}
    return Observation(
        id=row.work_order_id,
        asset_id=asset_id,
        source_ref=make_source_ref(row.work_order_id),
        recorded_at=row.created_at,
        kind="observed",
        text=compose_observation_text(row.fields),
        evidence_ids=None,
        confidence=None,
        content_hash=content_fingerprint(content),
        payload=json.dumps(payload, sort_keys=True),
    )


def ingest_work_orders(session: Session, source_name: str, csv_text: str) -> IngestReport:
    """Run the full ingestion pipeline over one CSV file and persist the outcome."""
    rows = split_csv(csv_text)
    if not rows:
        raise IngestionError("uploaded CSV is empty")
    header, data = rows[0], rows[1:]
    validate_header(header)

    asset_index = build_asset_index(session)
    if not asset_index.by_alias:
        raise IngestionError(
            "no assets registered — register the asset inventory before ingesting work orders"
        )

    stored = session.execute(
        select(Observation.id, Observation.content_hash, Observation.payload)
    ).all()
    detector = DuplicateDetector(
        stored_hashes={observation_id: content_hash for observation_id, content_hash, _ in stored},
        stored_content={
            observation_id: stored_content_from_payload(payload)
            for observation_id, _, payload in stored
        },
    )
    columns = column_index(header)

    review: list[ReviewEntry] = []
    prepared: list[Observation] = []
    deduplicated = 0
    for row_number, cells in enumerate(data, start=1):
        outcome = parse_row(row_number, columns, cells)
        if isinstance(outcome, ParseFailure):
            review.append(
                ReviewEntry(outcome.row_number, outcome.external_id, outcome.reason, cells)
            )
            continue
        resolution = asset_index.resolve(outcome.asset_tag)
        if not isinstance(resolution, Resolved):
            review.append(
                ReviewEntry(row_number, outcome.work_order_id, resolution.reason, cells)
            )
            continue
        verdict = detector.classify(outcome)
        if verdict.status == "collapsed":
            deduplicated += 1
            continue
        if verdict.status == "conflict":
            fields = ", ".join(verdict.differing_fields) or "content"
            review.append(
                ReviewEntry(
                    row_number,
                    outcome.work_order_id,
                    (
                        f"conflicting duplicate for work order {outcome.work_order_id} — "
                        f"field(s) {fields} differ from the earlier record"
                    ),
                    cells,
                )
            )
            continue
        prepared.append(_build_observation(outcome, resolution.asset_id, source_name))

    run = IngestRun(
        source_name=source_name,
        rows_total=len(data),
        rows_ingested=len(prepared),
        rows_deduplicated=deduplicated,
        rows_reviewed=len(review),
        created_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()  # assign run.id before persisting children
    for observation in prepared:
        session.add(observation)
    for entry in review:
        session.add(
            ReviewItem(
                run_id=run.id,
                source_name=source_name,
                row_number=entry.row_number,
                external_id=entry.external_id,
                reason=entry.reason,
                raw_row=json.dumps(entry.raw_row),
            )
        )

    return IngestReport(
        run_id=run.id,
        source_name=source_name,
        rows_total=len(data),
        rows_ingested=len(prepared),
        rows_deduplicated=deduplicated,
        rows_reviewed=len(review),
        review=review,
    )
