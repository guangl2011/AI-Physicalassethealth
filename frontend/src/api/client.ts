/** Typed fetch wrappers over the FastAPI surface (insmart_api/api.py). */

import type {
  AssetSummary,
  Diagnosis,
  FeedbackResponse,
  FeedbackVerdict,
  Timeline,
} from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch (cause) {
    throw new ApiError(0, `network request failed: ${String(cause)}`)
  }
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: unknown } | null
    const message =
      typeof detail?.detail === 'string' ? detail.detail : `${response.status} ${response.statusText}`
    throw new ApiError(response.status, message)
  }
  return (await response.json()) as T
}

export function listAssets(): Promise<AssetSummary[]> {
  return request<AssetSummary[]>('/assets')
}

export function getTimeline(assetId: string): Promise<Timeline> {
  return request<Timeline>(`/assets/${encodeURIComponent(assetId)}/timeline`)
}

export function getDiagnosis(assetId: string): Promise<Diagnosis> {
  return request<Diagnosis>(`/assets/${encodeURIComponent(assetId)}/diagnosis`)
}

export interface FeedbackInput {
  verdict: FeedbackVerdict
  correctedCause?: string
  note?: string
}

export function submitFeedback(
  diagnosisId: string,
  input: FeedbackInput,
): Promise<FeedbackResponse> {
  return request<FeedbackResponse>(`/diagnoses/${encodeURIComponent(diagnosisId)}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      verdict: input.verdict,
      corrected_cause: input.correctedCause?.trim() || null,
      note: input.note?.trim() || null,
    }),
  })
}
