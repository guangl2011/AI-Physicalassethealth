"""Duplicate detection for ingested work orders.

An exact repeat (same work order id, same content) collapses into the
record already accepted. A same-id row with differing content is a
conflict that routes to review — the pipeline never picks a winner.
Neither outcome is ever silent: both are counted in the run summary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from insmart_api.ingestion.parsing import WorkOrderRow

# The semantic fields whose equality defines "same work order, same content".
# ``asset_id`` is the entity RESOLVED by the previous stage — the raw
# asset_tag spelling is provenance, not identity, so a re-export that says
# 'ahu-1' where the original said 'AHU-1' is still the same record.
# Provenance fields (source file/row) are excluded for the same reason:
# re-uploading the same record under a different file name is the same record.
SEMANTIC_FIELDS: tuple[str, ...] = (
    "work_order_id",
    "recorded_at",
    "completed_at",
    "site",
    "asset_id",
    "summary",
    "technician",
    "notes",
    "resolution",
    "labor_hours",
    "priority",
)


def row_content(row: WorkOrderRow, asset_id: str) -> dict[str, Any]:
    """Canonical content map for one parsed work-order row.

    ``asset_id`` is the asset the row resolved to during entity resolution.
    """
    return {
        "work_order_id": row.work_order_id,
        "recorded_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "site": row.fields["site"],
        "asset_id": asset_id,
        "summary": row.fields["summary"],
        "technician": row.fields["technician"],
        "notes": row.fields["notes"],
        "resolution": row.fields["resolution"],
        "labor_hours": row.labor_hours,
        "priority": row.fields["priority"],
    }


def content_fingerprint(content: dict[str, Any]) -> str:
    """Stable sha256 fingerprint over the semantic fields."""
    canonical = json.dumps(
        {key: content.get(key) for key in SEMANTIC_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def differing_fields(
    content: dict[str, Any], stored: dict[str, Any] | None
) -> tuple[str, ...]:
    """Semantic fields where two versions of the same work order disagree."""
    return tuple(
        key
        for key in SEMANTIC_FIELDS
        if content.get(key) != (stored or {}).get(key)
    )


@dataclass(frozen=True)
class DuplicateVerdict:
    """Outcome of duplicate classification for one parsed row.

    ``accepted`` — first occurrence; the row becomes an observation.
    ``collapsed`` — exact duplicate of an accepted/persisted record.
    ``conflict`` — same id, different content; routes to review with the
    differing fields named in the reason.
    """

    status: str
    differing_fields: tuple[str, ...] = field(default=())


class DuplicateDetector:
    """Classifies rows against content accepted in this run or persisted before.

    Seeded with observation id → content hash and observation id → stored
    semantic content (from the database, so dedup also works across runs),
    it records every row accepted during the current run. Re-uploading a
    file therefore collapses instead of duplicating.
    """

    def __init__(
        self,
        stored_hashes: dict[str, str] | None = None,
        stored_content: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._hashes: dict[str, str] = dict(stored_hashes or {})
        self._content: dict[str, dict[str, Any]] = {
            observation_id: dict(content)
            for observation_id, content in (stored_content or {}).items()
        }

    def classify(self, row: WorkOrderRow, asset_id: str) -> DuplicateVerdict:
        """Classify one parsed row as accepted, collapsed, or conflict.

        ``asset_id`` is the entity the row resolved to; identity is keyed on
        the resolved asset, never the raw tag spelling.
        """
        content = row_content(row, asset_id)
        fingerprint = content_fingerprint(content)
        stored_hash = self._hashes.get(row.work_order_id)
        if stored_hash is None:
            self._hashes[row.work_order_id] = fingerprint
            self._content[row.work_order_id] = content
            return DuplicateVerdict(status="accepted")
        if stored_hash == fingerprint:
            return DuplicateVerdict(status="collapsed")
        return DuplicateVerdict(
            status="conflict",
            differing_fields=differing_fields(content, self._content.get(row.work_order_id)),
        )


def stored_content_from_payload(payload_json: str) -> dict[str, Any]:
    """Extract the semantic content of a persisted observation from its payload.

    The payload carries the raw CSV cells plus canonical semantic fields and
    provenance (source_file/source_row); the semantic subset drives conflict
    diffs across runs.
    """
    payload: dict[str, Any] = json.loads(payload_json)
    return {key: payload.get(key) for key in SEMANTIC_FIELDS}
