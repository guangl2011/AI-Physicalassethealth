"""API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
