"""Deterministic synthetic evaluation corpus generator for the Insmart AI MVP.

Produces, in a fixed output directory:

- ``corpus.csv``  — 150 synthetic commercial-HVAC work orders across 20 assets
  in the canonical ingestion shape the work-order parser will target, including
  deliberately malformed rows (missing columns, invalid dates, duplicates,
  unresolvable and ambiguous asset references) that downstream parser tests
  depend on.
- ``labels.json`` — adjudicated ground truth per asset: known failure causes,
  evidence-sufficiency flags (thin-history assets feed abstention tests),
  contradiction pairs, and provenance locators back to work-order ids.

The same ``--seed`` always yields byte-identical output; the committed corpus
and labels are regenerated with the default seed of 42.

Run: ``python seed/generate_corpus.py [--out-dir seed] [--seed 42]``
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_SEED = 42
TARGET_TOTAL_ROWS = 150
MALFORMED_ROW_COUNT = 9
SCHEMA_VERSION = "1.0.0"

# Resolvable work orders required before an asset's history is considered
# evidence-sufficient. Thin-history assets fall below this on purpose.
SUFFICIENCY_THRESHOLD = 8

FIRST_CREATED = datetime(2024, 1, 2, 7, 0, 0)
LAST_CREATED = datetime(2025, 10, 31, 18, 0, 0)

CSV_COLUMNS = [
    "work_order_id",
    "created_at",
    "completed_at",
    "site",
    "asset_tag",
    "summary",
    "technician",
    "notes",
    "resolution",
    "labor_hours",
    "priority",
]

TECHNICIANS = ["M. Alvarez", "D. Chen", "S. Okafor", "J. Wheeler", "P. Nakamura", "R. Delgado"]

# Raw tag variants the parser must normalize. ``AMBIGUOUS_TAGS`` resolve only
# with context (e.g. "Unit 3" fits both AHU-3 and RTU-3) and are excluded from
# label provenance.
AMBIGUOUS_TAGS = ("Unit 3", "unit three", "bldg 2 unit 3")

UNRESOLVABLE_TAGS = ("CHILLER-99", "RTU-???")
INVALID_DATES = ("2026-13-45T09:00:00", "not-a-date", "31/02/2024 10:00:00")


@dataclass(frozen=True)
class Asset:
    asset_id: str
    site: str
    equipment_type: str
    installed_year: int
    history_depth: str  # "rich" | "moderate" | "thin"
    failure_modes: tuple[str, ...]
    tag_variants: tuple[str, ...]


ASSETS: tuple[Asset, ...] = (
    Asset("AHU-1", "Harborview Medical Center", "air_handling_unit", 2009, "moderate",
          ("bearing_failure", "damper_actuator_failure"), ("AHU-1", "ahu-1", "AHU #1")),
    Asset("AHU-2", "Harborview Medical Center", "air_handling_unit", 2009, "moderate",
          ("fan_motor_failure", "belt_slippage"), ("AHU-2", "AHU 2", "Air Handler 2")),
    Asset("AHU-3", "Harborview Medical Center", "air_handling_unit", 2014, "moderate",
          ("bearing_failure", "filter_face_velocity"), ("AHU-3", "ahu 3", "Air Handler #3")),
    Asset("AHU-4", "Harborview Medical Center", "air_handling_unit", 2018, "thin",
          ("damper_actuator_failure",), ("AHU-4", "AHU-4")),
    Asset("CH-1", "Harborview Medical Center", "chiller", 2011, "rich",
          ("compressor_surging", "refrigerant_leak"), ("CH-1", "chiller 1", "CHILLER-1")),
    Asset("CT-1", "Harborview Medical Center", "cooling_tower", 2011, "moderate",
          ("fill_fouling", "fan_motor_failure"), ("CT-1", "CT 1", "Cooling Tower 1")),
    Asset("BLR-1", "Harborview Medical Center", "boiler", 2007, "rich",
          ("ignition_failure", "circulator_pump_failure"), ("BLR-1", "boiler 1", "BOILER-1")),
    Asset("RTU-1", "Meridian Office Park", "rooftop_unit", 2013, "moderate",
          ("control_board_failure",), ("RTU-1", "rtu 1", "RTU #1")),
    Asset("RTU-2", "Meridian Office Park", "rooftop_unit", 2012, "rich",
          ("compressor_failure", "condenser_fan_motor_failure"), ("RTU-2", "rtu-2", "RTU #2")),
    Asset("RTU-3", "Meridian Office Park", "rooftop_unit", 2016, "moderate",
          ("refrigerant_leak", "blower_motor_failure"), ("RTU-3", "rtu 3", "Rooftop Unit 3")),
    Asset("RTU-4", "Meridian Office Park", "rooftop_unit", 2010, "rich",
          ("compressor_failure", "control_board_failure"), ("RTU-4", "RTU 4", "Rooftop #4")),
    Asset("RTU-5", "Meridian Office Park", "rooftop_unit", 2020, "thin",
          ("refrigerant_leak",), ("RTU-5", "RTU-5")),
    Asset("AHU-5", "Meridian Office Park", "air_handling_unit", 2015, "moderate",
          ("belt_slippage", "fan_motor_failure"), ("AHU-5", "ahu-5", "AHU 5")),
    Asset("AHU-6", "Cedar Ridge Mall", "air_handling_unit", 2012, "moderate",
          ("bearing_failure", "damper_actuator_failure"), ("AHU-6", "ahu 6", "AHU #6")),
    Asset("CH-2", "Cedar Ridge Mall", "chiller", 2015, "moderate",
          ("tube_fouling", "control_fault"), ("CH-2", "chiller 2", "CHILLER-2")),
    Asset("CT-2", "Cedar Ridge Mall", "cooling_tower", 2015, "thin",
          ("fan_motor_failure",), ("CT-2", "CT-2")),
    Asset("BLR-2", "Cedar Ridge Mall", "boiler", 2018, "thin",
          ("low_water_cutoff_fault",), ("BLR-2", "boiler 2")),
    Asset("EF-1", "Cedar Ridge Mall", "exhaust_fan", 2012, "moderate",
          ("belt_failure",), ("EF-1", "EF 1", "Exhaust Fan 1")),
    Asset("EF-2", "Cedar Ridge Mall", "exhaust_fan", 2008, "thin",
          ("motor_bearing_failure",), ("EF-2", "EF-2")),
    Asset("MAU-1", "Cedar Ridge Mall", "make_up_air_unit", 2019, "moderate",
          ("gas_valve_failure", "blower_motor_failure"), ("MAU-1", "MAU 1", "Make-up Air 1")),
)

# Work orders per asset by history depth. 5 rich + 11 moderate + 4 thin assets.
DEPTH_WEIGHTS = {"rich": 14, "moderate": 6, "thin": 2}

# Per-failure-mode language: (symptom phrases, defect phrases, resolution
# phrases). The parser's weak-supervision lexicon is later evaluated against
# these phrases via labels.json.
MODE_TEXT: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "compressor_failure": (
        ("Compressor short cycling and tripping on high head pressure.",
         "Unit hard starting, compressor drawing locked-rotor amps on restart."),
        ("Suspected failed compressor, valves weak on pump-down check.",
         "Compressor winding resistance out of range, confirm with megger."),
        ("Replaced compressor with new Copeland scroll, recovered charge, pressure tested.",
         "Compressor replaced under warranty, system evacuated and recharged to nameplate."),
    ),
    "condenser_fan_motor_failure": (
        ("Condenser fan not turning, unit steaming at the condenser coil.",
         "Loud scraping from condenser section, fan blade rubbing shroud."),
        ("Condenser fan motor seized, shaft will not turn by hand.",
         "Fan blade loose on motor shaft, motor mounts corroded through."),
        ("Replaced condenser fan motor and blade, verified amp draw within FLA.",
         "New fan motor installed, checked rotation and superheat."),
    ),
    "control_board_failure": (
        ("Intermittent lockouts, board LEDs flashing fault code 4.",
         "Unit randomly shuts down, resets itself after power cycle."),
        ("Corroded terminals on defrost board, traces discolored.",
         "Board not energizing blower tap, suspect relay failure."),
        ("Replaced control board and harness, verified stages sequence correctly.",
         "New defrost board installed, test ran full cycle without lockout."),
    ),
    "refrigerant_leak": (
        ("Low suction pressure, unit not cooling, evidence of oil at service valve.",
         "Charge low again three weeks after top-off, suspect leak at evaporator coil."),
        ("Electronic detector alarming at the liquid line braze joint.",
         "Bubble test shows leak at evaporator return bend."),
        ("Located and repaired leak at coil header, pressure tested with nitrogen, recharged.",
         "Repaired braze joint, pulled vacuum to 500 microns, weighed in charge."),
    ),
    "blower_motor_failure": (
        ("Weak airflow from supply registers, blower tripping on overload.",
         "Blower squealing on startup, then breaker trips."),
        ("Blower motor bearings rough, end play excessive.",
         "Blower wheel dirty and unbalanced, motor amps above nameplate."),
        ("Replaced blower motor and capacitor, balanced wheel, airflow restored.",
         "New blower motor installed, checked belt tension and amps."),
    ),
    "bearing_failure": (
        ("Fan bearing noise audible in occupied space, vibration increasing.",
         "Plenum rumbling, bearing temperature elevated on IR scan."),
        ("Drive-end bearing spalled, grease dark and contaminated.",
         "Bearing seized on fan shaft, sheave scored."),
        ("Replaced fan shaft bearings, aligned sheaves, vibration within limits.",
         "New bearings and grease lines installed, baseline vibration recorded."),
    ),
    "damper_actuator_failure": (
        ("Mixed air temperature swings, outdoor air damper not modulating.",
         "OA damper stuck closed, economizer not changing over."),
        ("Actuator coupling stripped, damper shaft does not rotate.",
         "Actuator not responding to 2-10V command."),
        ("Replaced damper actuator and linkage, verified stroke and sequencing.",
         "New actuator commissioned, economizer changeover verified."),
    ),
    "fan_motor_failure": (
        ("Fan tripping on overload during morning startup.",
         "Airflow low, VFD showing high current alarm."),
        ("Motor windings smell of varnish, insulation resistance marginal.",
         "Fan wheel out of balance, motor bearings dry."),
        ("Replaced fan motor, verified rotation, amp draw and airflow.",
         "New motor and VFD parameters verified, unit returned to service."),
    ),
    "belt_slippage": (
        ("Squealing on startup, airflow below design.",
         "Tenant reports weak air, belt glazing noted at last visit."),
        ("Belt worn past wear line, sheave grooves worn.",
         "Belt tension loose, auto-tensioner spring fatigued."),
        ("Replaced belt, adjusted tension, verified sheave alignment.",
         "New belt installed and tensioned, airflow verified."),
    ),
    "filter_face_velocity": (
        ("Filter rack bypass, coils loading up with dust.",
         "Pressure drop across filter bank above threshold."),
        ("Filters collapsed into rack, bypass around cartridge seals.",
         "Wrong size filters installed, gaps at rack edges."),
        ("Replaced filters, sealed rack bypass gaps, verified pressure drop.",
         "Correct MERV filters installed and rack sealed."),
    ),
    "compressor_surging": (
        ("Chiller surging audibly at high load, trips on surge counter.",
         "Surge alarm on hot afternoons, approach temperature climbing."),
        ("Impeller fouling suspected, surge margin below minimum.",
         "Prerotation vanes sticking, surge control hunting."),
        ("Cleaned condenser tubes and verified refrigerant level, surge margin restored.",
         "PRV serviced and recalibrated, chiller ran full load without surge."),
    ),
    "tube_fouling": (
        ("Approach temperature high, ton-hours down this season.",
         "Chiller efficiency degraded, condenser delta-T abnormal."),
        ("Condenser tubes scaled, brush test confirms heavy deposit.",
         "Water-side fouling evident, biocide program lapsed."),
        ("Cleaned condenser tubes chemically, verified approach temperature.",
         "Tube cleaning completed, water treatment program reinstated."),
    ),
    "control_fault": (
        ("Chiller trips on low evaporator temperature under part load.",
         "Setpoint drifts, control panel reporting sensor faults."),
        ("Evaporator sensor reading out of tolerance, control unstable.",
         "Panel battery dead, program reverted to defaults."),
        ("Replaced faulty sensor, reprogrammed setpoints, verified stability.",
         "Control panel repaired, settings documented and backed up."),
    ),
    "ignition_failure": (
        ("Boiler locks out on ignition, tenant without heat overnight.",
         "Intermittent lockouts, flame signal weak."),
        ("Igniter cracked, flame sensor fouled with oxidation.",
         "Gas pressure low at manifold, ignition sequence fails."),
        ("Replaced igniter, cleaned flame sensor, verified flame signal and firing rate.",
         "Repaired gas train, boiler fired and held setpoint through full cycle."),
    ),
    "circulator_pump_failure": (
        ("Slab loop cold, circulator not proving flow.",
         "End switch never closes, pump amps low."),
        ("Circulator seal leaking, coupling worn.",
         "Pump impeller jammed by debris."),
        ("Replaced circulator and seal, purged air, verified flow and delta-T.",
         "New pump installed, system balanced and verified."),
    ),
    "low_water_cutoff_fault": (
        ("Boiler locked out on low water cutoff, manual reset required.",
         "LWCO tripping daily, feeder not filling."),
        ("Low water cutoff probe scaled, test button fails.",
         "Feeder valve passing, float chamber fouled."),
        ("Replaced low water cutoff probe and feeder, verified cutout on slow drain.",
         "LWCO serviced and tested per code, blowdown scheduled."),
    ),
    "fill_fouling": (
        ("Approach temperature drifting up, basin water quality poor.",
         "Tower not rejecting design load, scale in fill pack."),
        ("Fill pack scaled and plugged, distribution nozzles clogged.",
         "Basin sludge heavy, biocide levels low."),
        ("Cleaned fill pack and basin, replaced nozzles, water treatment verified.",
         "Descale completed, approach temperature back to design."),
    ),
    "belt_failure": (
        ("Exhaust fan stopped, tenant reports no restroom exhaust.",
         "Fan amp draw zero, breaker found tripped."),
        ("Belt broken and thrown, sheave alignment off.",
         "Belt cracked and glazed, tension at minimum."),
        ("Replaced belt, aligned sheaves, verified airflow and amps.",
         "New belt and tensioner installed, fan back in service."),
    ),
    "motor_bearing_failure": (
        ("Grinding noise from fan, vibration felt at access door.",
         "Motor hot to touch, thermal protector cycling."),
        ("Motor bearings rough with axial play, windings tested OK.",
         "Bearing grease burned, contamination from dust load."),
        ("Replaced exhaust fan motor, verified rotation and amp draw.",
         "New motor installed with dust shielding, vibration normal."),
    ),
    "gas_valve_failure": (
        ("Make-up air unit not firing, space temperature dropping.",
         "Intermittent ignition, gas valve clicking but no flame."),
        ("Gas valve sticks closed, actuator coil out of spec.",
         "Valve proving switch fault."),
        ("Replaced gas valve, verified manifold pressure and safe shutdown.",
         "New valve installed, combustion analyzed and tuned."),
    ),
}

# Generic (non-failure) maintenance text pools for filler work orders.
GENERIC_SYMPTOMS = (
    "Tenant reports unit noisy during occupied hours.",
    "Quarterly PM due per service agreement.",
    "Customer complaints of musty smell at the diffusers.",
    "Owner requested inspection ahead of lease turnover.",
    "Follow-up from last visit to confirm temperatures.",
    "BAS alarm notification for runtime above normal.",
)
GENERIC_NOTES = (
    "Inspected unit, checked filters, belts and refrigerant pressures. All within range.",
    "Completed scheduled PM checklist, logged temperatures and pressures for baseline.",
    "Cleaned drain pan and treated pan tablets, verified condensate flow.",
    "Checked economizer operation and damper travel, calibrated setpoints.",
    "Tightened electrical connections, recorded amps for trend.",
    "Walked roof, no visible damage or debris at unit. Photos attached.",
)
GENERIC_RESOLUTIONS = (
    "No defects found, unit performing to spec.",
    "PM completed, next service scheduled.",
    "Cleaned and inspected, monitoring trend.",
    "Adjusted setpoints per operator request.",
    "No action required this visit.",
)

# Contradiction plans: two work orders on the same asset whose service records
# conflict. Pairs marked "unresolved" feed timeline-conflict rendering tests.
CONTRADICTION_PLANS: tuple[dict[str, str], ...] = (
    {
        "asset_id": "RTU-2",
        "mode": "compressor_failure",
        "claim_a_field": "resolution",
        "claim_a_text": "Replaced compressor with new unit, system recharged.",
        "claim_b_field": "notes",
        "claim_b_text": (
            "Compressor nameplate shows 2011 manufacture date; appears original, "
            "no record of prior replacement."
        ),
        "adjudication": "unresolved",
    },
    {
        "asset_id": "CH-1",
        "mode": "compressor_surging",
        "claim_a_field": "resolution",
        "claim_a_text": "Surge caused by worn compressor; compressor replacement scheduled.",
        "claim_b_field": "notes",
        "claim_b_text": (
            "Surge traced to fouled condenser tubes; compressor itself healthy "
            "and original."
        ),
        "adjudication": "resolved: tube-cleaning record in the second work order confirms "
        "the fouling diagnosis; compressor replacement was never performed",
    },
    {
        "asset_id": "BLR-1",
        "mode": "ignition_failure",
        "claim_a_field": "resolution",
        "claim_a_text": "Replaced gas valve, verified manifold pressure.",
        "claim_b_field": "notes",
        "claim_b_text": (
            "Gas valve nameplate dated 2007, appears original — no record of "
            "prior replacement."
        ),
        "adjudication": "unresolved",
    },
)


def distribute_counts(total: int) -> list[int]:
    """Largest-remainder apportionment of ``total`` work orders across assets."""
    weights = [DEPTH_WEIGHTS[a.history_depth] for a in ASSETS]
    weight_sum = sum(weights)
    raw = [total * w / weight_sum for w in weights]
    counts = [int(r) for r in raw]
    remainder = total - sum(counts)
    order = sorted(
        range(len(ASSETS)),
        key=lambda i: (-(raw[i] - counts[i]), ASSETS[i].asset_id),
    )
    for i in order[:remainder]:
        counts[i] += 1
    return counts


@dataclass
class WorkOrder:
    wo_id: str
    created_at: datetime
    completed_at: datetime
    site: str
    asset_tag: str
    summary: str
    technician: str
    notes: str
    resolution: str
    labor_hours: str
    priority: str
    asset: Asset
    failure_mode: str | None

    def is_ambiguous(self) -> bool:
        return self.asset_tag in AMBIGUOUS_TAGS

    def to_row(self) -> list[str]:
        return [
            self.wo_id,
            self.created_at.isoformat(),
            self.completed_at.isoformat(),
            self.site,
            self.asset_tag,
            self.summary,
            self.technician,
            self.notes,
            self.resolution,
            self.labor_hours,
            self.priority,
        ]


def build_mode_text(rng: random.Random, mode: str) -> tuple[str, str, str]:
    symptom, defect, resolution = MODE_TEXT[mode]
    return rng.choice(symptom), rng.choice(defect), rng.choice(resolution)


def make_work_order(rng: random.Random, asset: Asset, seq: int, index: int) -> WorkOrder:
    """Build one work order; every third order on a rich asset is a failure event."""
    mode = pick_failure_mode(asset, index)
    if mode:
        symptom, defect, resolution = build_mode_text(rng, mode)
        summary = f"{asset.asset_id} {mode.replace('_', ' ')} investigation"
        priority = rng.choice(["high", "emergency", "medium"])
        labor = round(rng.uniform(2.0, 8.0), 1)
    else:
        symptom = rng.choice(GENERIC_SYMPTOMS)
        defect = rng.choice(GENERIC_NOTES)
        resolution = rng.choice(GENERIC_RESOLUTIONS)
        summary = f"{asset.asset_id} {rng.choice(['scheduled service', 'inspection', 'PM visit'])}"
        priority = rng.choice(["low", "medium"])
        labor = round(rng.uniform(0.5, 3.0), 1)

    created = FIRST_CREATED + timedelta(
        seconds=rng.uniform(0, (LAST_CREATED - FIRST_CREATED).total_seconds())
    )
    completed = created + timedelta(hours=rng.uniform(1.0, 72.0))
    tag = rng.choice(asset.tag_variants) if rng.random() < 0.7 else asset.asset_id
    if asset.asset_id in ("AHU-3", "RTU-3") and index % 3 == 2:
        tag = rng.choice(AMBIGUOUS_TAGS)
    return WorkOrder(
        wo_id=f"WO-{seq:04d}",
        created_at=created.replace(microsecond=0),
        completed_at=completed.replace(microsecond=0),
        site=asset.site,
        asset_tag=tag,
        summary=summary,
        technician=rng.choice(TECHNICIANS),
        notes=f"{symptom} {defect}",
        resolution=resolution,
        labor_hours=str(labor),
        priority=priority,
        asset=asset,
        failure_mode=mode,
    )


def pick_failure_mode(asset: Asset, index: int) -> str | None:
    if asset.history_depth != "rich" or index % 3 != 1:
        return None
    return asset.failure_modes[index % len(asset.failure_modes)]


def apply_contradictions(orders: list[WorkOrder]) -> list[dict[str, str]]:
    """Overwrite text on selected work orders to realize the contradiction plans."""
    pairs: list[dict[str, str]] = []
    for plan in CONTRADICTION_PLANS:
        asset_orders = [o for o in orders if o.asset.asset_id == plan["asset_id"]]
        candidates = [o for o in asset_orders if o.failure_mode == plan["mode"]]
        if len(candidates) < 2:
            continue  # plans are sized so this never fires; guard keeps it total
        first, second = candidates[0], candidates[-1]
        first.resolution = plan["claim_a_text"]
        second.notes = f"{second.notes} {plan['claim_b_text']}"
        pairs.append(
            {
                "asset_id": str(plan["asset_id"]),
                "claim_a": (
                    f"{first.wo_id}:{plan['claim_a_field']}:{plan['claim_a_text']}"
                ),
                "claim_b": (
                    f"{second.wo_id}:{plan['claim_b_field']}:{plan['claim_b_text']}"
                ),
                "adjudication": str(plan["adjudication"]),
            }
        )
    return pairs


def make_malformed_rows(orders: list[WorkOrder]) -> list[list[str]]:
    """Inject deliberately broken rows the parser must handle gracefully."""
    rows: list[list[str]] = []

    # 1. missing column: a ragged short row (no notes field)
    short = orders[10].to_row()
    del short[CSV_COLUMNS.index("notes")]
    rows.append(short)

    # 2. missing value: empty created_at (duplicates an existing work order id)
    empty_ts = orders[20].to_row()
    empty_ts[CSV_COLUMNS.index("created_at")] = ""
    rows.append(empty_ts)

    # 3. invalid dates
    for offset, bad_date in enumerate(INVALID_DATES, start=1):
        row = orders[30 + offset].to_row()
        row[CSV_COLUMNS.index("created_at")] = bad_date
        row[0] = f"WO-BAD-{offset:04d}"
        rows.append(row)

    # 4. duplicates: one identical copy, one same-id-different-content
    rows.append(list(orders[40].to_row()))
    conflicting = orders[41].to_row()
    conflicting[CSV_COLUMNS.index("notes")] = (
        "Second entry filed under the same work order id."
    )
    rows.append(conflicting)

    # 5. unresolvable asset references
    for offset, tag in enumerate(UNRESOLVABLE_TAGS, start=1):
        ghost = orders[50 + offset].to_row()
        ghost[CSV_COLUMNS.index("asset_tag")] = tag
        ghost[0] = f"WO-GHOST-{offset:04d}"
        rows.append(ghost)

    return rows


def evidence_entry(order: WorkOrder, field_name: str, quote: str) -> dict[str, str]:
    return {"work_order_id": order.wo_id, "field": field_name, "quote": quote[:160]}


def build_labels(
    orders: list[WorkOrder],
    contradiction_pairs: list[dict[str, str]],
    total_rows: int,
    seed: int,
) -> dict[str, object]:
    """Adjudicated ground truth derived from the same in-memory work orders."""
    assets_out: list[dict[str, object]] = []
    for asset in ASSETS:
        resolvable = [
            o for o in orders if o.asset.asset_id == asset.asset_id and not o.is_ambiguous()
        ]
        sufficient = len(resolvable) >= SUFFICIENCY_THRESHOLD
        causes = []
        for mode in dict.fromkeys(o.failure_mode for o in resolvable if o.failure_mode):
            mode_orders = [o for o in resolvable if o.failure_mode == mode]
            evidence = [evidence_entry(o, "notes", o.notes) for o in mode_orders] + [
                evidence_entry(o, "resolution", o.resolution) for o in mode_orders
            ]
            causes.append(
                {
                    "cause": mode,
                    "work_order_ids": [o.wo_id for o in mode_orders],
                    "evidence": evidence,
                    "first_observed": min(o.created_at for o in mode_orders).isoformat(),
                    "last_observed": max(o.created_at for o in mode_orders).isoformat(),
                }
            )

        assets_out.append(
            {
                "asset_id": asset.asset_id,
                "site": asset.site,
                "equipment_type": asset.equipment_type,
                "installed_year": asset.installed_year,
                "work_order_count": len(resolvable),
                "known_failure_causes": causes,
                "evidence_sufficiency": {
                    "sufficient": sufficient,
                    "reason": (
                        f"{len(resolvable)} resolvable work orders "
                        f"(>= threshold {SUFFICIENCY_THRESHOLD})"
                        if sufficient
                        else f"thin_history: only {len(resolvable)} resolvable work "
                        f"orders (< threshold {SUFFICIENCY_THRESHOLD})"
                    ),
                },
                "contradiction_pairs": [
                    pair for pair in contradiction_pairs
                    if pair["asset_id"] == asset.asset_id
                ],
                "provenance": {"work_order_ids": [o.wo_id for o in resolvable]},
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generator_seed": seed,
        "sufficiency_threshold_resolvable_orders": SUFFICIENCY_THRESHOLD,
        "corpus": {
            "path": "corpus.csv",
            "work_order_count": total_rows,
            "malformed_row_count": MALFORMED_ROW_COUNT,
            "asset_count": len(ASSETS),
        },
        "assets": assets_out,
    }


def build_corpus(seed: int) -> tuple[list[list[str]], dict[str, object]]:
    """Generate all CSV rows and the labels document for ``seed``."""
    rng = random.Random(seed)
    valid_target = TARGET_TOTAL_ROWS - MALFORMED_ROW_COUNT

    orders: list[WorkOrder] = []
    for asset, count in zip(ASSETS, distribute_counts(valid_target), strict=True):
        for index in range(count):
            orders.append(make_work_order(rng, asset, len(orders) + 1, index))

    contradiction_pairs = apply_contradictions(orders)
    rows = [o.to_row() for o in orders] + make_malformed_rows(orders)
    labels = build_labels(orders, contradiction_pairs, len(rows), seed)
    return rows, labels


def write_outputs(out_dir: Path, rows: list[list[str]], labels: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "corpus.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        writer.writerows(rows)

    with (out_dir / "labels.json").open("w", encoding="utf-8") as handle:
        json.dump(labels, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Insmart seed corpus.")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    rows, labels = build_corpus(args.seed)
    write_outputs(args.out_dir, rows, labels)
    print(f"wrote {len(rows)} work orders and labels to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
