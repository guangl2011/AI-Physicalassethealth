"""The Extractor interface: raw work-order text in, structured observations out.

Every extractor — the deterministic rule-based default and any LLM-backed
adapter — returns ``ExtractedObservation`` values whose provenance always
points back into the source work order via the ``work-order:<id>`` source-ref
scheme shared with the evidence graph. Deterministic output is ``observed``
(copied from the record); LLM output is ``inferred`` and must carry evidence
ids resolving to the observed record it was derived from — the same no-
inference-without-evidence rule the ``observations`` table enforces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from insmart_api.integrity import make_source_ref

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from insmart_api.ingestion.parsing import WorkOrderRow

# The free-text columns extraction reasons over. Structured columns
# (created_at, completed_at) are carried explicitly on WorkOrderText.
TEXT_FIELDS: tuple[str, ...] = ("summary", "notes", "resolution")


class ObservationCategory(StrEnum):
    """What an extracted observation claims about the asset."""

    DEFECT = "defect"
    SYMPTOM = "symptom"
    ACTION = "action"
    DATE = "date"


class EvidenceKind(StrEnum):
    """The evidence-graph kind this extraction would become."""

    OBSERVED = "observed"
    INFERRED = "inferred"


@dataclass(frozen=True)
class WorkOrderText:
    """The text of one work order, as an extractor sees it.

    A neutral view over an ingested work-order record: the free-text columns
    plus the structured dates. Built from a parsed ingestion row (or straight
    from a stored observation's payload) so extractors never depend on where
    the record came from.
    """

    work_order_id: str
    created_at: datetime
    completed_at: datetime | None
    fields: dict[str, str] = dataclass_field(default_factory=dict)

    @classmethod
    def from_row(cls, row: WorkOrderRow) -> WorkOrderText:
        """Build from a validated ingestion-parsing row."""
        return cls(
            work_order_id=row.work_order_id,
            created_at=row.created_at,
            completed_at=row.completed_at,
            fields={name: row.fields[name] for name in TEXT_FIELDS},
        )

    def text_of(self, field: str) -> str:
        """The stripped text of one free-text column (empty if absent)."""
        return self.fields.get(field, "")


@dataclass(frozen=True)
class ExtractedObservation:
    """One structured finding, with provenance into the source work order.

    ``source_ref`` uses the shared ``work-order:<id>`` scheme so it resolves
    against the evidence graph. ``observed`` output carries no confidence or
    evidence ids; ``inferred`` output (LLM) must carry ``evidence_ids``.
    """

    category: ObservationCategory
    text: str
    work_order_id: str
    field: str  # which work-order column the finding came from
    source_ref: str
    kind: EvidenceKind = EvidenceKind.OBSERVED
    evidence_ids: tuple[str, ...] = ()
    confidence: float | None = None


def observed_observation(
    category: ObservationCategory, text: str, work_order_id: str, field: str
) -> ExtractedObservation:
    """Build an ``observed`` extraction — copied from the source record."""
    return ExtractedObservation(
        category=category,
        text=text,
        work_order_id=work_order_id,
        field=field,
        source_ref=make_source_ref(work_order_id),
        kind=EvidenceKind.OBSERVED,
    )


def inferred_observation(
    category: ObservationCategory,
    text: str,
    work_order_id: str,
    field: str,
    confidence: float | None = None,
) -> ExtractedObservation:
    """Build an ``inferred`` extraction citing the record it was derived from.

    ``confidence`` must sit in [0, 1] when given — the same range the
    ``observations`` table's check constraint enforces.
    """
    if confidence is not None and not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence {confidence} outside [0, 1]")
    return ExtractedObservation(
        category=category,
        text=text,
        work_order_id=work_order_id,
        field=field,
        source_ref=make_source_ref(work_order_id),
        kind=EvidenceKind.INFERRED,
        evidence_ids=(work_order_id,),
        confidence=confidence,
    )


class Extractor(ABC):
    """Turn raw work-order text into structured observations.

    Implementations must be deterministic per record for the same input
    (an LLM adapter pinned to a temperature of 0 satisfies this in practice;
    the deterministic extractor satisfies it exactly) and must never require
    network access — a fallback extractor must always exist.
    """

    name: str

    @abstractmethod
    def extract(self, work_order: WorkOrderText) -> list[ExtractedObservation]:
        """Extract every finding from one work order."""

    def extract_all(
        self, work_orders: Iterable[WorkOrderText]
    ) -> list[ExtractedObservation]:
        """Extract over many work orders, in input order."""
        observations: list[ExtractedObservation] = []
        for work_order in work_orders:
            observations.extend(self.extract(work_order))
        return observations


def work_order_text(
    work_order_id: str,
    fields: Mapping[str, str],
    created_at: datetime,
    completed_at: datetime | None,
) -> WorkOrderText:
    """Build a WorkOrderText from stored payload fields (used by the eval)."""
    return WorkOrderText(
        work_order_id=work_order_id,
        created_at=created_at,
        completed_at=completed_at,
        fields={name: fields.get(name, "") for name in TEXT_FIELDS},
    )
