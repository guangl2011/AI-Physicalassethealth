/**
 * Citation helpers — provenance is rendered, never paraphrased.
 *
 * Every observed observation cites its source work order via a
 * ``work-order:<id>`` source_ref (see insmart_api/integrity.py). Inferred
 * observations cite the observed rows they were derived from via
 * ``evidence_ids``. Citations render as in-page links to the cited record.
 */

import type { TimelineEntry } from '../api/types'

/** ``work-order:WO-0041`` → ``WO-0041``; null when the ref is malformed. */
export function workOrderIdFromRef(sourceRef: string): string | null {
  const [scheme, workOrderId] = sourceRef.split(':')
  if (scheme !== 'work-order' || !workOrderId) return null
  return workOrderId
}

export interface Citation {
  /** Work-order id the citation points at, e.g. ``WO-0041``. */
  workOrderId: string
  /** In-page anchor target of the cited record's card. */
  href: string
  /** Human-readable locator, e.g. ``corpus.csv · row 41``. */
  locator: string
}

export function citationForEntry(entry: TimelineEntry): Citation | null {
  const workOrderId = workOrderIdFromRef(entry.source_ref)
  if (workOrderId === null) return null
  const locatorParts = [entry.source_file, entry.source_row !== null ? `row ${entry.source_row}` : null]
  return {
    workOrderId,
    href: `#work-order-${entry.observation_id}`,
    locator: locatorParts.filter((part) => part !== null).join(' · '),
  }
}

/** Citations for an inferred entry: the observed rows it was derived from. */
export function citationsForEvidence(
  entry: TimelineEntry,
  byObservationId: Map<string, TimelineEntry>,
): Citation[] {
  return (entry.evidence_ids ?? []).flatMap((id) => {
    const evidence = byObservationId.get(id)
    return evidence ? [citationForEntry(evidence)].filter((c) => c !== null) : []
  })
}

export function indexByObservationId(entries: TimelineEntry[]): Map<string, TimelineEntry> {
  return new Map(entries.map((entry) => [entry.observation_id, entry]))
}

export function formatRecordedAt(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
