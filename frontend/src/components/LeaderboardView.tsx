/**
 * Repeat-failure leaderboard — assets ranked by recurrence count.
 *
 * The backend does not yet expose a leaderboard endpoint, so the view fetches
 * the asset list plus each asset's timeline and counts failure visits
 * client-side (see lib/recurrence.ts for the definition).
 */

import { useEffect, useState } from 'react'
import { getTimeline, listAssets } from '../api/client'
import type { TimelineEntry } from '../api/types'
import { rankByRecurrence, type LeaderboardRow } from '../lib/recurrence'
import { EmptyPanel, ErrorPanel, LoadingPanel } from './PanelStates'

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; rows: LeaderboardRow[]; totalAssets: number }

function useLeaderboard(reloadToken: number): LoadState {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })

  useEffect(() => {
    let cancelled = false
    const load = async (): Promise<void> => {
      setState({ phase: 'loading' })
      try {
        const assets = await listAssets()
        const timelines = await Promise.all(
          assets.map((asset) =>
            getTimeline(asset.asset_id).then((timeline) => [asset.asset_id, timeline.entries] as const),
          ),
        )
        if (cancelled) return
        const timelinesByAsset = new Map<string, TimelineEntry[]>(timelines)
        setState({
          phase: 'ready',
          rows: rankByRecurrence(assets, timelinesByAsset),
          totalAssets: assets.length,
        })
      } catch (cause) {
        if (!cancelled) setState({ phase: 'error', message: String(cause) })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [reloadToken])

  return state
}

function LeaderboardTable({
  rows,
  onSelect,
}: {
  rows: LeaderboardRow[]
  onSelect: (assetId: string) => void
}) {
  return (
    <table className="leaderboard-table" data-testid="leaderboard-table">
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">Asset</th>
          <th scope="col">Equipment</th>
          <th scope="col">Site</th>
          <th scope="col" className="numeric">
            Failure recurrences
          </th>
          <th scope="col" className="numeric">
            Work orders
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr
            key={row.assetId}
            onClick={() => onSelect(row.assetId)}
            className="leaderboard-row"
          >
            <td className="rank">{index + 1}</td>
            <td>
              <button
                type="button"
                className="link-button"
                onClick={(event) => {
                  event.stopPropagation()
                  onSelect(row.assetId)
                }}
              >
                {row.assetId}
              </button>
            </td>
            <td>{row.equipmentType}</td>
            <td>{row.siteId}</td>
            <td className="numeric">
              <span className="recurrence-count" data-testid="recurrence-count">
                {row.recurrenceCount}
              </span>
            </td>
            <td className="numeric">{row.workOrderCount}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function LeaderboardView({ onSelect }: { onSelect: (assetId: string) => void }) {
  const [reloadToken, setReloadToken] = useState(0)
  const state = useLeaderboard(reloadToken)
  const retry = () => setReloadToken((token) => token + 1)

  switch (state.phase) {
    case 'loading':
      return <LoadingPanel label="Loading leaderboard" />
    case 'error':
      return <ErrorPanel message={state.message} onRetry={retry} />
    case 'ready':
      if (state.totalAssets === 0) {
        return (
          <EmptyPanel
            title="No assets registered yet."
            hint="Register the asset inventory and upload a work-order export to rank failure recurrences."
          />
        )
      }
      return (
        <>
          <p className="view-hint">
            Ranked by work orders that recorded a defect finding — the repeat-failure problem
            behind every return visit. Select an asset to inspect its history.
          </p>
          <LeaderboardTable rows={state.rows} onSelect={onSelect} />
        </>
      )
  }
}
