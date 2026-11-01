# Seed corpus — synthetic evaluation data for the Insmart AI MVP

This directory holds the deterministic synthetic evaluation corpus (spec
`art_N0ARICWR`, deliverable D3 groundwork): ~150 commercial-HVAC work orders
across 20 assets, plus adjudicated ground-truth labels. The whole downstream
test strategy (parser, timeline, ranked diagnosis, abstention) stands on these
files.

## Contents

| File | What it is |
|---|---|
| `generate_corpus.py` | Deterministic generator (fixed seed, default 42) |
| `corpus.csv` | 150 work orders, generated output — **committed** |
| `labels.json` | Adjudicated ground truth, generated output — **committed** |

## Corpus shape (`corpus.csv`)

Canonical ingestion shape the work-order parser targets — 11 columns:

| Column | Notes |
|---|---|
| `work_order_id` | `WO-nnnn` plus deliberately broken ids (`WO-BAD-*`, `WO-GHOST-*`) |
| `created_at` / `completed_at` | ISO-8601 timestamps (some deliberately invalid) |
| `site` | One of three fictional sites |
| `asset_tag` | **Raw technician-entered tag**, not a canonical id |
| `summary` | Short free-text line |
| `technician` | Free-text name |
| `notes` | Technician free text with symptom/defect language |
| `resolution` | Outcome text with action language |
| `labor_hours` | Decimal hours |
| `priority` | low / medium / high / emergency |

### Asset identifier variants

`asset_tag` is intentionally messy. The parser must normalize variants such as
`RTU-2`, `rtu-2`, `RTU #2` to one canonical asset. Two ambiguity classes exist
on purpose:

- **Ambiguous tags** (`Unit 3`, `unit three`, `bldg 2 unit 3`) — appear on rows
  belonging to both `AHU-3` and `RTU-3`. Resolvable only with site/equipment
  context; excluded from label provenance.
- **Unresolvable tags** (`CHILLER-99`, `RTU-???`) — match no asset in the
  inventory; the parser must surface these, not silently drop them.

### Malformed rows (9 of 150)

Deliberately injected for parser tests: one ragged row missing the `notes`
column, one row with an empty `created_at`, three rows with invalid dates
(`2026-13-45T09:00:00`, `not-a-date`, `31/02/2024 10:00:00`), one identical
duplicate row, one duplicate-id row with conflicting content, and the two
unresolvable asset rows above. Any test may assert their presence.

## Label schema (`labels.json`)

Top level: `schema_version`, `generator_seed`,
`sufficiency_threshold_resolvable_orders`, `corpus` (counts), `assets`.

Each entry in `assets` (one per canonical asset):

- `asset_id`, `site`, `equipment_type`, `installed_year` — inventory fields.
- `known_failure_causes` — list of `{cause, work_order_ids, evidence,
  first_observed, last_observed}`. `evidence` items locate the claim:
  `{work_order_id, field, quote}` where `field` names the CSV column and
  `quote` is the exact text (≤160 chars) found there. Present only for
  rich-history assets.
- `evidence_sufficiency` — `{sufficient, reason}`. An asset is sufficient when
  it has ≥ 8 resolvable work orders. Thin-history assets (4, with 2 work
  orders each) are `sufficient: false` — they feed **abstention tests**.
- `contradiction_pairs` — two work orders on the same asset whose records
  conflict (e.g. "compressor replaced" vs "compressor appears original").
  Claims are located as `work_order_id:field:quote`; `adjudication` records
  the ground-truth verdict (`unresolved`, or `resolved: ...` with the
  rationale). Three pairs, on RTU-2, CH-1, and BLR-1.
- `provenance` — `work_order_ids`: every resolvable work order backing the
  labels for this asset (ambiguous-tag rows excluded).

All label `work_order_id` values resolve to rows in `corpus.csv`.

## Regeneration

```bash
python seed/generate_corpus.py                # writes seed/corpus.csv + seed/labels.json
python seed/generate_corpus.py --seed 7 --out-dir /tmp/x   # any seed; same seed → byte-identical
```

The committed `corpus.csv` and `labels.json` are the seed-42 output. Tests
regenerate into a temp directory and byte-compare against the committed files,
so any generator change that alters output must be accompanied by regenerating
both files in the same commit.
