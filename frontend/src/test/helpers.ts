/** Shared fetch-mock helper for component tests. */

import { vi } from 'vitest'

interface Route {
  pattern: RegExp
  body: unknown
}

const state: { routes: Route[]; calls: { url: string; init?: RequestInit }[] } = {
  routes: [],
  calls: [],
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: async () => body,
  } as unknown as Response
}

export const fetchMock = {
  install(): void {
    state.routes = []
    state.calls = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        state.calls.push({ url, init })
        const match = state.routes.find((route) => route.pattern.test(url))
        if (match) return jsonResponse(match.body)
        return jsonResponse({ detail: `no mock route matches ${url}` }, 404)
      }),
    )
  },
  uninstall(): void {
    vi.unstubAllGlobals()
  },
  route(pattern: RegExp, body: unknown): void {
    state.routes.push({ pattern, body })
  },
  callsTo(urlPattern: RegExp): { url: string; init?: RequestInit }[] {
    return state.calls.filter((call) => urlPattern.test(call.url))
  },
  /** The parsed JSON body sent to the first matching POST. */
  firstPostBody(urlPattern: RegExp): unknown {
    const call = state.calls.find(
      (candidate) => urlPattern.test(candidate.url) && candidate.init?.method === 'POST',
    )
    if (!call?.init?.body) throw new Error(`no POST captured for ${urlPattern}`)
    return JSON.parse(String(call.init.body))
  },
}
