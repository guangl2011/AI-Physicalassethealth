"""Graph-integrity tests over the ingested seed corpus.

Invariants: every observation carries a non-empty source_ref that resolves
to a real stored record with full provenance; ingestion only writes
`observed` rows (no inference exists without a downstream evidence chain);
and per-asset counts match the adjudicated labels exactly.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from insmart_api.ingestion.dedup import (
    content_fingerprint,
    stored_content_from_payload,
)
from insmart_api.models import Asset, Observation

SOURCE_REF_KIND = "work-order"


def _observations(session: Session) -> list[Observation]:
    rows = session.scalars(select(Observation)).all()
    assert rows, "the ingested corpus produced no observations"
    return list(rows)


def test_every_observation_has_a_non_empty_source_ref(db_session: Session) -> None:
    for observation in _observations(db_session):
        assert observation.source_ref, (
            f"observation {observation.id} has an empty source_ref"
        )


def test_every_source_ref_resolves_to_a_stored_record(db_session: Session) -> None:
    for observation in _observations(db_session):
        kind, _, external_id = observation.source_ref.partition(":")
        assert kind == SOURCE_REF_KIND
        assert external_id == observation.id, (
            "source_ref must name the record it points at"
        )
        payload = json.loads(observation.payload)
        assert payload["work_order_id"] == external_id
        assert payload["asset_id"] == observation.asset_id
        assert payload["source_file"], "record provenance is missing the source file"
        assert payload["source_row"] > 0


def test_every_observation_resolves_to_a_registered_asset(db_session: Session) -> None:
    asset_ids = set(db_session.scalars(select(Asset.id)).all())
    for observation in _observations(db_session):
        assert observation.asset_id in asset_ids, (
            f"observation {observation.id} points at unregistered asset"
            f" {observation.asset_id}"
        )


def test_ingestion_writes_only_observed_rows_without_inferred_evidence(
    db_session: Session,
) -> None:
    for observation in _observations(db_session):
        assert observation.kind == "observed"
        assert observation.evidence_ids is None
        assert observation.confidence is None


def test_content_hash_matches_the_stored_semantic_content(
    db_session: Session,
) -> None:
    # Cross-run consistency: the persisted hash must equal the fingerprint of
    # the semantic content recovered from the payload — otherwise a re-upload
    # would misclassify the record as a conflict.
    for observation in _observations(db_session):
        stored = stored_content_from_payload(observation.payload)
        assert observation.content_hash == content_fingerprint(stored)


def test_per_asset_counts_match_the_adjudicated_labels(
    db_session: Session, labels: dict
) -> None:
    counts: dict[str, int] = {}
    for observation in _observations(db_session):
        counts[observation.asset_id] = counts.get(observation.asset_id, 0) + 1
    expected = {
        str(asset["asset_id"]): int(asset["work_order_count"])
        for asset in labels["assets"]
    }
    assert counts == expected
