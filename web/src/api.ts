// Types and fetch helpers for the Firstbite API (api/main.py). The dev server proxies /api.

export type Verdict = 'sent_before_consent' | 'sent_after_reject' | 'sent_after_consent' | 'not_sent' | 'unknown'
export type PhaseStatus = 'ok' | 'blocked' | 'error' | 'no_search' | 'no_accept' | 'no_reject' | 'unstable'
export type PhaseKey = 'before' | 'reject' | 'after'

export interface Carrier {
  ms: number
  url: string
  field: string
  snippet: string
}

export interface Recipient {
  name: string
  category: string
  own_domain: boolean
  fields: string[]
  evidence: Carrier[]
  first_ms: number
}

export interface Phase {
  status: PhaseStatus
  searched?: 'url' | 'typed' | 'guessed'
  answered_via?: 'button' | 'text' | 'api'
  error?: string | null
  recipients: Recipient[]
  seen_once: string[]
}

export interface SiteCheck {
  site: string
  label?: string
  term: string
  country?: string
  kind?: 'pharmacy' | 'clinic'
  checked_at: string
  browser?: string
  before: Phase
  after: Phase
  reject?: Phase
  verdict: Verdict
}

export interface Company {
  name: string
  category: string
  before: number
  after: number
  reject?: number
  total: number
}

export interface Method {
  selection: string
  terms: string
  phases: string
  runs: number
  wait_ms: number
  checked_at: string
  browser?: string
  run_from?: string
  user_agent?: string
  answered_via?: string
  anonymised?: string
}

export interface Survey {
  method: Method
  summary: {
    sites: number
    verdicts: Partial<Record<Verdict, number>>
    own_domain: string[]
    companies: Company[]
    after_reject?: { checked: number; sent: number }
  }
  sites: SiteCheck[]
  demo: boolean
}

async function get<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(path)
  } catch {
    throw new Error('The Firstbite API is not running. Start it with: DEMO_MODE=1 uvicorn api.main:app --port 8000')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `The API answered ${res.status}.`)
  }
  return res.json() as Promise<T>
}

export const fetchSurvey = () => get<Survey>('/api/survey')
export const fetchSite = (site: string) => get<SiteCheck & { demo: boolean }>(`/api/site/${encodeURIComponent(site)}`)
