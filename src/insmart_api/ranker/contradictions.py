"""Contradiction detection: records whose claims cannot both be true.

The engine surfaces conflicts — it never adjudicates them. When one record
asserts a component was replaced (or a replacement was scheduled) and another
asserts that same component appears original, with no record of replacement,
both claims are shown side-by-side with their sources and the diagnosis is
``contested``. The product's job is to put the conflict in front of a
technician, not to quietly pick a winner.

The rules are plain data: a component lexicon plus the two claim languages
(replacement vs. originality). A claim is one sentence of one work-order
field that names the component and uses exactly one of the two languages.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

# Component lexicon: canonical name -> patterns that name it in text.
_COMPONENT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    component: tuple(re.compile(p, re.IGNORECASE) for p in patterns)
    for component, patterns in {
        "compressor": (r"compressor",),
        "fan motor": (r"fan motor", r"condenser fan", r"blower motor"),
        "control board": (r"control board", r"defrost board"),
        "gas valve": (r"gas valve",),
        "circulator pump": (r"circulator",),
        "igniter": (r"igniter",),
        "flame sensor": (r"flame sensor",),
    }.items()
}

# Language asserting the component was (or would be) replaced. "Scheduled"
# / recommended / proposed replacements are plans, not facts — they do not
# oppose an originality claim (that distinction is what resolves the CH-1
# pair in the seed adjudication: a replacement was scheduled and never
# happened, so no conflict remains).
_REPLACEMENT = re.compile(r"\b(?:replaced|replacement|new)\b", re.IGNORECASE)
_PLAN_LANGUAGE = re.compile(
    r"\b(?:schedul\w+|recommend\w*|propos\w+|plan(?:ned)?)\b", re.IGNORECASE
)
# Language asserting the component is original / was never replaced.
_ORIGINALITY = re.compile(
    r"\b(?:original|never replaced|no record of)\b", re.IGNORECASE
)

# Sentence split: a claim lives in one sentence of one field. Splits on
# periods only — semicolons stay inside the sentence, so a claim like
# "Compressor nameplate shows 2011 manufacture date; appears original, no
# record of prior replacement" keeps its component and its claim language
# together.
_SENTENCE_SPLIT = re.compile(r"\.\s+")
QUOTE_MAX_CHARS = 200


@dataclass(frozen=True)
class ContradictionClaim:
    """One side of a contradiction, cited to its source record."""

    observation_id: str
    source_ref: str
    field: str
    quote: str
    recorded_at: str  # ISO string — the pair is stored as JSON


@dataclass(frozen=True)
class ContradictionPair:
    """Two claims about one component that cannot both be true."""

    component: str
    claim_a: ContradictionClaim
    claim_b: ContradictionClaim


@dataclass(frozen=True)
class ClaimRecord:
    """The text of one stored record, as the detector sees it."""

    observation_id: str
    source_ref: str
    recorded_at: str  # ISO string
    fields: Mapping[str, str]


def _claims(record: ClaimRecord, language: re.Pattern[str]) -> list[tuple[str, ContradictionClaim]]:
    """(component, claim) for every sentence in the record matching the language."""
    claims: list[tuple[str, ContradictionClaim]] = []
    for field_name, text in record.fields.items():
        for sentence in _SENTENCE_SPLIT.split(text):
            component = _component_of(sentence)
            if component is None or not language.search(sentence):
                continue
            if language is _REPLACEMENT and _PLAN_LANGUAGE.search(sentence):
                continue  # a scheduled replacement is a plan, not a fact
            claims.append(
                (
                    component,
                    ContradictionClaim(
                        observation_id=record.observation_id,
                        source_ref=record.source_ref,
                        field=field_name,
                        quote=sentence.strip()[:QUOTE_MAX_CHARS],
                        recorded_at=record.recorded_at,
                    ),
                )
            )
    return claims


def find_contradictions(records: list[ClaimRecord]) -> list[ContradictionPair]:
    """Pairs of records making conflicting claims about the same component.

    A pair needs the replacement language in one record and the originality
    language in a different record, over the same component. Claims inside a
    single record are not a contradiction (one record can update itself).
    """
    pairs: dict[tuple[str, str, str], ContradictionPair] = {}
    for record in records:
        for component, replacement in _claims(record, _REPLACEMENT):
            for other in records:
                if other.observation_id == record.observation_id:
                    continue
                for originality_component, originality in _claims(other, _ORIGINALITY):
                    if originality_component != component:
                        continue
                    key = (
                        component,
                        min(record.observation_id, other.observation_id),
                        max(record.observation_id, other.observation_id),
                    )
                    pairs.setdefault(
                        key,
                        ContradictionPair(
                            component=component,
                            claim_a=replacement,
                            claim_b=originality,
                        ),
                    )
    return sorted(
        pairs.values(),
        key=lambda pair: (pair.claim_a.observation_id, pair.claim_b.observation_id),
    )


def _component_of(quote: str) -> str | None:
    """The canonical component a claim quote names, if any."""
    return next(
        (
            name
            for name, patterns in _COMPONENT_PATTERNS.items()
            if any(pattern.search(quote) for pattern in patterns)
        ),
        None,
    )
