"""Executable graph-integrity contract for the evidence graph.

The invariant the product stands on: provenance never dangles. Every
observation cites a source record, and every inference cites evidence that
resolves to real observed rows. ``graph_integrity_violations`` turns that
invariant into data tests (and later, monitoring) can assert on.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from insmart_api.models import Observation

SOURCE_REF_SCHEME = "work-order"


def make_source_ref(work_order_id: str) -> str:
    """Build the provenance locator for an observed work-order row."""
    return f"{SOURCE_REF_SCHEME}:{work_order_id}"


def parse_source_ref(source_ref: str) -> tuple[str, str] | None:
    """Split ``work-order:WO-0041`` into (scheme, record id); None if malformed."""
    scheme, separator, record_id = source_ref.partition(":")
    if not separator or not scheme or not record_id:
        return None
    return scheme, record_id


def graph_integrity_violations(session: Session) -> list[str]:
    """List every violation of the evidence-graph invariants, empty if sound.

    Checks, per observation row: non-empty parseable ``source_ref``, non-empty
    ``text`` and ``asset_id``, and — the core contract — that ``inferred`` rows
    carry a non-empty ``evidence_ids`` list in which every id resolves to an
    existing ``observed`` observation. No inference exists without evidence.
    """
    violations: list[str] = []
    observations = list(session.scalars(select(Observation)))
    by_id = {obs.id: obs for obs in observations}
    for obs in observations:
        label = f"observation {obs.id}"
        if not obs.source_ref:
            violations.append(f"{label}: empty source_ref")
        elif parse_source_ref(obs.source_ref) is None:
            violations.append(f"{label}: unparseable source_ref {obs.source_ref!r}")
        if not obs.text:
            violations.append(f"{label}: empty text")
        if not obs.asset_id:
            violations.append(f"{label}: no asset")
        if obs.kind == "observed":
            continue
        if obs.evidence_ids is None:
            violations.append(f"{label}: inferred without evidence_ids")
            continue
        evidence: Any = json.loads(obs.evidence_ids)
        if not isinstance(evidence, list) or not evidence:
            violations.append(f"{label}: inferred with an empty evidence list")
            continue
        for evidence_id in evidence:
            evidence_row = by_id.get(str(evidence_id))
            if evidence_row is None:
                violations.append(f"{label}: evidence {evidence_id} does not resolve")
            elif evidence_row.kind != "observed":
                violations.append(
                    f"{label}: evidence {evidence_id} is not an observed row"
                )
    return violations
