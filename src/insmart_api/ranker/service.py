"""The DiagnosisService — rank evidence-backed causes or abstain.

The product's core commitment, enforced here and nowhere else:

- A diagnosis is **ranked** only when enough usable evidence exists and every
  shown cause cites at least one observation record. Confidence below the
  threshold is suppressed, not displayed.
- **insufficient_evidence** when fewer than three distinct defect
  observations exist for the asset, or when all of them are stale. The
  response carries a plain-language rationale and what would help — and it
  structurally cannot carry a confidence figure (the ``diagnoses`` table's
  check constraints make causes NULL for abstentions; the response schema
  has no such field).
- **contested** when the records contradict each other (e.g. one says a
  component was replaced, another says it appears original). Both claims are
  shown side-by-side with their sources; the engine surfaces conflicts, it
  never resolves them silently.

"Usable evidence" means extracted defect observations — symptoms never create
candidates (an asset whose records complain but never report findings
abstains), they only feed the physics priors.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from insmart_api.extractors import (
    DeterministicExtractor,
    Extractor,
    ObservationCategory,
    work_order_text,
)
from insmart_api.integrity import make_source_ref
from insmart_api.models import Asset, Diagnosis, Observation
from insmart_api.ranker.contradictions import (
    ClaimRecord,
    ContradictionPair,
    find_contradictions,
)
from insmart_api.ranker.scoring import ScoredCause, rank_causes
from insmart_api.ranker.signatures import build_candidates

# Sufficiency gates — a diagnosis needs enough records, enough defect
# evidence in them, and none of it stale. The records bar mirrors the seed
# labels' adjudicated threshold (``sufficiency_threshold_resolvable_orders
# = 8``: assets below it are thin-history); the defect bar is the spec's
# "fewer than 3 distinct observations abstain".
MIN_RESOLVABLE_ORDERS = 8
MIN_DEFECT_OBSERVATIONS = 3
# Staleness: usable evidence older than this window stops being diagnostic.
STALE_AFTER_DAYS = 545


@dataclass(frozen=True)
class RecordEvidence:
    """What extraction found in one stored record."""

    observation_id: str
    source_ref: str
    recorded_at: datetime
    all_fields: dict[str, str]  # field name -> full field text
    defect_fields: dict[str, str]  # the fields where defect spans matched
    defect_spans: list[str]
    symptom_spans: list[str]


def extract_record_evidence(
    records: list[Observation], extractor: Extractor
) -> list[RecordEvidence]:
    """Run extraction over stored records and keep the diagnostic signal.

    Each record's payload is rebuilt into the extractor's neutral input view
    (the same pattern the extraction eval uses), so diagnosis depends on the
    extractor contract, not on where the record came from. Only ``observed``
    rows are evidence — inferred rows are downstream products.
    """
    evidence: list[RecordEvidence] = []
    for record in records:
        if record.kind != "observed":
            continue
        payload: dict[str, Any] = json.loads(record.payload)
        completed_at = payload.get("completed_at")
        work_order = work_order_text(
            record.id,
            payload,
            datetime.fromisoformat(payload["created_at"]),
            datetime.fromisoformat(completed_at) if completed_at else None,
        )
        extracted = extractor.extract(work_order)
        defect_fields: dict[str, str] = {}
        defect_spans: list[str] = []
        symptom_spans: list[str] = []
        for finding in extracted:
            if finding.category is ObservationCategory.DEFECT:
                defect_spans.append(finding.text)
                defect_fields[finding.field] = work_order.text_of(finding.field)
            elif finding.category is ObservationCategory.SYMPTOM:
                symptom_spans.append(finding.text)
        evidence.append(
            RecordEvidence(
                observation_id=record.id,
                source_ref=make_source_ref(record.id),
                recorded_at=record.recorded_at,
                all_fields=dict(work_order.fields),
                defect_fields=defect_fields,
                defect_spans=defect_spans,
                symptom_spans=symptom_spans,
            )
        )
    return evidence


def evaluate_sufficiency(
    evidence: list[RecordEvidence], as_of: datetime
) -> tuple[bool, str, str]:
    """The sufficiency verdict: (sufficient, rationale, what would help).

    Three gates, checked in order — the rationale names the first one that
    fails: enough records exist for this asset (the labels' thin-history
    threshold), enough of them carry defect findings, and the newest of
    those is still inside the diagnostic window.
    """
    if len(evidence) < MIN_RESOLVABLE_ORDERS:
        record_word = "record" if len(evidence) == 1 else "records"
        return (
            False,
            (
                f"Thin history: only {len(evidence)} resolvable work-order "
                f"{record_word} for this asset; at least {MIN_RESOLVABLE_ORDERS} are "
                "needed to diagnose it fairly."
            ),
            "Add this asset's historical service records so its history is deep "
            "enough to compare against.",
        )
    usable = [record for record in evidence if record.defect_spans]
    defect_count = sum(len(record.defect_spans) for record in usable)
    if defect_count < MIN_DEFECT_OBSERVATIONS:
        record_word = "record" if len(usable) == 1 else "records"
        return (
            False,
            (
                f"{len(usable)} usable {record_word} for this asset "
                f"({defect_count} defect observations); at least "
                f"{MIN_DEFECT_OBSERVATIONS} defect observations are needed to rank causes."
            ),
            "Add service records that describe defect findings or repairs for this asset.",
        )
    most_recent = max(record.recorded_at for record in usable)
    stale_after = timedelta(days=STALE_AFTER_DAYS)
    if as_of - most_recent > stale_after:
        age_days = (as_of - most_recent).days
        return (
            False,
            (
                f"The most recent usable record for this asset is {age_days} days old — "
                f"beyond the {STALE_AFTER_DAYS}-day diagnostic window — so the evidence "
                "may no longer describe the asset."
            ),
            (
                "Add recent service records; records older than the diagnostic window "
                "stop being treated as evidence."
            ),
        )
    return True, "", ""


def serialize_causes(causes: list[ScoredCause]) -> str:
    """Causes to the JSON stored on a diagnosis row."""
    return json.dumps([asdict(cause) for cause in causes])


def serialize_contradictions(pairs: list[ContradictionPair]) -> str:
    """Contradiction pairs to the JSON stored on a diagnosis row."""
    return json.dumps([asdict(pair) for pair in pairs])


class DiagnosisService:
    """Compute, state-classify, and persist the diagnosis for one asset."""

    def __init__(self, session: Session, extractor: Extractor | None = None) -> None:
        self._session = session
        # The extractor is injectable so tests can pin the deterministic one.
        self._extractor = extractor or DeterministicExtractor()

    def diagnose(self, asset_id: str, as_of: datetime | None = None) -> Diagnosis:
        """Diagnose one asset as of a moment (default: now) and persist the row."""
        asset = self._session.get(Asset, asset_id)
        if asset is None:
            raise LookupError(f"asset {asset_id!r} is not registered")
        moment = as_of or datetime.now()

        records = list(
            self._session.scalars(
                select(Observation)
                .where(Observation.asset_id == asset_id)
                .order_by(Observation.recorded_at, Observation.id)
            )
        )
        evidence = extract_record_evidence(records, self._extractor)

        sufficient, rationale, what_would_help = evaluate_sufficiency(evidence, moment)
        if not sufficient:
            return self._persist(
                asset_id=asset_id,
                state="insufficient_evidence",
                rationale=rationale,
                what_would_help=what_would_help,
                as_of=moment,
                causes=None,
                contradictions=None,
            )

        contradictions = find_contradictions(
            [
                ClaimRecord(
                    observation_id=record.observation_id,
                    source_ref=record.source_ref,
                    recorded_at=record.recorded_at.isoformat(),
                    fields=record.all_fields,
                )
                for record in evidence
            ]
        )
        causes = self._rank(asset, evidence, moment)
        if contradictions:
            return self._persist(
                asset_id=asset_id,
                state="contested",
                rationale=(
                    "Records conflict on "
                    + ", ".join(sorted({pair.component for pair in contradictions}))
                    + " — both claims are shown with their sources; the conflict needs "
                    "a person, not a resolution behind their back."
                ),
                what_would_help=None,
                as_of=moment,
                causes=serialize_causes(causes),
                contradictions=serialize_contradictions(contradictions),
            )
        if causes:
            top = causes[0]
            return self._persist(
                asset_id=asset_id,
                state="ranked",
                rationale=(
                    f"{top.label} ranks first, supported by {top.observation_count} "
                    f"record(s); every ranked cause cites its records."
                ),
                what_would_help=None,
                as_of=moment,
                causes=serialize_causes(causes),
                contradictions=None,
            )
        return self._persist(
            asset_id=asset_id,
            state="insufficient_evidence",
            rationale=(
                "The records describe defects, but none of the evidence is strong "
                "enough to name a cause with the available signals."
            ),
            what_would_help=(
                "A technician inspection, or records with more specific defect findings."
            ),
            as_of=moment,
            causes=None,
            contradictions=None,
        )

    def _rank(
        self, asset: Asset, evidence: list[RecordEvidence], moment: datetime
    ) -> list[ScoredCause]:
        """Candidates from defect evidence, scored with the physics priors."""
        candidates = build_candidates(
            [
                (
                    record.observation_id,
                    record.source_ref,
                    record.defect_fields,
                    record.defect_spans,
                )
                for record in evidence
            ]
        )
        symptom_texts = {
            span.lower() for record in evidence for span in record.symptom_spans
        }
        record_dates = {record.observation_id: record.recorded_at for record in evidence}
        return rank_causes(
            candidates, asset.equipment_type, symptom_texts, record_dates, moment
        )

    def _persist(
        self,
        asset_id: str,
        state: str,
        rationale: str,
        what_would_help: str | None,
        as_of: datetime,
        causes: str | None,
        contradictions: str | None,
    ) -> Diagnosis:
        """Persist one diagnosis snapshot (commit belongs to the caller)."""
        diagnosis = Diagnosis(
            id=f"DX-{uuid4().hex[:12]}",
            asset_id=asset_id,
            state=state,
            rationale=rationale,
            what_would_help=what_would_help,
            as_of=as_of,
            causes=causes,
            contradictions=contradictions,
            created_at=datetime.now(),
        )
        self._session.add(diagnosis)
        self._session.flush()
        return diagnosis
