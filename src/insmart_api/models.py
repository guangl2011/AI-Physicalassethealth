"""SQLAlchemy ORM models — the evidence graph.

One table per concept, provenance attached to every row (spec art_N0ARICWR).
``observations`` distinguishes ``observed`` rows (copied from a source record;
the ingestion pipeline's output) from ``inferred`` rows (derived by later
diagnosis tasks), which must carry evidence ids resolving to real observed
rows — no inference exists without evidence.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all Insmart ORM models."""


class Asset(Base):
    """Canonical (normalized) equipment identity — the entity-resolution target."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(200), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    installed_year: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Observation(Base):
    """One evidence node: a claim about an asset, observed or inferred.

    ``observed`` rows carry a non-empty ``source_ref`` pointing back at the
    source record they were copied from. ``inferred`` rows must carry
    ``evidence_ids`` — a JSON array of observation ids, each resolving to an
    ``observed`` row. ``content_hash`` fingerprints the source content so
    duplicate ingestion collapses deterministically; ``payload`` keeps the
    extract-prepared fields (including the source-file locator) for the
    downstream extraction task.
    """

    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint("kind IN ('observed', 'inferred')", name="ck_observation_kind"),
        CheckConstraint("source_ref != ''", name="ck_observation_source_ref"),
        CheckConstraint(
            "kind != 'observed' OR evidence_ids IS NULL",
            name="ck_observed_without_evidence_ids",
        ),
        CheckConstraint(
            "kind != 'observed' OR confidence IS NULL",
            name="ck_observed_without_confidence",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_confidence_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.id"), nullable=False, index=True
    )
    source_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="observed")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class IngestRun(Base):
    """Accounting record for one bulk-ingestion run.

    Every input row lands in exactly one of three buckets — ingested,
    deduplicated, or review — so the counts must always sum to ``rows_total``.
    This is how "zero silent drops" stays a queryable fact instead of a claim.
    """

    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(300), nullable=False)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_ingested: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_deduplicated: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_reviewed: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewItem(Base):
    """A row that did not become an observation, with the human-readable why.

    Unparseable rows, unresolvable or ambiguous asset tags, and conflicting
    duplicates all land here. Nothing is ever dropped without a reason a
    person can read and act on.
    """

    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("ingest_runs.id"), nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(String(300), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    raw_row: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of raw cells
