/**
 * Asset timeline — chronological work-order observations for one asset.
 *
 * Every entry cites its source record. Observed entries cite the work order
 * they were copied from; inferred entries cite the observed rows they were
 * derived from (``evidence_ids``) and are visually distinct — an inference is
 * never allowed to look like a record.
 */

import type { TimelineEntry } from '../api/types'
import {
  citationForEntry,
  citationsForEvidence,
  formatRecordedAt,
  indexByObservationId,
} from '../lib/citations'
import { ErrorPanel, EmptyPanel, LoadingPanel } from './PanelStates'

function CitationLink({
  workOrderId,
  href,
  locator,
}: {
  workOrderId: string
  href: string
  locator: string
}) {
  return (
    <a className="citation-link" href={href} title={`Source record — ${locator}`}>
      <span aria-hidden="true" className="citation-icon">
        §
      </span>{' '}
      {workOrderId}
      <span className="citation-locator">{locator}</span>
    </a>
  )
}

function EntryCard({ entry, byObservationId }: { entry: TimelineEntry; byObservationId: Map<string, TimelineEntry> }) {
  const isInferred = entry.kind === 'inferred'
  const citation = citationForEntry(entry)
  return (
    <li
      className={`card timeline-entry ${isInferred ? 'timeline-entry-inferred' : 'timeline-entry-observed'}`}
      id={`work-order-${entry.observation_id}`}
      data-testid="timeline-entry"
    >
      <div className="timeline-entry-meta">
        <span className={`badge ${isInferred ? 'badge-inferred' : 'badge-observed'}`}>
          {isInferred ? 'Inferred' : 'Observed'}
        </span>
        <time dateTime={entry.recorded_at}>{formatRecordedAt(entry.recorded_at)}</time>
        {citation && (
          <CitationLink
            workOrderId={citation.workOrderId}
            href={citation.href}
            locator={citation.locator}
          />
        )}
      </div>
      <p className="timeline-entry-text">{entry.text}</p>
      {isInferred && <EvidenceCitations entry={entry} byObservationId={byObservationId} />}
    </li>
  )
}

function EvidenceCitations({
  entry,
  byObservationId,
}: {
  entry: TimelineEntry
  byObservationId: Map<string, TimelineEntry>
}) {
  const citations = citationsForEvidence(entry, byObservationId)
  if (citations.length === 0) return null
  return (
    <div className="evidence-citations">
      <span className="evidence-citations-label">Derived from:</span>
      {citations.map((citation) => (
        <CitationLink
          key={citation.workOrderId}
          workOrderId={citation.workOrderId}
          href={citation.href}
          locator={citation.locator}
        />
      ))}
    </div>
  )
}

export function TimelineList({ timeline }: { timeline: TimelineEntry[] }) {
  if (timeline.length === 0) {
    return (
      <EmptyPanel
        title="No work orders recorded for this asset yet."
        hint="Upload a work-order export to build this asset's history."
      />
    )
  }
  const byObservationId = indexByObservationId(timeline)
  return (
    <ol className="timeline-list">
      {timeline.map((entry) => (
        <EntryCard
          key={entry.observation_id}
          entry={entry}
          byObservationId={byObservationId}
        />
      ))}
    </ol>
  )
}

export type TimelineState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string; retry: () => void }
  | { phase: 'ready'; timeline: TimelineEntry[] }

export function TimelineView({ state }: { state: TimelineState }) {
  switch (state.phase) {
    case 'loading':
      return <LoadingPanel label="Loading timeline" />
    case 'error':
      return <ErrorPanel message={state.message} onRetry={state.retry} />
    case 'ready':
      return <TimelineList timeline={state.timeline} />
  }
}
