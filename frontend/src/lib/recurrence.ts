/**
 * Repeat-failure leaderboard math.
 *
 * A "recurrence" is one work order that recorded a defect finding — the
 * failure language the deterministic extractor treats as defect evidence
 * (``_DEFECT_PATTERNS`` in insmart_api/extractors/deterministic.py). The
 * backend does not yet expose a leaderboard endpoint, so the count is
 * computed client-side over each asset's timeline with the same defect
 * vocabulary; when a backend endpoint lands, this module shrinks to a
 * fetch wrapper.
 */

import type { TimelineEntry } from '../api/types'

// Mirrors the extractor's defect vocabulary (failure causes and repair
// evidence). Symptoms and routine maintenance language are deliberately
// absent: "tenant reports unit noisy" is a symptom, not a failure.
const DEFECT_PATTERNS: readonly RegExp[] = [
  /\bleak/i,
  /\bsurging\b/i,
  /surge margin below minimum/i,
  /not proving flow/i,
  /impeller jammed/i,
  /coupling worn/i,
  /\blocks? out\b/i,
  /igniter cracked/i,
  /flame sensor fouled/i,
  /flame signal weak/i,
  /ignition sequence fails/i,
  /\bscraping\b/i,
  /fan blade loose/i,
  /\bcorroded\b/i,
  /\bseized\b/i,
  /locked-rotor/i,
  /winding resistance out of range/i,
  /short cycling/i,
  /valves weak/i,
  /\bfault code\b/i,
  /traces discolored/i,
  /not cooling/i,
  /low suction/i,
  /hard starting/i,
]

export function isFailureVisit(text: string): boolean {
  return DEFECT_PATTERNS.some((pattern) => pattern.test(text))
}

/** Distinct failure work orders in one asset's timeline. */
export function countRecurrence(entries: TimelineEntry[]): number {
  return entries.filter((entry) => isFailureVisit(entry.text)).length
}

export interface LeaderboardRow {
  assetId: string
  siteId: string
  equipmentType: string
  /** Work orders that recorded a defect finding. */
  recurrenceCount: number
  /** All ingested work orders for the asset. */
  workOrderCount: number
}

export function rankByRecurrence(
  assets: { asset_id: string; site_id: string; equipment_type: string }[],
  timelinesByAsset: Map<string, TimelineEntry[]>,
): LeaderboardRow[] {
  const rows = assets.map<LeaderboardRow>((asset) => {
    const entries = timelinesByAsset.get(asset.asset_id) ?? []
    return {
      assetId: asset.asset_id,
      siteId: asset.site_id,
      equipmentType: asset.equipment_type,
      recurrenceCount: countRecurrence(entries),
      workOrderCount: entries.length,
    }
  })
  // Rank by recurrences, then by total history so ties resolve stably.
  return rows.sort(
    (a, b) => b.recurrenceCount - a.recurrenceCount || b.workOrderCount - a.workOrderCount,
  )
}
