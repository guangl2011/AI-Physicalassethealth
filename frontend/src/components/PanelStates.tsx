/** Small shared UI states: loading, error, and empty. */

export function LoadingPanel({ label }: { label: string }) {
  return (
    <div className="card loading-panel" role="status" aria-live="polite">
      <div className="skeleton skeleton-line" />
      <div className="skeleton skeleton-line short" />
      <div className="skeleton skeleton-line" />
      <span className="visually-hidden">{label}</span>
    </div>
  )
}

export function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card error-panel" role="alert">
      <p>
        <strong>Could not load data.</strong> {message}
      </p>
      <button type="button" className="btn" onClick={onRetry}>
        Retry
      </button>
    </div>
  )
}

export function EmptyPanel({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="card empty-panel">
      <p className="empty-title">{title}</p>
      <p>{hint}</p>
    </div>
  )
}

