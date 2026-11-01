"""Physics priors — the explicit, inspectable physical-knowledge module.

Encodes what is physically knowable about failure causes independent of any
one asset's records:

- **Equipment fit** — which subsystems a piece of equipment even has. A
  boiler has no refrigerant circuit, so a "leak" on a boiler cannot be a
  refrigerant leak; a chiller does not ignite anything.
- **Symptom co-occurrence** — the symptoms a cause physically produces.
  Compressor failures depress suction pressure; a slipping condenser fan
  drives head pressure up. Presence of the expected symptoms is positive
  physical evidence for the cause; their absence is not proof against it
  (records may simply not mention them), so it damps rather than vetoes.
- **Seasonality** — some failure modes track the seasons. Refrigerant leaks
  and cooling-side failures cluster in cooling season; ignition and hydronic
  heating-side failures cluster in heating season.

Everything here is plain data plus pure functions: no I/O, no model state.
``prior_for`` returns a breakdown with a plain-language rationale so a
reader can see exactly why a cause's prior applies — the ranking response
carries that rationale back out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# Cause id -> {equipment_type: fit}. Fit is the prior strength of "this cause
# lives in this equipment" — 1.0 = the subsystem is core to the machine,
# lower = possible but not typical. Absent from the table = physically
# implausible (the equipment has no such subsystem).
_EQUIPMENT_FIT: dict[str, dict[str, float]] = {
    "refrigerant_leak": {"chiller": 1.0, "rooftop_unit": 1.0, "make_up_air_unit": 0.8},
    "compressor_failure": {"chiller": 1.0, "rooftop_unit": 1.0, "make_up_air_unit": 0.8},
    "compressor_surging": {"chiller": 1.0},
    "condenser_fan_motor_failure": {"rooftop_unit": 1.0},
    "control_board_failure": {
        "air_handling_unit": 0.9,
        "boiler": 0.9,
        "chiller": 0.9,
        "cooling_tower": 0.9,
        "exhaust_fan": 0.7,
        "make_up_air_unit": 0.9,
        "rooftop_unit": 0.9,
    },
    "circulator_pump_failure": {"air_handling_unit": 0.7, "boiler": 1.0},
    "ignition_failure": {"boiler": 1.0},
}
# A cause with no subsystem in this equipment is not impossible — records can
# be wrong or the taxonomy incomplete — but it is heavily discounted.
DEFAULT_EQUIPMENT_FIT = 0.1

# Cause id -> symptom patterns the cause physically produces. Matched against
# the asset's extracted symptom spans (lowercased).
_EXPECTED_SYMPTOMS: dict[str, tuple[re.Pattern[str], ...]] = {
    cause: tuple(re.compile(p, re.IGNORECASE) for p in patterns)
    for cause, patterns in {
        "refrigerant_leak": (r"low suction", r"not cooling", r"charge low", r"unit steaming"),
        "compressor_failure": (
            r"low suction",
            r"high head pressure",
            r"hard starting",
            r"short cycling",
            r"not cooling",
        ),
        "compressor_surging": (r"surging", r"shuts? down", r"alarm"),
        "condenser_fan_motor_failure": (
            r"high head pressure",
            r"not cooling",
            r"unit steaming",
            r"not turning",
        ),
        "control_board_failure": (r"lockouts?", r"shuts? down", r"alarm"),
        "circulator_pump_failure": (r"slab loop cold", r"not proving flow", r"no heat"),
        "ignition_failure": (r"no heat", r"lockouts?", r"shuts? down"),
    }.items()
}
# Two distinct expected symptoms = full physical support.
SYMPTOM_SUPPORT_SATURATION = 2

# Seasonal causes and their in-season calendar months (failure-mode load
# follows the weather; a "leak" found in January weighs less than one found
# in July).
COOLING_SEASON_CAUSES = {
    "refrigerant_leak",
    "compressor_failure",
    "compressor_surging",
    "condenser_fan_motor_failure",
}
HEATING_SEASON_CAUSES = {"ignition_failure", "circulator_pump_failure"}
_COOLING_MONTHS = {5, 6, 7, 8, 9}
_HEATING_MONTHS = {10, 11, 12, 1, 2}
_IN_SEASON = 1.0
_SHOULDER = 0.9
_OFF_SEASON = 0.75

# Symptom support contributes at most a quarter of the prior: absence of the
# expected symptoms damps the prior but never vetoes the cause.
_SYMPTOM_FLOOR = 0.75
_SYMPTOM_SPAN = 0.25


@dataclass(frozen=True)
class PriorBreakdown:
    """The prior for one cause on one asset, with its components exposed.

    ``strength`` is what the ranker consumes; the components and the
    ``rationale`` are what a reader inspects.
    """

    cause: str
    strength: float
    equipment_fit: float
    symptom_support: float
    seasonality: float
    rationale: str


def equipment_fit(cause: str, equipment_type: str) -> float:
    """How plausible the cause's subsystem is in this equipment type."""
    return _EQUIPMENT_FIT.get(cause, {}).get(equipment_type, DEFAULT_EQUIPMENT_FIT)


