/**
 * Feedback contract: the verdict buttons issue the API call against
 * /diagnoses/{id}/feedback and the submitted state is reflected in the UI.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { DiagnosisPanel } from '../components/DiagnosisPanel'
import { fetchMock } from './helpers'

// FeedbackSection renders inside DiagnosisPanel, which fetches a diagnosis
// first. A ranked response keeps the test close to the happy path.
const rankedDiagnosis = {
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
      observation_ids: [],
      source_refs: ['work-order:WO-0100'],
      evidence_spans: [],
      prior_rationale: 'Compressor failures dominate this equipment class.',
    },
  ],
}

beforeEach(() => {
  fetchMock.install()
  fetchMock.route(/\/diagnosis$/, rankedDiagnosis)
  fetchMock.route(/\/timeline$/, { asset_id: 'RTU-2', entries: [] })
  fetchMock.route(/\/feedback$/, {
    id: 7,
    diagnosis_id: 'diag-456',
    verdict: 'confirm',
    corrected_cause: null,
    note: null,
    created_at: '2026-11-01T00:00:00',
  })
})

afterEach(() => {
  fetchMock.uninstall()
})

describe('DiagnosisPanel feedback', () => {
  it('posting confirm hits the feedback API and reflects the submitted state', async () => {
    const user = userEvent.setup()
    render(<DiagnosisPanel assetId="RTU-2" />)

    await screen.findByTestId('feedback-section')
    await user.type(screen.getByLabelText('Note (optional)'), 'Replaced unit last week.')
    await user.click(screen.getByTestId('verdict-confirm'))

    expect(fetchMock.firstPostBody(/\/diagnoses\/diag-456\/feedback$/)).toEqual({
      verdict: 'confirm',
      corrected_cause: null,
      note: 'Replaced unit last week.',
    })

    const recorded = await screen.findByTestId('feedback-recorded')
    expect(recorded).toHaveTextContent('Verdict recorded: confirm')
    expect(recorded).toHaveTextContent('feedback #7')
  })

  it('a correct verdict requires a corrected cause before submitting', async () => {
    const user = userEvent.setup()
    render(<DiagnosisPanel assetId="RTU-2" />)

    await screen.findByTestId('feedback-section')
    await user.click(screen.getByTestId('verdict-correct'))
    // No POST yet — a correction needs its cause.
    expect(fetchMock.callsTo(/\/feedback$/)).toHaveLength(0)
    await user.type(screen.getByLabelText('What should the cause have been?'), 'bearing_failure')
    await user.click(screen.getByRole('button', { name: 'Submit correction' }))

    expect(fetchMock.firstPostBody(/\/diagnoses\/diag-456\/feedback$/)).toEqual({
      verdict: 'correct',
      corrected_cause: 'bearing_failure',
      note: null,
    })
    expect(await screen.findByTestId('feedback-recorded')).toHaveTextContent('Verdict recorded:')
  })
})
