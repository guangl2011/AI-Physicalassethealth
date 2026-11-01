/**
 * App shell — asset picker plus the three product views: timeline,
 * repeat-failure leaderboard, and diagnosis panel.
 */

import { useState } from 'react'
import { getTimeline, listAssets } from './api/client'
import { useApiData } from './api/useApiData'
import { DiagnosisPanel } from './components/DiagnosisPanel'
import { LeaderboardView } from './components/LeaderboardView'
import { TimelineView, type TimelineState } from './components/TimelineView'
import './App.css'

type ViewKey = 'timeline' | 'leaderboard' | 'diagnosis'

const VIEW_LABELS: Record<ViewKey, string> = {
  timeline: 'Timeline',
  leaderboard: 'Repeat failures',
  diagnosis: 'Diagnosis',
}

function AssetPicker({
  assets,
  selected,
  onSelect,
}: {
  assets: { asset_id: string; site_id: string; equipment_type: string }[]
  selected: string | null
  onSelect: (assetId: string) => void
}) {
  return (
    <label className="asset-picker">
      Asset
      <select
        value={selected ?? ''}
        onChange={(event) => onSelect(event.target.value)}
        aria-label="Select asset"
      >
        <option value="" disabled>
          Choose an asset…
        </option>
        {assets.map((asset) => (
          <option key={asset.asset_id} value={asset.asset_id}>
            {asset.asset_id} — {asset.equipment_type} · {asset.site_id}
          </option>
        ))}
      </select>
    </label>
  )
}

function TimelinePanel({ assetId }: { assetId: string }) {
  const { data, error, loading, retry } = useApiData(() => getTimeline(assetId), [assetId])

  const state: TimelineState = (() => {
    if (loading) return { phase: 'loading' }
    if (error || data === null)
      return { phase: 'error', message: error ?? 'No timeline returned.', retry }
    return { phase: 'ready', timeline: data.entries }
  })()

  return <TimelineView state={state} />
}

function App() {
  const assetsState = useApiData(() => listAssets(), [])
  const [view, setView] = useState<ViewKey>('leaderboard')
  const [assetId, setAssetId] = useState<string | null>(null)

  const selectAsset = (next: string): void => {
    setAssetId(next)
    // Arriving from the leaderboard means "show me this asset's history".
    if (view === 'leaderboard') setView('timeline')
  }

  const assets = assetsState.data ?? []
  const assetIsRegistered = assets.some((asset) => asset.asset_id === assetId)

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-title">
          <h1>Insmart AI</h1>
          <p>Asset health from the work orders you already have</p>
        </div>
        {assets.length > 0 && (
          <AssetPicker assets={assets} selected={assetId} onSelect={selectAsset} />
        )}
      </header>

      <nav className="view-tabs" aria-label="Views">
        {(Object.keys(VIEW_LABELS) as ViewKey[]).map((key) => (
          <button
            key={key}
            type="button"
            className={`view-tab ${view === key ? 'view-tab-active' : ''}`}
            aria-current={view === key ? 'page' : undefined}
            onClick={() => setView(key)}
          >
            {VIEW_LABELS[key]}
          </button>
        ))}
      </nav>

      <main className="app-main">
        {view === 'leaderboard' && <LeaderboardView onSelect={selectAsset} />}

        {view === 'timeline' && (
          <>
            {assetId === null ? (
              <p className="view-hint">Select an asset to see its cited work-order history.</p>
            ) : assets.length > 0 && !assetIsRegistered ? (
              <div className="card error-panel" role="alert">
                <p>
                  Asset {assetId} is not registered — pick one from the list above. The asset
                  detail pages navigate instead of showing a dead 404 banner.
                </p>
              </div>
            ) : (
              <TimelinePanel assetId={assetId} />
            )}
          </>
        )}

        {view === 'diagnosis' && (
          <>
            {assetId === null ? (
              <p className="view-hint">Select an asset to diagnose it from its records.</p>
            ) : assets.length > 0 && !assetIsRegistered ? (
              <div className="card error-panel" role="alert">
                <p>Asset {assetId} is not registered — pick one from the list above.</p>
              </div>
            ) : (
              <DiagnosisPanel assetId={assetId} />
            )}
          </>
        )}
      </main>
    </div>
  )
}

export default App