def symptom_support(cause: str, symptom_texts: set[str]) -> float:
    """Fraction (0-1) of expected symptoms the asset's symptom spans show."""
    expected = _EXPECTED_SYMPTOMS.get(cause, ())
    if not expected:
        return 0.0
    matched = sum(
        1 for pattern in expected if any(pattern.search(text) for text in symptom_texts)
    )
    denominator = min(SYMPTOM_SUPPORT_SATURATION, len(expected))
    if denominator == 0:  # pragma: no cover - expected is non-empty above
        return 0.0
    return min(1.0, matched / denominator)


def seasonality_weight(cause: str, recorded_months: set[int]) -> float:
    """Mean seasonal weight of a cause across the months its evidence was recorded."""
    if cause in COOLING_SEASON_CAUSES:
        in_season, off_season = _COOLING_MONTHS, _HEATING_MONTHS
    elif cause in HEATING_SEASON_CAUSES:
        in_season, off_season = _HEATING_MONTHS, _COOLING_MONTHS
    else:
        return 1.0  # not a seasonal failure mode
    if not recorded_months:
        return _SHOULDER
    weights = [
        (
            _IN_SEASON
            if month in in_season
            else _OFF_SEASON
            if month in off_season
            else _SHOULDER
        )
        for month in recorded_months
    ]
    return sum(weights) / len(weights)


def prior_for(
    cause: str,
    equipment_type: str,
    symptom_texts: set[str],
    recorded_months: set[int],
) -> PriorBreakdown:
    """The physics prior for one cause on one asset, with its rationale."""
    fit = equipment_fit(cause, equipment_type)
    symptoms = symptom_support(cause, symptom_texts)
    season = seasonality_weight(cause, recorded_months)
    strength = fit * (_SYMPTOM_FLOOR + _SYMPTOM_SPAN * symptoms) * season

    rationale_parts: list[str] = []
    if fit >= 1.0:
        rationale_parts.append(f"core subsystem of {equipment_type}s")
    elif fit >= 0.5:
        rationale_parts.append(f"plausible for {equipment_type}s")
    else:
        rationale_parts.append(
            f"{equipment_type}s have no typical {cause.replace('_', ' ')} subsystem"
        )
    if symptoms > 0:
        rationale_parts.append("expected symptoms present in the record history")
    elif _EXPECTED_SYMPTOMS.get(cause):
        rationale_parts.append("expected symptoms not seen in the record history")
    if season < 1.0:
        rationale_parts.append("seasonal failure mode, evidence partly off-season")
    elif cause in COOLING_SEASON_CAUSES or cause in HEATING_SEASON_CAUSES:
        rationale_parts.append("seasonal failure mode, evidence in season")
    rationale = "; ".join(rationale_parts)

    return PriorBreakdown(
        cause=cause,
        strength=strength,
        equipment_fit=fit,
        symptom_support=symptoms,
        seasonality=season,
        rationale=rationale,
    )


def evidence_months(recorded_ats: list[datetime]) -> set[int]:
    """The calendar months in which a cause's evidence was recorded."""
    return {recorded.month for recorded in recorded_ats}
