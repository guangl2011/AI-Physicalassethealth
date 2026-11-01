"""API request/response schemas.

The diagnosis response is a discriminated union on ``state``. The
``insufficient_evidence`` variant has no field that could hold a confidence
figure — the abstention contract ("never render a confidence number for an
abstention") is a property of the type, not a rendering convention.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AssetIn(BaseModel):
    """One asset-inventory registration row.

    Accepts canonical field names and the ``site`` spelling used by the
    adjudicated labels file.
    """

    model_config = ConfigDict(populate_by_name=True)

    asset_id: str = Field(validation_alias=AliasChoices("asset_id", "id"))
    site_id: str = Field(validation_alias=AliasChoices("site_id", "site"))
    equipment_type: str
    installed_year: int | None = None


class AssetOut(BaseModel):
    asset_id: str
    site_id: str
    equipment_type: str
    installed_year: int | None
    observation_count: int


class ReviewItemOut(BaseModel):
    run_id: int
    source_name: str
    row_number: int
    external_id: str | None
    reason: str
    raw_row: list[str]


class ReviewListOut(BaseModel):
    total: int
    items: list[ReviewItemOut]


class IngestReportOut(BaseModel):
    run_id: int
    source_name: str
    rows_total: int
    rows_ingested: int
    rows_deduplicated: int
    rows_reviewed: int
    review: list[ReviewItemOut]


class AssetRegistrationOut(BaseModel):
    registered: int
    asset_ids: list[str]


class TimelineEntryOut(BaseModel):
    observation_id: str
    kind: str
    recorded_at: datetime
    text: str
    source_ref: str
    source_file: str | None
    source_row: int | None
    completed_at: datetime | None
    evidence_ids: list[str] | None
    confidence: float | None
    payload: dict[str, Any]


class TimelineOut(BaseModel):
    asset_id: str
    site_id: str
    equipment_type: str
    entries: list[TimelineEntryOut]


# --- diagnosis -----------------------------------------------------------------


class RankedCauseOut(BaseModel):
    """One ranked cause, with the observations that back it."""

    cause: str
    label: str
    confidence: float
    observation_count: int
    observation_ids: list[str]
    source_refs: list[str]
    evidence_spans: list[str]
    prior_rationale: str


class ContradictionClaimOut(BaseModel):
    """One side of a conflict, cited to its source record."""

    observation_id: str
    source_ref: str
    field: str
    quote: str
    recorded_at: datetime


class ContradictionPairOut(BaseModel):
    """Two claims that cannot both be true, shown side-by-side."""

    component: str
    claim_a: ContradictionClaimOut
    claim_b: ContradictionClaimOut


class DiagnosisBaseOut(BaseModel):
    diagnosis_id: str
    asset_id: str
    as_of: datetime
    rationale: str


class RankedDiagnosisOut(DiagnosisBaseOut):
    """A ranked diagnosis: every cause carries its citations."""

    state: Literal["ranked"]
    causes: list[RankedCauseOut]


class InsufficientDiagnosisOut(DiagnosisBaseOut):
    """An abstention: rationale and what would help — and nothing else.

    Deliberately no ``causes`` and no ``confidence`` anywhere: the schema is
    the rendering contract.
    """

    state: Literal["insufficient_evidence"]
    what_would_help: str


class ContestedDiagnosisOut(DiagnosisBaseOut):
    """A contested diagnosis: conflicts side-by-side, ranking still cited."""

    state: Literal["contested"]
    contradictions: list[ContradictionPairOut]
    causes: list[RankedCauseOut]


DiagnosisOut = Annotated[
    RankedDiagnosisOut | InsufficientDiagnosisOut | ContestedDiagnosisOut,
    Field(discriminator="state"),
]


class FeedbackIn(BaseModel):
    """A technician's verdict on a diagnosis."""

    verdict: Literal["confirm", "correct", "reject"]
    corrected_cause: str | None = None
    note: str | None = None


class FeedbackOut(BaseModel):
    id: int
    diagnosis_id: str
    verdict: str
    corrected_cause: str | None
    note: str | None
    created_at: datetime
