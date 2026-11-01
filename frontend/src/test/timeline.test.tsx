/**
 * Timeline component contract: every entry renders a citation link to its
 * source work order, and inferred entries are visually distinguishable.
 */

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { TimelineEntry } from '../api/types'
import { TimelineView } from '../components/TimelineView'

const observedEntry: TimelineEntry = {
  observation_id: 'WO-0041',
  kind: 'observed',
  recorded_at: '2025-03-14T09:30:00',
  text: 'Compressor winding resistance out of range; replaced compressor.',
  source_ref: 'work-order:WO-0041',
  source_file: 'corpus.csv',
  source_row: 41,
  completed_at: null,
  evidence_ids: null,
  confidence: null,
  payload: {},
}

const inferredEntry: TimelineEntry = {
  observation_id: 'INF-009',
  kind: 'inferred',
  recorded_at: '2025-03-15T10:00:00',
  text: 'Recurring leak pattern inferred from repair history.',
  source_ref: 'work-order:WO-0041',
  source_file: 'corpus.csv',
  source_row: 41,
  completed_at: null,
  evidence_ids: ['WO-0041'],
  confidence: 0.7,
  payload: {},
}

describe('TimelineView', () => {
  it('renders a citation link for an observed entry', () => {
    render(<TimelineView state={{ phase: 'ready', timeline: [observedEntry] }} />)
    const entry = screen.getByTestId('timeline-entry')
    const citation = within(entry).getByRole('link', { name: /WO-0041/ })
    expect(citation).toHaveAttribute('href', '#work-order-WO-0041')
    expect(within(citation).getByText(/row 41/)).toBeInTheDocument()
  })

  it('renders citations for an inferred entry and marks it inferred', () => {
    render(
      <TimelineView state={{ phase: 'ready', timeline: [observedEntry, inferredEntry] }} />,
    )
    const entries = screen.getAllByTestId('timeline-entry')
    const inferred = entries.find((node) => node.textContent?.includes('Inferred'))
    expect(inferred).toBeDefined()
    // The inferred entry cites the observed row it was derived from.
    const evidence = within(inferred!).getByText('Derived from:').parentElement!
    expect(within(evidence).getByRole('link', { name: /WO-0041/ })).toBeInTheDocument()
    // Observed and inferred look different: the inferred card carries the class.
    expect(inferred).toHaveClass('timeline-entry-inferred')
    expect(entries[0]).toHaveClass('timeline-entry-observed')
  })

  it('shows the empty state when the asset has no work orders', () => {
    render(<TimelineView state={{ phase: 'ready', timeline: [] }} />)
    expect(screen.getByText(/No work orders recorded/)).toBeInTheDocument()
  })
})
