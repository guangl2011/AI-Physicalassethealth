"""HTTP surface for ingestion and evidence-graph reads.

Read endpoints are append-only views over the evidence graph: the timeline
shows every observation with its own citation, and conflicting claims stay
side-by-side — nothing is ever merged or silently resolved.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from insmart_api.ingestion.parsing import HeaderError
from insmart_api.ingestion.pipeline import (
    AssetRegistrationError,
    IngestionError,
    ingest_work_orders,
    register_assets,
)
from insmart_api.models import Asset, Diagnosis, Feedback, Observation, ReviewItem
from insmart_api.ranker.service import DiagnosisService
from insmart_api.schemas import (
    AssetIn,
    AssetOut,
    AssetRegistrationOut,
    ContestedDiagnosisOut,
    ContradictionPairOut,
    DiagnosisOut,
    FeedbackIn,
    FeedbackOut,
    IngestReportOut,
    InsufficientDiagnosisOut,
    RankedCauseOut,
    RankedDiagnosisOut,
    ReviewItemOut,
    ReviewListOut,
    TimelineEntryOut,
    TimelineOut,
)

router = APIRouter()


def get_db(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session from the app's session factory."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.post("/ingest/assets")
def ingest_assets(
    entries: list[AssetIn], session: Annotated[Session, Depends(get_db)]
) -> AssetRegistrationOut:
    """Register the asset inventory that entity resolution resolves against."""
    try:
        registered = register_assets(session, [entry.model_dump() for entry in entries])
    except AssetRegistrationError as error:
        session.rollback()
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    session.commit()
    return AssetRegistrationOut(registered=len(registered), asset_ids=registered)


@router.post("/ingest/work-orders")
async def upload_work_orders(
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db)],
) -> IngestReportOut:
    """Bulk-upload a CSV work-order export; every row is accounted for."""
    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=422, detail="uploaded file is not valid UTF-8 text"
        ) from error
    source_name = Path(file.filename or "upload.csv").name
    try:
        report = ingest_work_orders(session, source_name=source_name, csv_text=csv_text)
    except (HeaderError, IngestionError) as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return IngestReportOut(
        run_id=report.run_id,
        source_name=report.source_name,
        rows_total=report.rows_total,
        rows_ingested=report.rows_ingested,
        rows_deduplicated=report.rows_deduplicated,
        rows_reviewed=report.rows_reviewed,
        review=[
            ReviewItemOut(
                run_id=report.run_id,
                source_name=report.source_name,
                row_number=entry.row_number,
                external_id=entry.external_id,
                reason=entry.reason,
                raw_row=entry.raw_row,
            )
            for entry in report.review
        ],
    )


@router.get("/assets")
def list_assets(session: Annotated[Session, Depends(get_db)]) -> list[AssetOut]:
    """List registered assets with their observation counts."""
    rows = session.execute(
        select(Asset, func.count(Observation.id))
        .outerjoin(Observation, Observation.asset_id == Asset.id)
        .group_by(Asset.id)
        .order_by(Asset.id)
    ).all()
    return [
        AssetOut(
            asset_id=asset.id,
            site_id=asset.site_id,
            equipment_type=asset.equipment_type,
            installed_year=asset.installed_year,
            observation_count=count,
        )
        for asset, count in rows
    ]


def _timeline_entry(observation: Observation) -> TimelineEntryOut:
    payload: dict[str, Any] = json.loads(observation.payload)
    evidence_ids: list[str] | None = (
        json.loads(observation.evidence_ids) if observation.evidence_ids else None
    )
    return TimelineEntryOut(
        observation_id=observation.id,
        kind=observation.kind,
        recorded_at=observation.recorded_at,
        text=observation.text,
        source_ref=observation.source_ref,
        source_file=payload.get("source_file"),
        source_row=payload.get("source_row"),
        completed_at=payload.get("completed_at"),
        evidence_ids=evidence_ids,
        confidence=observation.confidence,
        payload=payload,
    )


@router.get("/assets/{asset_id}/timeline")
def asset_timeline(
    asset_id: str, session: Annotated[Session, Depends(get_db)]
) -> TimelineOut:
    """Chronological observations for one asset, each citing its source record."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=404, detail=f"asset {asset_id!r} is not registered"
        )
    observations = session.scalars(
        select(Observation)
        .where(Observation.asset_id == asset_id)
        .order_by(Observation.recorded_at, Observation.id)
    ).all()
    return TimelineOut(
        asset_id=asset.id,
        site_id=asset.site_id,
        equipment_type=asset.equipment_type,
        entries=[_timeline_entry(observation) for observation in observations],
    )


