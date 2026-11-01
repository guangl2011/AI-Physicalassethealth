"""Pure evaluation metrics — no I/O, no product imports.

Each function is a named, testable transformation from sets or rankings to
the spec's metrics (spec art_N0ARICWR, D3).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PrecisionRecall:
    """Precision/recall over id sets, with the counts behind them."""

    true_positives: int
    predicted_total: int
    actual_total: int

    @property
    def precision(self) -> float:
        return self.true_positives / self.predicted_total if self.predicted_total else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.actual_total if self.actual_total else 0.0


def precision_recall(predicted: Collection[str], actual: Collection[str]) -> PrecisionRecall:
    """Precision/recall of a predicted id set against a ground-truth id set."""
    predicted_set, actual_set = set(predicted), set(actual)
    return PrecisionRecall(
        true_positives=len(predicted_set & actual_set),
        predicted_total=len(predicted_set),
        actual_total=len(actual_set),
    )


def primary_hit_at_k(ranked: Sequence[str], relevant: Sequence[str], k: int = 3) -> bool:
    """True when the primary (first-adjudicated) relevant id is in the top ``k``.

    The spec's hit@k: the asset's primary known failure cause ranks inside
    the top k. An asset with no adjudicated causes cannot hit (it is an
    abstention case, measured by ``abstention_correctness`` instead).
    """
    return bool(relevant) and relevant[0] in ranked[:k]


StateExpectation = Literal["insufficient_evidence", "contested"]
AbstentionOutcome = tuple[str, StateExpectation, str]  # (asset_id, expected, actual)


@dataclass(frozen=True)
class AbstentionReport:
    """Per-asset state mismatches from the abstention/contested expectations."""

    checked: int
    mismatches: tuple[AbstentionOutcome, ...]

    @property
    def correct(self) -> bool:
        return not self.mismatches


def abstention_correctness(
    actual_states: Mapping[str, str], expected_states: Mapping[str, StateExpectation]
) -> AbstentionReport:
    """Compare predicted diagnosis states against the adjudicated expectations."""
    mismatches = [
        (asset_id, expected, actual_states[asset_id])
        for asset_id, expected in sorted(expected_states.items())
        if actual_states[asset_id] != expected
    ]
    return AbstentionReport(checked=len(expected_states), mismatches=tuple(mismatches))
