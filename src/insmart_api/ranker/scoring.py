"""Scoring: combine frequency, recency, and physics priors into ranked causes.

The score is a transparent weighted sum, not a model:

- **frequency** — distinct records supporting the cause, normalized by the
  strongest candidate on the asset.
- **recency** — exponential decay of the supporting records' ages
  (half-life one year): recent failures weigh more than ancient ones.
- **physics prior** — the ``priors`` module's strength for the cause on this
  equipment (fit, symptom co-occurrence, seasonality).

Causes below ``CONFIDENCE_THRESHOLD`` are suppressed: an evidence-backed
cause that scores too low is not shown at all rather than shown with a
disclaimer. Every cause that survives carries at least one observation
citation by construction — candidacy requires defect evidence.

``fleet_baseline_top_causes`` is the frequency-only baseline: rank causes by
corpus-wide frequency, ignoring evidence quality entirely. It is the naive
alternative the physics-aware ranking has to beat (the eval asserts it does).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from insmart_api.ranker.priors import PriorBreakdown, prior_for
from insmart_api.ranker.signatures import CAUSE_LABELS, CauseCandidate

CONFIDENCE_THRESHOLD = 0.3
WEIGHT_FREQUENCY = 0.5
WEIGHT_RECENCY = 0.2
WEIGHT_PRIOR = 0.3
RECENCY_HALF_LIFE_DAYS = 365.0


@dataclass(frozen=True)
class ScoredCause:
    """One ranked cause, with the citations that back it.

    ``observation_ids`` resolve to real observation rows; ``source_refs``
    locate the source records (the shared ``work-order:<id>`` scheme). A
    cause without at least one citation cannot exist here — candidacy
    requires defect evidence.
    """

    cause: str
    label: str
    confidence: float
    observation_count: int
    observation_ids: tuple[str, ...]
    source_refs: tuple[str, ...]
    evidence_spans: tuple[str, ...]
    prior_rationale: str


def recency_score(recorded_ats: list[datetime], as_of: datetime) -> float:
    """Mean exponentially-decayed weight of the supporting records' ages."""
    if not recorded_ats:
        return 0.0
    decay = math.log(2.0) / RECENCY_HALF_LIFE_DAYS
    weights = [
        math.exp(-decay * max(0.0, (as_of - recorded).total_seconds() / 86400.0))
        for recorded in recorded_ats
    ]
    return sum(weights) / len(weights)


def score_candidate(
    candidate: CauseCandidate,
    max_support: int,
    equipment_type: str,
    symptom_texts: set[str],
    recorded_ats: list[datetime],
    as_of: datetime,
) -> tuple[float, PriorBreakdown]:
    """The confidence for one candidate cause: frequency + recency + prior."""
    prior = prior_for(
        candidate.cause,
        equipment_type,
        symptom_texts,
        {recorded.month for recorded in recorded_ats},
    )
    frequency = candidate.support / max_support if max_support else 0.0
    recency = recency_score(recorded_ats, as_of)
    confidence = (
        WEIGHT_FREQUENCY * frequency
        + WEIGHT_RECENCY * recency
        + WEIGHT_PRIOR * prior.strength
    )
    return confidence, prior


def rank_causes(
    candidates: Mapping[str, CauseCandidate],
    equipment_type: str,
    symptom_texts: set[str],
    record_dates: Mapping[str, datetime],
    as_of: datetime,
) -> list[ScoredCause]:
    """Rank candidate causes above the confidence threshold, best first."""
    max_support = max((candidate.support for candidate in candidates.values()), default=0)
    scored: list[ScoredCause] = []
    for candidate in candidates.values():
        recorded_ats = [
            record_dates[record_id]
            for record_id in candidate.record_ids
            if record_id in record_dates
        ]
        confidence, prior = score_candidate(
            candidate, max_support, equipment_type, symptom_texts, recorded_ats, as_of
        )
        if confidence < CONFIDENCE_THRESHOLD:
            continue
        scored.append(
            ScoredCause(
                cause=candidate.cause,
                label=CAUSE_LABELS.get(candidate.cause, candidate.cause),
                confidence=round(confidence, 4),
                observation_count=candidate.support,
                observation_ids=tuple(sorted(candidate.record_ids)),
                source_refs=tuple(sorted({span[1] for span in candidate.spans})),
                evidence_spans=tuple(sorted({span[2] for span in candidate.spans})),
                prior_rationale=prior.rationale,
            )
        )
    # Deterministic order: confidence, then support, then cause id.
    return sorted(scored, key=lambda s: (-s.confidence, -s.observation_count, s.cause))


def fleet_baseline_top_causes(cause_support: Mapping[str, int], k: int = 3) -> tuple[str, ...]:
    """Corpus-wide most common causes, ties alphabetical — the frequency-only baseline."""
    ranked = sorted(cause_support, key=lambda cause: (-cause_support[cause], cause))
    return tuple(ranked[:k])
