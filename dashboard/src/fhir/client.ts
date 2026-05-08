// Generic FHIR client. Bearer auth via injected token-getter so the auth
// module owns token storage; this file owns network shape only.
//
// `searchAll` follows Bundle.link[rel=next] up to a soft cap so a runaway
// pagination loop on a buggy server doesn't melt the dashboard.

import type { Bundle, OperationOutcome } from './types'

const PAGINATION_CAP = 20 // pages, not entries

export class FhirError extends Error {
  status: number
  outcome?: OperationOutcome
  constructor(status: number, message: string, outcome?: OperationOutcome) {
    super(message)
    this.name = 'FhirError'
    this.status = status
    this.outcome = outcome
  }
}

export interface FhirClientOptions {
  baseUrl: string
  getAccessToken: () => string | null
  // Called on 401 so the auth layer can clear tokens and redirect to login.
  onAuthError?: () => void
  // Optional: rewrite a URL before fetch. Used in dev to redirect absolute
  // FHIR-server URLs (e.g. paginated Bundle.link.next) through the Vite
  // proxy when the browser can't reach the public FHIR server directly
  // (common on corporate networks with HTTPS interception).
  rewriteUrl?: (url: string) => string
}

export class FhirClient {
  private baseUrl: string
  private getAccessToken: () => string | null
  private onAuthError?: () => void
  private rewriteUrl?: (url: string) => string

  constructor(opts: FhirClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, '')
    this.getAccessToken = opts.getAccessToken
    this.onAuthError = opts.onAuthError
    this.rewriteUrl = opts.rewriteUrl
  }

  // GET an absolute or relative FHIR URL. Throws FhirError on non-2xx.
  async getUrl<T>(url: string): Promise<T> {
    const token = this.getAccessToken()
    const headers: Record<string, string> = {
      Accept: 'application/fhir+json',
    }
    if (token) headers.Authorization = `Bearer ${token}`

    const finalUrl = this.rewriteUrl ? this.rewriteUrl(url) : url
    const res = await fetch(finalUrl, { headers })
    if (res.status === 401) {
      this.onAuthError?.()
      throw new FhirError(401, 'Authentication failed or expired')
    }

    const text = await res.text()
    let body: unknown = null
    if (text) {
      try {
        body = JSON.parse(text)
      } catch {
        // FHIR servers should always return JSON; if not, surface raw text.
      }
    }

    if (!res.ok) {
      const outcome =
        body && typeof body === 'object' && (body as { resourceType?: string }).resourceType === 'OperationOutcome'
          ? (body as OperationOutcome)
          : undefined
      const detail =
        outcome?.issue?.[0]?.diagnostics ?? outcome?.issue?.[0]?.details?.text ?? text ?? `HTTP ${res.status}`
      throw new FhirError(res.status, detail, outcome)
    }

    return body as T
  }

  // GET a path relative to the FHIR base, with optional query params.
  async get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
    const url = this.buildUrl(path, params)
    return this.getUrl<T>(url)
  }

  // Search returning a single Bundle page. For "all results" use searchAll.
  async search<T>(
    resourceType: string,
    params?: Record<string, string | number | undefined>,
  ): Promise<Bundle<T>> {
    return this.get<Bundle<T>>(`/${resourceType}`, params)
  }

  // Search and follow Bundle.link[rel=next]. Returns flattened resources.
  async searchAll<T>(
    resourceType: string,
    params?: Record<string, string | number | undefined>,
  ): Promise<T[]> {
    const out: T[] = []
    let page: Bundle<T> = await this.search<T>(resourceType, params)
    let pages = 0
    while (true) {
      pages += 1
      for (const entry of page.entry ?? []) {
        if (entry.resource) out.push(entry.resource)
      }
      const nextLink = page.link?.find((l) => l.relation === 'next')?.url
      if (!nextLink || pages >= PAGINATION_CAP) break
      page = await this.getUrl<Bundle<T>>(nextLink)
    }
    return out
  }

  private buildUrl(path: string, params?: Record<string, string | number | undefined>): string {
    const cleanPath = path.startsWith('/') ? path : `/${path}`
    const fullPath = `${this.baseUrl}${cleanPath}`
    // Absolute (https://...) — URL constructor handles directly.
    // Relative (/fhir-api/...) — anchor against the current page origin so
    // the URL constructor can build a query string.
    const isAbsolute = /^https?:\/\//i.test(fullPath)
    const url = isAbsolute
      ? new URL(fullPath)
      : new URL(fullPath, window.location.origin)
    for (const [k, v] of Object.entries(params ?? {})) {
      if (v !== undefined && v !== '') url.searchParams.set(k, String(v))
    }
    // For a relative base, return path+query without the synthetic origin so
    // the browser fetches relative-to-current-origin (which is the dev server,
    // which proxies to the real FHIR server).
    if (!isAbsolute) {
      return `${url.pathname}${url.search}`
    }
    return url.toString()
  }
}
