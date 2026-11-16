// Types and fetch helpers for the Firstbite API (api/main.py). The dev server proxies /api.

export type LeadStatus = 'leaving' | 'trialling' | 'switched' | 'weak' | 'locked_in' | 'unknown'

export type TapeClass =
  | 'ours_only'
  | 'both'
  | 'competitor_only'
  | 'competitor_ours_hidden'
  | 'chat_hidden'
  | 'none_detected'
  | 'no_snapshot'

export interface Alternative {
  name: string
  same_page: string[]
  other_pages: string[]
  in_privacy_policy: string | null
  help_centre: boolean
  since: string | null
}

export interface Snapshot {
  page: string
  date: string
  url: string
  products: string[]
}

export interface Month {
  month: string
  class: TapeClass
  vendors: string[]
  snapshots: Snapshot[]
  inferred: boolean
}

export interface Timeline {
  product: string
  months: Month[]
  summary: {
    first_competitor_seen: string | null
    ours_first_seen: string | null
    ours_last_seen: string | null
    moving_to_us: boolean
  }
}

export interface Lead {
  site: string
  url: string | null
  status: LeadStatus
  competitor: string
  competitor_running: boolean
  competitor_pages: string[]
  switching_to: string | null
  alternatives: Alternative[]
  dropped_since_last_check: boolean
  help_center: { platform: string; url: string } | null
  products: string[]
  timeline: Timeline | null
  error: string | null
}

export interface LeadReport {
  competitor: string
  checked_at: string
  summary: Partial<Record<LeadStatus, number>>
  leads: Lead[]
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

export const fetchLeads = () => get<LeadReport>('/api/leads')
export const fetchLead = (site: string) => get<Lead & { demo: boolean }>(`/api/leads/${encodeURIComponent(site)}`)

// Search check (backend/leaks.py): who receives what a visitor searches for

export type Verdict = 'sent_before_consent' | 'sent_after_consent' | 'not_sent' | 'unknown'
export type PhaseStatus = 'ok' | 'blocked' | 'error' | 'no_search' | 'no_accept' | 'unstable'

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
  error?: string | null
  recipients: Recipient[]
  seen_once: string[]
}

export interface SiteCheck {
  site: string
  term: string
  country?: string
  kind?: 'pharmacy' | 'clinic'
  checked_at: string
  before: Phase
  after: Phase
  verdict: Verdict
}

export interface Company {
  name: string
  category: string
  before: number
  after: number
  total: number
}

export interface Survey {
  method: { selection: string; terms: string; phases: string; runs: number; wait_ms: number; checked_at: string; regulators: Record<string, string> }
  summary: { sites: number; verdicts: Partial<Record<Verdict, number>>; own_domain: string[]; companies: Company[] }
  sites: SiteCheck[]
  demo: boolean
}

export const fetchSurvey = () => get<Survey>('/api/survey')
export const fetchSite = (site: string) => get<SiteCheck & { demo: boolean }>(`/api/site/${encodeURIComponent(site)}`)

export async function postCheck(site: string, term: string): Promise<SiteCheck> {
  const q = new URLSearchParams({ site, term })
  let res: Response
  try {
    res = await fetch(`/api/check?${q}`, { method: 'POST' })
  } catch {
    throw new Error('The Firstbite API is not running. Start it with: uvicorn api.main:app --port 8000')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `The API answered ${res.status}.`)
  }
  return res.json() as Promise<SiteCheck>
}
