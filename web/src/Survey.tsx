import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { fetchSurvey, type SiteCheck, type Survey as SurveyData, type Verdict } from './api'
import { counted, VERDICT_COLOR, VERDICT_LABEL, VERDICT_ORDER } from './search'
import { Problem, Shell } from './Shell'
import { VerdictMark } from './SitePage'

const COUNTRY: Record<string, string> = { fi: 'Finland', se: 'Sweden', no: 'Norway', dk: 'Denmark', de: 'Germany', uk: 'UK' }

function headline(s: SurveyData): string {
  const checked = s.sites.filter((r) => r.verdict !== 'unknown').length
  const before = s.summary.verdicts.sent_before_consent ?? 0
  const sent = before + (s.summary.verdicts.sent_after_consent ?? 0)
  return `We searched ${checked} pharmacy and clinic sites for things like “pregnancy test”. ${sent} sent the search to ad or analytics companies, ${before} before the cookie banner was answered.`
}

function recipients(r: SiteCheck, phase: 'before' | 'after'): string {
  const p = r[phase]
  if (p.status !== 'ok') return ''
  return p.recipients.filter(counted).map((x) => x.name).join(', ')
}

function Row({ r }: { r: SiteCheck }) {
  const before = recipients(r, 'before')
  const after = recipients(r, 'after')
  return (
    <li className="border-t border-rule first:border-t-0">
      <Link
        to={`/site/${r.site}`}
        className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-1.5 px-4 py-4 text-ink no-underline hover:bg-paper sm:grid-cols-[13rem_15rem_1fr_1fr] sm:px-5"
      >
        <span>
          <span className="font-semibold">{r.site}</span>
          <span className="block text-sm text-muted">“{r.term}”</span>
        </span>
        <VerdictMark check={r} />
        <span className="col-span-2 text-sm sm:col-span-1">
          <span className="text-muted sm:hidden">Before consent: </span>
          {before || <span className="text-muted">–</span>}
        </span>
        <span className="col-span-2 text-sm sm:col-span-1">
          <span className="text-muted sm:hidden">After accepting: </span>
          {after || <span className="text-muted">–</span>}
        </span>
      </Link>
    </li>
  )
}

export function Survey() {
  const [survey, setSurvey] = useState<SurveyData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Verdict | 'all'>('all')

  useEffect(() => {
    fetchSurvey().then(setSurvey, (e: Error) => setError(e.message))
  }, [])

  if (error) return <Shell demo={false}><Problem title="Couldn't load the survey" detail={error} /></Shell>
  if (!survey) return <Shell demo={false}><p className="text-muted">Loading the survey…</p></Shell>

  const { summary, method } = survey
  const rows = survey.sites.filter((r) => filter === 'all' || r.verdict === filter)
  const companies = summary.companies.slice(0, 8)
  return (
    <Shell demo={survey.demo}>
      <h1 className="max-w-[30ch] text-3xl font-semibold leading-tight tracking-tight sm:text-[2.4rem]">{headline(survey)}</h1>
      <p className="mt-3 max-w-[64ch] text-muted">
        Each site was opened in a fresh browser and searched twice without touching the cookie banner, then twice after accepting it.
        We recorded every request that carried the search term. Site-search providers that need the term to work are shown but not counted.
        {summary.own_domain.length > 0 && ` On ${summary.own_domain.join(', ')}, part of it went through the site’s own domain, where cookie scanners and ad blockers don’t look.`}
      </p>

      <div className="mt-10 grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section>
          <div className="flex flex-wrap gap-2 text-sm" role="group" aria-label="Filter sites">
            {(['all', ...VERDICT_ORDER] as const).map((v) => {
              const n = v === 'all' ? survey.sites.length : summary.verdicts[v] ?? 0
              if (!n) return null
              const active = filter === v
              return (
                <button
                  key={v}
                  type="button"
                  onClick={() => setFilter(v)}
                  aria-pressed={active}
                  className={`flex items-center gap-2 rounded-sm border px-2.5 py-1 ${active ? 'border-ink bg-surface' : 'border-rule hover:border-muted'}`}
                >
                  {v !== 'all' && <span className="size-2 rounded-full" style={{ background: VERDICT_COLOR[v] }} />}
                  <span className="font-semibold tabular-nums">{n}</span>
                  {v === 'all' ? 'All sites' : VERDICT_LABEL[v].replace(/^\w/, (c) => c.toLowerCase())}
                </button>
              )
            })}
          </div>
          <div className="mt-4 rounded-md border border-rule bg-surface">
            <div className="hidden grid-cols-[13rem_15rem_1fr_1fr] gap-x-6 border-b border-rule px-5 py-2.5 text-sm text-muted sm:grid">
              <span>Site and search</span>
              <span>Result</span>
              <span>Before consent</span>
              <span>After accepting</span>
            </div>
            <ol>
              {rows.map((r) => (
                <Row key={r.site} r={r} />
              ))}
            </ol>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="rounded-md border border-rule bg-surface p-5">
            <h2 className="font-semibold">Who received the searches</h2>
            <ol className="mt-3 space-y-2.5">
              {companies.map((c) => (
                <li key={c.name} className="flex items-baseline justify-between gap-3">
                  <span>
                    {c.name}
                    <span className="block text-xs text-muted">{c.category}</span>
                  </span>
                  <span className="shrink-0 text-right text-sm tabular-nums">
                    {c.total} {c.total === 1 ? 'site' : 'sites'}
                    {c.before > 0 && <span className="block text-xs text-before">{c.before} before consent</span>}
                  </span>
                </li>
              ))}
            </ol>
          </section>
          <section className="rounded-md border border-rule bg-surface p-5 text-sm">
            <h2 className="font-semibold">How the sites were chosen</h2>
            <p className="mt-2 text-muted">{method.selection}</p>
            <p className="mt-2 text-muted">
              Countries: {[...new Set(survey.sites.map((s) => s.country).filter(Boolean))].map((c) => COUNTRY[c!] ?? c).join(', ')}. Checked{' '}
              {method.checked_at.slice(0, 10)}.
            </p>
            <p className="mt-3"><Link to="/check">Check another site</Link></p>
          </section>
        </aside>
      </div>
    </Shell>
  )
}
