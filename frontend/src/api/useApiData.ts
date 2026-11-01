/** Fetch-one-endpoint hook with loading / error / retry states. */

import { useCallback, useEffect, useState } from 'react'

export interface ApiData<T> {
  data: T | null
  error: string | null
  loading: boolean
  /** Re-run the fetcher (e.g. after a failed request or stale data). */
  retry: () => void
}

export function useApiData<T>(fetcher: () => Promise<T>, deps: readonly unknown[]): ApiData<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)

  const retry = useCallback(() => setReloadToken((token) => token + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetcher()
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setLoading(false)
        }
      })
      .catch((cause: Error) => {
        if (!cancelled) {
          setError(cause.message)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the fetcher identity follows deps
  }, [...deps, reloadToken])

  return { data, error, loading, retry }
}
