/**
 * The absolute contract, enforced at the render layer: an abstention card
 * shows the plain-language reason and what would help — and no confidence
 * figure anywhere. Mirrors tests/test_diagnosis.py's
 * test_abstention_response_never_carries_a_confidence_figure.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { InsufficientDiagnosis, RankedDiagnosis } from '../api/types'
import { DiagnosisPanel } from '../components/DiagnosisPanel'
import { fetchMock } from './helpers'

const abstention: InsufficientDiagnosis = {
  state: 'insufficient_evidence',
  diagnosis_id: 'diag-123',
  asset_id: 'AHU-1',
  as_of: '2026-11-01T00:00:00',
  rationale: 'Only 2 distinct defect observations exist for this asset — below the 3 needed.',
  what_would_help: 'More repair records naming the failed component.',
}

const ranked: RankedDiagnosis = {
  state: 'ranked',
  diagnosis_id: 'diag-456',
  asset_id: 'RTU-2',
  as_of: '2026-11-01T00:00:00',
  rationale: 'Enough usable evidence to rank causes.',
  causes: [
    {
      cause: 'compressor_failure',
      label: 'Compressor failure',
      confidence: 0.72,
      observation_count: 4,
      observation_ids: ['WO-0100'],
      source_refs: ['work-order:WO-0100'],
      evidence_spans: ['winding resistance out of range'],
      prior_rationale: 'Compressor failures dominate this equipment class.',
    },
  ],
}

beforeEach(() => {
  fetchMock.install()
})

afterEach(() => {
  fetchMock.uninstall()
})

describe('DiagnosisPanel — abstention invariant', () => {
  it('renders the plain-language reason and what would help', async () => {
    fetchMock.route(/\/diagnosis$/, abstention)
    fetchMock.route(/\/timeline$/, { asset_id: 'AHU-1', entries: [] })
    render(<DiagnosisPanel assetId="AHU-1" />)

    const card = await screen.findByTestId('abstention-card')
    expect(card).toHaveTextContent('Not enough evidence to diagnose')
    expect(
      screen.getByText(/Only 2 distinct defect observations exist/),
    ).toBeInTheDocument()
    expect(screen.getByText(/More repair records naming the failed component/)).toBeInTheDocument()
  })

  it('renders no confidence figure anywhere on an abstention card', async () => {
    fetchMock.route(/\/diagnosis$/, abstention)
    fetchMock.route(/\/timeline$/, { asset_id: 'AHU-1', entries: [] })
    const { container } = render(<DiagnosisPanel assetId="AHU-1" />)

    await screen.findByTestId('abstention-card')
    const cardText = screen.getByTestId('abstention-card').textContent ?? ''
    // No confidence word, no confidence bar, no percentage, no 0–1 score.
    expect(cardText).not.toMatch(/confidence/i)
    expect(cardText).not.toMatch(/0\.\d+/)
    expect(cardText).not.toMatch(/\d+%/)
    expect(container.querySelector('.confidence-bar')).toBeNull()
  })

  it('renders confidence bars only for ranked causes', async () => {
    fetchMock.route(/\/diagnosis$/, ranked)
    fetchMock.route(/\/timeline$/, { asset_id: 'RTU-2', entries: [] })
    render(<DiagnosisPanel assetId="RTU-2" />)

    const causeRow = await screen.findByTestId('cause-row')
    await waitFor(() => {
      expect(screen.getByText('72%')).toBeInTheDocument()
    })
    expect(causeRow.querySelector('.confidence-bar-fill')).not.toBeNull()
    expect(screen.queryByTestId('abstention-card')).toBeNull()
  })
})
