/**
 * Diagnosis panel — ranked causes, abstentions, contradictions, and feedback.
 *
 * The abstention invariant lives in the types: an ``insufficient_evidence``
 * response has no confidence field (schemas.py, models.py check constraints),
 * and AbstentionCard renders exactly what the response carries — a
 * plain-language rationale and what would help. No confidence figure is ever
 * computed, formatted, or displayed for an abstention.
 */

import { useState } from 'react'
import { getDiagnosis, getTimeline, submitFeedback } from '../api/client'
import type {
  ContradictionPair,
  Diagnosis,
  FeedbackVerdict,
  RankedCause,
  TimelineEntry,
} from '../api/types'
import { useApiData } from '../api/useApiData'
import { formatRecordedAt } from '../lib/citations'
import { ErrorPanel, LoadingPanel } from './PanelStates'

function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`
}

function WorkOrderRef({ entry }: { entry: TimelineEntry }) {
  const workOrderId = entry.observation_id
  return (
    <a className="citation-link" href={`#work-order-${workOrderId}`} title="Cited work order">
      <span aria-hidden="true" className="citation-icon">
        §
      </span>{' '}
      {workOrderId}
    </a>
  )
}

function CauseRow({
  cause,
  citedEntries,
}: {
  cause: RankedCause
  citedEntries: Map<string, TimelineEntry>
}) {
  const [expanded, setExpanded] = useState(false)
  const cited = cause.observation_ids.flatMap((id) => {
    const entry = citedEntries.get(id)
    return entry ? [entry] : []
  })
  return (
    <li className="card cause-row" data-testid="cause-row">
      <div className="cause-row-head">
        <button
          type="button"
          className="cause-expand"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <span className="cause-label">{cause.label}</span>
          <span className="cause-caret" aria-hidden="true">
            {expanded ? '▾' : '▸'}
          </span>
        </button>
        <div
          className="confidence-bar"
          role="img"
          aria-label={`Confidence ${formatConfidence(cause.confidence)}`}
        >
          <div className="confidence-bar-fill" style={{ width: `${cause.confidence * 100}%` }} />
        </div>
        <span className="confidence-value">{formatConfidence(cause.confidence)}</span>
      </div>
      {expanded && (
        <div className="cause-detail">
          <p className="cause-evidence-count">
            {cause.observation_count} supporting work order{cause.observation_count === 1 ? '' : 's'}
          </p>
          <p className="cause-prior">{cause.prior_rationale}</p>
          {cause.evidence_spans.length > 0 && (
            <ul className="evidence-spans">
              {cause.evidence_spans.map((span) => (
                <li key={span}>“{span}”</li>
              ))}
            </ul>
          )}
          {cited.length > 0 ? (
            <div className="cited-work-orders">
              <p className="cited-heading">Cited work orders</p>
              <ul>
                {cited.map((entry) => (
                  <li key={entry.observation_id}>
                    <WorkOrderRef entry={entry} />
                    <span className="cited-text">{entry.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="cited-fallback">
              Cited records: {cause.source_refs.join(', ')}
            </p>
          )}
        </div>
      )}
    </li>
  )
}

function RankedCauses({
  causes,
  citedEntries,
}: {
  causes: RankedCause[]
  citedEntries: Map<string, TimelineEntry>
}) {
  return (
    <section aria-label="Ranked causes">
      <ol className="cause-list">
        {causes.map((cause) => (
          <CauseRow key={cause.cause} cause={cause} citedEntries={citedEntries} />
        ))}
      </ol>
    </section>
  )
}

/** The abstention card. Renders rationale + what would help — never a number. */
function AbstentionCard({ diagnosis }: { diagnosis: Extract<Diagnosis, { state: 'insufficient_evidence' }> }) {
  return (
    <section className="card abstention-card" data-testid="abstention-card" aria-live="polite">
      <h3 className="abstention-title">Not enough evidence to diagnose</h3>
      <p className="abstention-rationale">{diagnosis.rationale}</p>
      {diagnosis.what_would_help && (
        <p className="abstention-help">
          <strong>What would help:</strong> {diagnosis.what_would_help}
        </p>
      )}
    </section>
  )
}

function ClaimCard({
  side,
  observationId,
  sourceRef,
  field,
  quote,
  recordedAt,
}: {
  side: 'a' | 'b'
  observationId: string
  sourceRef: string
  field: string
  quote: string
  recordedAt: string
}) {
  return (
    <div className={`card claim-card claim-${side}`} data-testid={`claim-${side}`}>
      <p className="claim-field">{field}</p>
      <p className="claim-quote">“{quote}”</p>
      <p className="claim-meta">
        <a className="citation-link" href={`#work-order-${observationId}`} title={`Source record — ${sourceRef}`}>
          <span aria-hidden="true" className="citation-icon">
            §
          </span>{' '}
          {observationId}
        </a>
        <time dateTime={recordedAt}> · {formatRecordedAt(recordedAt)}</time>
      </p>
    </div>
  )
}

function ContradictionPairCard({ pair }: { pair: ContradictionPair }) {
  return (
    <div className="contradiction-pair" data-testid="contradiction-pair">
      <p className="contradiction-component">{pair.component}</p>
      <div className="contradiction-claims">
        <ClaimCard
          side="a"
          observationId={pair.claim_a.observation_id}
          sourceRef={pair.claim_a.source_ref}
          field={pair.claim_a.field}
          quote={pair.claim_a.quote}
          recordedAt={pair.claim_a.recorded_at}
        />
        <ClaimCard
          side="b"
          observationId={pair.claim_b.observation_id}
          sourceRef={pair.claim_b.source_ref}
          field={pair.claim_b.field}
          quote={pair.claim_b.quote}
          recordedAt={pair.claim_b.recorded_at}
        />
      </div>
    </div>
  )
}

function ContestedSection({ pairs }: { pairs: ContradictionPair[] }) {
  return (
    <section className="contested-section" aria-label="Contradicting observations">
      <h3 className="contested-title">Records contradict each other</h3>
      <p className="contested-hint">
        Both claims are shown with their sources — the evidence conflicts, and nothing here
        silently resolves it.
      </p>
      {pairs.map((pair) => (
        <ContradictionPairCard key={pair.component} pair={pair} />
      ))}
    </section>
  )
}

type FeedbackFormState =
  | { phase: 'idle' }
  | { phase: 'submitting' }
  | { phase: 'recorded'; verdict: FeedbackVerdict; responseId: number }
  | { phase: 'error'; message: string }

function FeedbackSection({ diagnosisId }: { diagnosisId: string }) {
  const [note, setNote] = useState('')
  const [correctedCause, setCorrectedCause] = useState('')
  const [pendingCorrection, setPendingCorrection] = useState(false)
  const [state, setState] = useState<FeedbackFormState>({ phase: 'idle' })

  const record = async (verdict: FeedbackVerdict, cause?: string): Promise<void> => {
    setState({ phase: 'submitting' })
    try {
      const response = await submitFeedback(diagnosisId, {
        verdict,
        correctedCause: cause,
        note: note.trim() || undefined,
      })
      setState({ phase: 'recorded', verdict: response.verdict as FeedbackVerdict, responseId: response.id })
    } catch (cause) {
      setState({ phase: 'error', message: String(cause) })
    }
  }

  const chooseVerdict = (verdict: FeedbackVerdict): void => {
    if (state.phase === 'submitting' || state.phase === 'recorded') return
    if (verdict === 'correct') {
      setPendingCorrection(true)
      return
    }
    void record(verdict)
  }

  if (state.phase === 'recorded') {
    return (
      <div className="feedback-recorded" data-testid="feedback-recorded">
        Verdict recorded: <strong>{state.verdict}</strong> (feedback #{state.responseId}). Thank
        you — your call is stored against this diagnosis.
      </div>
    )
  }

  return (
    <div className="feedback-section" data-testid="feedback-section">
      <p className="feedback-heading">Is this diagnosis right?</p>
      <div className="feedback-buttons">
        {(['confirm', 'correct', 'reject'] as const).map((verdict) => (
          <button
            key={verdict}
            type="button"
            className={`btn btn-verdict btn-${verdict}`}
            disabled={state.phase === 'submitting'}
            data-testid={`verdict-${verdict}`}
            onClick={() => chooseVerdict(verdict)}
          >
            {verdict === 'confirm' ? 'Confirm' : verdict === 'correct' ? 'Correct it' : 'Reject'}
          </button>
        ))}
      </div>
      {pendingCorrection && (
        <div className="correction-input">
          <label htmlFor="corrected-cause">What should the cause have been?</label>
          <input
            id="corrected-cause"
            type="text"
            value={correctedCause}
            onChange={(event) => setCorrectedCause(event.target.value)}
            placeholder="e.g. bearing_failure"
          />
          <button
            type="button"
            className="btn"
            disabled={correctedCause.trim() === '' || state.phase === 'submitting'}
            onClick={() => void record('correct', correctedCause.trim())}
          >
            Submit correction
          </button>
        </div>
      )}
      <label className="feedback-note-label" htmlFor="feedback-note">
        Note (optional)
      </label>
      <textarea
        id="feedback-note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="What a colleague would want to know"
      />
      {state.phase === 'error' && (
        <p className="feedback-error" role="alert">
          Could not record feedback: {state.message}
        </p>
      )}
    </div>
  )
}

export function DiagnosisPanel({ assetId }: { assetId: string }) {
  const diagnosisState = useApiData(() => getDiagnosis(assetId), [assetId])
  // Citations resolve against the timeline; a timeline failure must not block
  // the diagnosis — cited work orders degrade to their ids (partial state).
  const timelineState = useApiData(
    () => getTimeline(assetId).catch(() => null),
    [assetId],
  )

  if (diagnosisState.loading) return <LoadingPanel label="Loading diagnosis" />
  if (diagnosisState.error || diagnosisState.data === null) {
    return (
      <ErrorPanel
        message={diagnosisState.error ?? 'No diagnosis returned.'}
        onRetry={diagnosisState.retry}
      />
    )
  }

  const diagnosis: Diagnosis = diagnosisState.data
  const citedEntries = new Map(
    (timelineState.data?.entries ?? []).map((entry) => [entry.observation_id, entry]),
  )

  return (
    <div className="diagnosis-panel" data-testid="diagnosis-panel">
      <p className="diagnosis-as-of">
        Diagnosed as of {formatRecordedAt(diagnosis.as_of)} · diagnosis {diagnosis.diagnosis_id}
      </p>
      {diagnosis.state === 'ranked' && (
        <>
          <p className="diagnosis-rationale">{diagnosis.rationale}</p>
          <RankedCauses causes={diagnosis.causes} citedEntries={citedEntries} />
        </>
      )}
      {diagnosis.state === 'insufficient_evidence' && <AbstentionCard diagnosis={diagnosis} />}
      {diagnosis.state === 'contested' && (
        <>
          <ContestedSection pairs={diagnosis.contradictions} />
          <p className="diagnosis-rationale">{diagnosis.rationale}</p>
          <RankedCauses causes={diagnosis.causes} citedEntries={citedEntries} />
        </>
      )}
      <FeedbackSection key={diagnosis.diagnosis_id} diagnosisId={diagnosis.diagnosis_id} />
    </div>
  )
}
