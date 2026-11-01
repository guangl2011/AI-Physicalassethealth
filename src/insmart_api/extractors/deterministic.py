"""The deterministic rule-based extractor — the default, no network, no model.

Regular-expression pattern tables over the work-order free text, tuned
against the adjudicated seed corpus: defect patterns name failure causes
and repair evidence; symptom patterns name observable indications a
technician or tenant reports; action patterns name work performed. The
patterns deliberately distinguish the two: "tenant reports unit noisy"
is a symptom; "compressor winding resistance out of range" is a defect.
Dates come from the structured columns, so they are exact by construction.
"""

from __future__ import annotations

import re

from insmart_api.extractors.base import (
    TEXT_FIELDS,
    ExtractedObservation,
    Extractor,
    ObservationCategory,
    WorkOrderText,
    observed_observation,
)

# Failure-cause / repair-evidence language. A work order whose notes or
# resolution match any of these carries an adjudicated-style defect.
_DEFECT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bleak",
        r"\bsurging\b",
        r"surge margin below minimum",
        r"not proving flow",
        r"impeller jammed",
        r"coupling worn",
        r"\blocks? out\b",
        r"igniter cracked",
        r"flame sensor fouled",
        r"flame signal weak",
        r"ignition sequence fails",
        r"\bscraping\b",
        r"fan blade loose",
        r"\bcorroded\b",
        r"\bseized\b",
        r"locked-rotor",
        r"winding resistance out of range",
        r"hard starting",
        r"short cycling",
        r"valves weak",
        r"\bshuts down\b",
        r"fault code",
        r"traces discolored",
        r"not cooling",
        r"low suction",
    )
)

# Observable indications — reported by tenants, alarms, or technician senses.
_SYMPTOM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"tenant reports?",
        r"customer complaints?",
        r"\bnoisy\b",
        r"\bno heat\b",
        r"musty smell",
        r"slab loop cold",
        r"not turning",
        r"alarm notification",
        r"high head pressure",
        r"unit steaming",
        r"\bshuts? down\b",
        r"\blockouts?\b",
        r"hard starting",
        r"short cycling",
        r"\bsurging\b",
        r"not cooling",
        r"not proving flow",
    )
)

# Work performed — maintenance and repair verbs.
_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\breplaced?\b",
        r"\brepair(?:ed|ing)?\b",
        r"\binstalled?\b",
        r"\btightened\b",
        r"\bcalibrated\b",
        r"\bcleaned\b",
        r"\binspected\b",
        r"\bserviced\b",
        r"\bverified\b",
        r"\badjusted\b",
        r"\brecorded\b",
        r"\brecharged\b",
        r"\bpurged\b",
        r"\bpressure tested\b",
        r"\bpulled vacuum\b",
        r"\bbalanced\b",
        r"\bcompleted\b",
        r"\bchecked\b",
        r"\bmonitored\b",
        r"\blogged\b",
        r"\blocated\b",
        r"\bscheduled\b",
    )
)


def _match_unique(
    patterns: tuple[re.Pattern[str], ...], text: str
) -> list[str]:
    """Matched spans of one field, deduplicated case-insensitively, in order."""
    seen: set[str] = set()
    matches: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            span = match.group(0)
            key = span.lower()
            if key not in seen:
                seen.add(key)
                matches.append(span)
    return matches


class DeterministicExtractor(Extractor):
    """Rule-based extractor: regex pattern tables over the free-text fields."""

    name = "deterministic"

    def extract(self, work_order: WorkOrderText) -> list[ExtractedObservation]:
        observations: list[ExtractedObservation] = []
        for field_name in TEXT_FIELDS:
            text = work_order.text_of(field_name)
            if not text:
                continue
            for span in _match_unique(_DEFECT_PATTERNS, text):
                observations.append(
                    observed_observation(
                        ObservationCategory.DEFECT,
                        span,
                        work_order.work_order_id,
                        field_name,
                    )
                )
            for span in _match_unique(_SYMPTOM_PATTERNS, text):
                observations.append(
                    observed_observation(
                        ObservationCategory.SYMPTOM,
                        span,
                        work_order.work_order_id,
                        field_name,
                    )
                )
            for span in _match_unique(_ACTION_PATTERNS, text):
                observations.append(
                    observed_observation(
                        ObservationCategory.ACTION,
                        span,
                        work_order.work_order_id,
                        field_name,
                    )
                )
        observations.extend(self._extract_dates(work_order))
        return observations

    @staticmethod
    def _extract_dates(work_order: WorkOrderText) -> list[ExtractedObservation]:
        """Emit the structured dates — exact by construction, never guessed."""
        observations = [
            observed_observation(
                ObservationCategory.DATE,
                work_order.created_at.isoformat(),
                work_order.work_order_id,
                "created_at",
            )
        ]
        if work_order.completed_at is not None:
            observations.append(
                observed_observation(
                    ObservationCategory.DATE,
                    work_order.completed_at.isoformat(),
                    work_order.work_order_id,
                    "completed_at",
                )
            )
        return observations