@router.get("/review")
def review_list(session: Annotated[Session, Depends(get_db)]) -> ReviewListOut:
    """Rows that did not become observations, each with a human-readable reason."""
    items = session.scalars(
        select(ReviewItem).order_by(ReviewItem.run_id, ReviewItem.row_number)
    ).all()
    return ReviewListOut(
        total=len(items),
        items=[
            ReviewItemOut(
                run_id=item.run_id,
                source_name=item.source_name,
                row_number=item.row_number,
                external_id=item.external_id,
                reason=item.reason,
                raw_row=json.loads(item.raw_row),
            )
            for item in items
        ],
    )


# --- diagnosis ------------------------------------------------------------------


def _diagnosis_out(diagnosis: Diagnosis) -> DiagnosisOut:
    """Map a stored diagnosis row to its state's response schema."""
    if diagnosis.state == "insufficient_evidence":
        # An abstention carries no causes — the schema forbids it.
        return InsufficientDiagnosisOut(
            state="insufficient_evidence",
            diagnosis_id=diagnosis.id,
            asset_id=diagnosis.asset_id,
            as_of=diagnosis.as_of,
            rationale=diagnosis.rationale,
            what_would_help=diagnosis.what_would_help or "",
        )
    causes = [
        RankedCauseOut.model_validate(cause)
        for cause in json.loads(diagnosis.causes or "[]")
    ]
    if diagnosis.state == "contested":
        return ContestedDiagnosisOut(
            state="contested",
            diagnosis_id=diagnosis.id,
            asset_id=diagnosis.asset_id,
            as_of=diagnosis.as_of,
            rationale=diagnosis.rationale,
            contradictions=[
                ContradictionPairOut.model_validate(pair)
                for pair in json.loads(diagnosis.contradictions or "[]")
            ],
            causes=causes,
        )
    return RankedDiagnosisOut(
        state="ranked",
        diagnosis_id=diagnosis.id,
        asset_id=diagnosis.asset_id,
        as_of=diagnosis.as_of,
        rationale=diagnosis.rationale,
        causes=causes,
    )


@router.get("/assets/{asset_id}/diagnosis")
def asset_diagnosis(
    asset_id: str,
    session: Annotated[Session, Depends(get_db)],
    as_of: datetime | None = None,
) -> DiagnosisOut:
    """Diagnose an asset as of a moment (default: now); each call snapshots a row.

    The optional ``as_of`` query parameter pins the diagnostic moment — how
    the evaluation runs the same engine over historical evidence.
    """
    service = DiagnosisService(session)
    try:
        diagnosis = service.diagnose(asset_id, as_of=as_of)
    except LookupError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    session.commit()
    return _diagnosis_out(diagnosis)


@router.post("/diagnoses/{diagnosis_id}/feedback")
def diagnose_feedback(
    diagnosis_id: str,
    feedback: FeedbackIn,
    session: Annotated[Session, Depends(get_db)],
) -> FeedbackOut:
    """Record a technician's verdict on a diagnosis (confirm / correct / reject)."""
    diagnosis = session.get(Diagnosis, diagnosis_id)
    if diagnosis is None:
        raise HTTPException(
            status_code=404, detail=f"diagnosis {diagnosis_id!r} does not exist"
        )
    if feedback.verdict == "correct" and not feedback.corrected_cause:
        raise HTTPException(
            status_code=422,
            detail="a 'correct' verdict needs corrected_cause — the cause it should have been",
        )
    row = Feedback(
        diagnosis_id=diagnosis_id,
        verdict=feedback.verdict,
        corrected_cause=feedback.corrected_cause,
        note=feedback.note,
        created_at=datetime.now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return FeedbackOut(
        id=row.id,
        diagnosis_id=row.diagnosis_id,
        verdict=row.verdict,
        corrected_cause=row.corrected_cause,
        note=row.note,
        created_at=row.created_at,
    )
