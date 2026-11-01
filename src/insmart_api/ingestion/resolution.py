"""Entity resolution: raw technician asset tags → canonical assets.

Tag normalization is conservative by design: a tag either matches exactly
one asset, or it is flagged for human review. Ambiguous tags (``Unit 3`` —
could be ``AHU-3`` or ``RTU-3``) are never guessed, and tags matching no
asset are never dropped silently.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Equipment-type vocabulary: canonical equipment_type → the tag words
# technicians use for it (each may be multi-word; normalized before matching).
# Tags carrying one of these words resolve by word + unit number; tags without
# one fall back to the generic "unit N" path.
EQUIPMENT_TAG_WORDS: dict[str, tuple[str, ...]] = {
    "air_handling_unit": ("ahu", "air handler"),
    "rooftop_unit": ("rtu", "rooftop unit"),
    "chiller": ("chiller", "ch"),
    "cooling_tower": ("cooling tower", "ct"),
    "boiler": ("boiler", "blr"),
    "exhaust_fan": ("exhaust fan", "ef"),
    "make_up_air_unit": ("make up air", "makeup air", "mau"),
}

WORD_NUMBERS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}

_CANONICAL_ID = re.compile(r"^([a-z]+)(\d+)$")


def normalize_tag(raw: str) -> str:
    """Lowercase and collapse every non-alphanumeric run to a single space."""
    return re.sub(r"[^a-z0-9]+", " ", raw.strip().lower()).strip()


def squash(normalized: str) -> str:
    """Remove spaces from a normalized tag ('ahu 1' → 'ahu1')."""
    return normalized.replace(" ", "")


@dataclass(frozen=True)
class AssetDescriptor:
    """What the resolution index needs to know about one asset."""

    asset_id: str
    equipment_type: str


@dataclass(frozen=True)
class Resolved:
    """The tag matches exactly one asset."""

    asset_id: str


@dataclass(frozen=True)
class Ambiguous:
    """The tag matches several assets — routed to review, never guessed."""

    reason: str


@dataclass(frozen=True)
class Unresolvable:
    """The tag matches no asset in the inventory."""

    reason: str


Resolution = Resolved | Ambiguous | Unresolvable


@dataclass(frozen=True)
class AssetIndex:
    """Alias → asset and unit-number → asset maps over the asset inventory.

    ``by_alias`` maps every squashed alias (canonical id and equipment-word
    forms, e.g. ``ahu1``, ``airhandler3``) to the assets claiming it; a set
    with more than one member means the alias itself is ambiguous.
    ``by_number`` maps a unit number to every asset carrying it, for tags
    that name no equipment type ('unit 3', 'bldg 2 unit 3').
    """

    by_alias: dict[str, set[str]]
    by_number: dict[str, set[str]]

    @classmethod
    def build(cls, assets: Iterable[AssetDescriptor]) -> AssetIndex:
        by_alias: dict[str, set[str]] = {}
        by_number: dict[str, set[str]] = {}
        for descriptor in assets:
            normalized_id = squash(normalize_tag(descriptor.asset_id))
            by_alias.setdefault(normalized_id, set()).add(descriptor.asset_id)
            match = _CANONICAL_ID.match(normalized_id)
            if match is not None:
                number = match.group(2)
                by_number.setdefault(number, set()).add(descriptor.asset_id)
                for word in EQUIPMENT_TAG_WORDS.get(descriptor.equipment_type, ()):
                    word_key = squash(normalize_tag(word))
                    by_alias.setdefault(f"{word_key}{number}", set()).add(
                        descriptor.asset_id
                    )
        return cls(by_alias=by_alias, by_number=by_number)

    def resolve(self, raw_tag: str) -> Resolution:
        """Resolve one raw asset tag, or explain why that is not possible."""
        normalized = normalize_tag(raw_tag)
        if not normalized:
            return Unresolvable(reason=f"asset tag is empty: {raw_tag!r}")

        aliases = self.by_alias.get(squash(normalized), set())
        if len(aliases) == 1:
            return Resolved(asset_id=next(iter(aliases)))
        if len(aliases) > 1:
            return Ambiguous(
                reason=(
                    f"asset tag {raw_tag!r} is ambiguous — matches "
                    f"{', '.join(sorted(aliases))}; routed for human review, not guessed"
                )
            )

        number = self._unit_number(normalized.split())
        if number is None:
            return Unresolvable(
                reason=(
                    f"asset tag {raw_tag!r} does not match any asset or unit number"
                )
            )
        candidates = self.by_number.get(number, set())
        if len(candidates) == 1:
            return Resolved(asset_id=next(iter(candidates)))
        if len(candidates) > 1:
            return Ambiguous(
                reason=(
                    f"asset tag {raw_tag!r} is ambiguous — matches "
                    f"{', '.join(sorted(candidates))}; routed for human review, not guessed"
                )
            )
        return Unresolvable(
            reason=(
                f"asset tag {raw_tag!r} matches no asset in the inventory "
                f"(unit number {number})"
            )
        )

    @staticmethod
    def _unit_number(tokens: list[str]) -> str | None:
        """Find the unit number: the token after 'unit', else a trailing number."""
        if "unit" in tokens:
            position = tokens.index("unit")
            if position + 1 < len(tokens):
                number = _number_token(tokens[position + 1])
                if number is not None:
                    return number
        if tokens:
            return _number_token(tokens[-1])
        return None


def _number_token(token: str) -> str | None:
    """Normalize a digit ('3') or word ('three') number to its canonical form."""
    if token.isdigit():
        return str(int(token))
    return WORD_NUMBERS.get(token)


def resolve_asset_tag(raw_tag: str, index: AssetIndex) -> Resolution:
    """Module-level entry point so callers need not touch index internals."""
    return index.resolve(raw_tag)
