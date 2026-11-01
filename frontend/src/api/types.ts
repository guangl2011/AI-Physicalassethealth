/**
 * API response types — mirrors insmart_api/schemas.py.
 *
 * The diagnosis response is a discriminated union on ``state``. The
 * ``insufficient_evidence`` variant deliberately has no field that could hold a
 * confidence figure: the abstention contract ("never render a confidence number
 * for an abstention") is a property of the type, so the render layer cannot
 * invent one.
 */

export interface AssetSummary {
  asset_id: string
  site_id: string
  equipment_type: string
  installed_year: number | null
  observation_count: number
}

export interface TimelineEntry {
  observation_id: string
  kind: 'observed' | 'inferred'
  recorded_at: string
  text: string
  source_ref: string
  source_file: string | null
  source_row: number | null
  completed_at: string | null
  evidence_ids: string[] | null
  /** Present only on inferred rows; observed rows carry none by constraint. */
  confidence: number | null
  payload: Record<string, unknown>
}

export interface Timeline {
  asset_id: string
  site_id: string
  equipment_type: string
  entries: TimelineEntry[]
}

export interface RankedCause {
  cause: string
  label: string
  confidence: number
  observation_count: number
  observation_ids: string[]
  source_refs: string[]
  evidence_spans: string[]
  prior_rationale: string
}

export interface ContradictionClaim {
  observation_id: string
  source_ref: string
  field: string
  quote: string
  recorded_at: string
}

export interface ContradictionPair {
  component: string
  claim_a: ContradictionClaim
  claim_b: ContradictionClaim
}

interface DiagnosisBase {
  diagnosis_id: string
  asset_id: string
  as_of: string
  rationale: string
}

export interface RankedDiagnosis extends DiagnosisBase {
  state: 'ranked'
  causes: RankedCause[]
}

/** An abstention: rationale and what would help — and nothing else. */
export interface InsufficientDiagnosis extends DiagnosisBase {
  state: 'insufficient_evidence'
  what_would_help: string
}

export interface ContestedDiagnosis extends DiagnosisBase {
  state: 'contested'
  contradictions: ContradictionPair[]
  causes: RankedCause[]
}

export type Diagnosis = RankedDiagnosis | InsufficientDiagnosis | ContestedDiagnosis

export type FeedbackVerdict = 'confirm' | 'correct' | 'reject'

export interface FeedbackResponse {
  id: number
  diagnosis_id: string
  verdict: string
  corrected_cause: string | null
  note: string | null
  created_at: string
}
