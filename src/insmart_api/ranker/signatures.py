"""Cause signatures: which failure causes a record's defect evidence can support.

The attribution table is the link between extracted defect spans and the
candidate-cause universe. Candidacy is evidence-gated: a record contributes
support to a cause only when the extractor found a defect span in one of its
fields AND that field's text names the cause's subsystem. Symptoms never
create candidates — they only feed the physics priors — so an asset whose
records describe complaints but no defect findings has no candidates at all.

The table is deliberately plain data: inspect it, test it, extend it. Cause
ids mirror the adjudicated label vocabulary (seed/labels.json).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# The candidate-cause universe. Keys are the adjudicated label cause ids.
CAUSE_LABELS: dict[str, str] = {
    "refrigerant_leak": "Refrigerant leak",
    "compressor_failure": "Compressor failure",
    "compressor_surging": "Compressor surging",
    "condenser_fan_motor_failure": "Condenser fan motor failure",
    "control_board_failure": "Control board failure",
    "circulator_pump_failure": "Circulator pump failure",
    "ignition_failure": "Ignition failure",
}

# Field-text language that attributes a defect-bearing record to a cause.
# Matched against the lowercased full text of fields where a defect span was
# found — context ("corroded terminals") disambiguates bare defect spans
# ("corroded") that alone could not name a subsystem.
_ATTRIBUTION_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    cause: tuple(re.compile(p, re.IGNORECASE) for p in patterns)
    for cause, patterns in {
        "refrigerant_leak": (
            r"\bleak(?:s|ing|ed)?\b",
            r"charge low",
            r"low suction",
            r"bubble test",
            r"electronic detector",
            r"oil at (?:the )?service valve",
            r"undercharg",
        ),
        "compressor_failure": (
            r"compressor winding resistance",
            r"locked-rotor",
            r"valves weak",
            r"failed compressor",
            r"worn compressor",
            r"compressor short cycling",
            r"compressor drawing locked-rotor",
        ),
        "compressor_surging": (
            r"\bsurging\b",
            r"surge margin",
            r"surge counter",
            r"surge alarm",
            r"surge caused",
        ),
        "condenser_fan_motor_failure": (
            r"fan motor",
            r"fan blade",
            r"condenser fan",
            r"motor mounts",
            r"scraping from condenser",
            r"motor seized",
            r"shaft will not turn",
        ),
        "control_board_failure": (
            r"control board",
            r"defrost board",
            r"board leds",
            r"fault code",
            r"traces discolored",
            r"corroded terminals",
            r"terminals corroded",
            r"resets itself",
            r"power cycle",
        ),
        "circulator_pump_failure": (
            r"circulator",
            r"not proving flow",
            r"impeller jammed",
            r"coupling worn",
            r"pump amps",
            r"end switch",
            r"pump impeller",
            r"pump seal",
        ),
        "ignition_failure": (
            r"ignit(?:er|ion)",
            r"flame sensor",
            r"flame signal",
            r"gas valve",
            r"gas pressure",
            r"\blocks? out\b",
            r"lockouts",
        ),
    }.items()
}


def attribute_causes(field_texts: dict[str, str]) -> set[str]:
    """Causes supported by one record, given the text of its defect-bearing fields.

    ``field_texts`` maps field name (``notes``, ``resolution``, ``summary``)
    to that field's full text. A cause is attributed when any of its patterns
    matches any field's text.
    """
    causes: set[str] = set()
    for text in field_texts.values():
        lowered = text.lower()
        for cause, patterns in _ATTRIBUTION_PATTERNS.items():
            if cause in causes:
                continue
            if any(pattern.search(lowered) for pattern in patterns):
                causes.add(cause)
    return causes


@dataclass
class CauseCandidate:
    """Accumulating evidence pool for one candidate cause on one asset.

    ``record_ids`` are the work-order observation rows backing the cause
    (observation ids equal work-order ids on observed rows); ``spans`` are the
    matched defect spans with their locations — the citation material the
    ranked response renders.
    """

    cause: str
    record_ids: set[str] = field(default_factory=set)
    # (record_id, source_ref, span) — the citation material the ranked
    # response renders.
    spans: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def support(self) -> int:
        """Distinct records supporting the cause — the frequency signal."""
        return len(self.record_ids)


def build_candidates(
    extracted: list[tuple[str, str, dict[str, str], list[str]]],
) -> dict[str, CauseCandidate]:
    """Pool defect evidence into per-cause candidates.

    ``extracted`` is one entry per record: ``(record_id, source_ref,
    defect_field_texts, defect_spans)``. A record with no defect spans is
    skipped — no defect evidence, no candidacy.
    """
    candidates: dict[str, CauseCandidate] = {}
    for record_id, source_ref, field_texts, defect_spans in extracted:
        if not defect_spans:
            continue
        for cause in attribute_causes(field_texts):
            candidate = candidates.setdefault(
                cause, CauseCandidate(cause=cause)
            )
            candidate.record_ids.add(record_id)
            for span in defect_spans:
                candidate.spans.append((record_id, source_ref, span))
    return candidates
