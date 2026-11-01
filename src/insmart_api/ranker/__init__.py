"""Diagnosis: rank evidence-backed causes or abstain — never diagnose without citations."""

from insmart_api.ranker.contradictions import (
    ContradictionClaim,
    ContradictionPair,
    find_contradictions,
)
from insmart_api.ranker.priors import PriorBreakdown, prior_for
from insmart_api.ranker.scoring import (
    CONFIDENCE_THRESHOLD,
    ScoredCause,
    fleet_baseline_top_causes,
    rank_causes,
)
from insmart_api.ranker.service import DiagnosisService
from insmart_api.ranker.signatures import (
    CAUSE_LABELS,
    CauseCandidate,
    attribute_causes,
    build_candidates,
)

__all__ = [
    "CAUSE_LABELS",
    "CONFIDENCE_THRESHOLD",
    "CauseCandidate",
    "ContradictionClaim",
    "ContradictionPair",
    "DiagnosisService",
    "PriorBreakdown",
    "ScoredCause",
    "attribute_causes",
    "build_candidates",
    "find_contradictions",
    "fleet_baseline_top_causes",
    "prior_for",
    "rank_causes",
]
