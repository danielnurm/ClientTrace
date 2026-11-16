import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { fetchSurvey, type SiteCheck, type Survey as SurveyData, type Verdict } from './api'
import { NetworkLog } from './Replay'
import { counted, logLines, siteName, VERDICT_COLOR, VERDICT_LABEL, VERDICT_ORDER } from './search'
import { Problem, Reveal, Shell } from './Shell'

const n = (s: SurveyData, v: Verdict) => s.summary.verdicts[v] ?? 0

/** The showcase: the site where the most ad or analytics companies got the term before consent. */
function worst(s: SurveyData): SiteCheck | undefined {
  const score = (r: SiteCheck) => (r.before.status === 'ok' ? r.before.recipients.filter(counted).length : 0)
  return s.sites.filter((r) => r.verdict === 'sent_before_consent').sort((a, b) => score(b) - score(a))[0]
}

function Hero({ s }: { s: SurveyData }) {
  const checked = s.sites.filter((r) => r.verdict !== 'unknown').length
  return (
    <Reveal className="px-4 pb-20 pt-20 text-center sm:pt-28">
      <p className="text-lg font-semibold text-before">Firstbite</p>
      <h1 className="mx-auto mt-3 max-w-[20ch] text-balance text-5xl font-semibold leading-[1.05] tracking-[-0.03em] sm:text-7xl">
        You searched for “pregnancy test”.
        <span className="block text-muted">It was sent before you said yes.</span>
      </h1>
      <p className="mx-auto mt-10 text-[5.5rem] font-semibold leading-none tracking-[-0.04em] tabular-nums sm:text-[8rem]">
        {n(s, 'sent_before_consent')}
        <span className="text-muted"> of {checked}</span>
      </p>
      <p className="mx-auto mt-4 max-w-[36rem] text-xl text-muted">
        pharmacy and clinic sites sent the search to ad or analytics companies before the cookie banner was answered.
      </p>
    </Reveal>
  )
}

function Showcase({ site, spanMs }: { site: SiteCheck; spanMs: number }) {
  const first = logLines(site.before).find((l) => l.counted)
  return (
    <Reveal className="dark bg-black px-4 py-24 text-white">
      <div className="mx-auto max-w-[56rem] text-center">
        <h2 className="text-4xl font-semibold tracking-[-0.02em] sm:text-6xl">Watch it happen.</h2>
        <p className="mx-auto mt-4 max-w-[38rem] text-lg text-muted-dark">
          {siteName(site)}. A search for “{site.term}” in a fresh browser, before touching the cookie banner.
          {first && ` ${first.who} had it ${(first.ms / 1000).toFixed(2)} seconds later.`}
        </p>
      </div>
      <div className="mx-auto mt-12 max-w-[56rem]">
        <NetworkLog phase={site.before} term={site.term} color="var(--color-before)" spanMs={spanMs}
          title={`Network · ${site.site}.example · search “${site.term}”`} />
      </div>
      <p className="mt-8 text-center text-lg">
        <Link to={`/site/${site.site}`}>See every phase for this site ›</Link>
      </p>
    </Reveal>
  )
}

function Tile({ value, of, color, children }: { value: number; of?: number; color: string; children: string }) {
  return (
    <div className="rounded-[28px] bg-white p-8">
      <p className="flex items-center gap-3 text-6xl font-semibold tracking-[-0.03em] tabular-nums">
        <span className="size-3 rounded-full" style={{ background: color }} />
        {value}
        {of !== undefined && <span className="text-3xl text-muted">of {of}</span>}
      </p>
      <p className="mt-3 text-lg leading-snug text-muted">{children}</p>
    </div>
  )
}

function Stats({ s }: { s: SurveyData }) {
  const reject = s.summary.after_reject
  const checked = s.sites.filter((r) => r.verdict !== 'unknown').length
  return (
    <Reveal className="bg-light px-4 py-24">
      <h2 className="mx-auto max-w-[56rem] text-center text-4xl font-semibold tracking-[-0.02em] sm:text-5xl">
        Saying no doesn’t always help.
      </h2>
      <div className="mx-auto mt-12 grid max-w-[64rem] gap-5 md:grid-cols-3">
        <Tile value={n(s, 'sent_before_consent')} of={checked} color="var(--color-before)">sites sent the search before the cookie banner was answered.</Tile>
        {reject?.checked ? (
          <Tile value={reject.sent} of={reject.checked} color="var(--color-reject)">sites still sent it after the visitor pressed reject.</Tile>
        ) : (
          <Tile value={n(s, 'sent_after_consent')} color="var(--color-after)">more sent it once the visitor accepted cookies.</Tile>
        )}
        <Tile value={s.summary.own_domain.length} color="var(--color-unknown)">
          routed part of it through their own domain, where ad blockers and cookie scanners don’t look.
        </Tile>
      </div>
    </Reveal>
  )
}

function Companies({ s }: { s: SurveyData }) {
  const top = s.summary.companies.slice(0, 8)
  const max = Math.max(...top.map((c) => c.total), 1)
  return (
    <Reveal className="px-4 py-24">
      <div className="mx-auto max-w-[48rem]">
        <h2 className="text-center text-4xl font-semibold tracking-[-0.02em] sm:text-5xl">Who receives it.</h2>
        <ol className="mt-12 space-y-5">
          {top.map((c) => (
            <li key={c.name}>
              <div className="flex items-baseline justify-between gap-4">
                <span className="font-semibold">{c.name} <span className="font-normal text-muted">· {c.category}</span></span>
                <span className="shrink-0 text-sm tabular-nums text-muted">{c.total} {c.total === 1 ? 'site' : 'sites'}</span>
              </div>
              <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-light" aria-hidden>
                <span style={{ width: `${(c.before / max) * 100}%`, background: 'var(--color-before)' }} />
                <span style={{ width: `${((c.total - c.before) / max) * 100}%`, background: 'var(--color-unknown)' }} />
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-6 flex justify-center gap-6 text-sm text-muted">
          <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-before" />before consent</span>
          <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-unknown" />only after answering the banner</span>
        </p>
      </div>
    </Reveal>
  )
}

function Sites({ s }: { s: SurveyData }) {
  const [filter, setFilter] = useState<Verdict | 'all'>('all')
  const rows = s.sites.filter((r) => filter === 'all' || r.verdict === filter)
  return (
    <Reveal className="bg-light px-4 py-24">
      <div className="mx-auto max-w-[56rem]">
        <h2 className="text-center text-4xl font-semibold tracking-[-0.02em] sm:text-5xl">Every site we checked.</h2>
        <p className="mx-auto mt-4 max-w-[36rem] text-center text-lg text-muted">
          Named by type and country on purpose: the point is the pattern, not one company.
        </p>
        <div className="mt-10 flex flex-wrap justify-center gap-2" role="group" aria-label="Filter sites">
          {(['all', ...VERDICT_ORDER] as const).map((v) => {
            const count = v === 'all' ? s.sites.length : n(s, v)
            if (!count) return null
            const active = filter === v
            return (
              <button key={v} type="button" onClick={() => setFilter(v)} aria-pressed={active}
                className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-sm transition-colors ${active ? 'bg-ink text-white' : 'bg-white text-ink hover:bg-white/60'}`}>
                {v !== 'all' && <span className="size-2 rounded-full" style={{ background: VERDICT_COLOR[v] }} />}
                {v === 'all' ? 'All' : VERDICT_LABEL[v]}
                <span className="tabular-nums opacity-60">{count}</span>
              </button>
            )
          })}
        </div>
        <ul className="mt-8 overflow-hidden rounded-[28px] bg-white">
          {rows.map((r) => (
            <li key={r.site} className="border-t border-rule first:border-t-0">
              <Link to={`/site/${r.site}`} className="flex items-center gap-4 px-6 py-4 text-ink hover:bg-light hover:no-underline">
                <span className="size-2.5 shrink-0 rounded-full" style={{ background: VERDICT_COLOR[r.verdict] }} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{siteName(r)}</span>
                  <span className="block truncate font-mono text-xs text-muted">“{r.term}”</span>
                </span>
                <span className="hidden text-sm text-muted sm:block">{VERDICT_LABEL[r.verdict]}</span>
                <span className="text-xl text-muted" aria-hidden>›</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </Reveal>
  )
}

function Footnotes({ s }: { s: SurveyData }) {
  const m = s.method
  const notes = [
    `Sites: ${m.selection}`,
    `Searches: ${m.terms}`,
    `Phases: ${m.phases} Each phase ran ${m.runs} times; a company counts only if it received the term in every run. Requests were recorded for ${m.wait_ms / 1000} s after the search started.`,
    m.answered_via,
    m.user_agent,
    `Browser: ${m.browser || 'headless Chromium'}. Run from: ${m.run_from || 'unknown'}. Checked ${m.checked_at.slice(0, 10)}.`,
    '“Sent” means the term appeared in a request to that company, decoded from the URL or body. Site-search, consent and chat tools that need the term to work are shown but not counted.',
    'Limits: what a company does after receiving the term isn’t visible. Data forwarded server to server beyond the site’s own domain, logged-in pages and other countries may differ. Results reflect one day.',
    m.anonymised,
  ].filter(Boolean)
  return (
    <section className="bg-light px-4 pb-16">
      <ol className="mx-auto max-w-[64rem] list-decimal space-y-2 border-t border-rule pl-8 pt-8 text-xs leading-relaxed text-muted">
        {notes.map((t, i) => <li key={i}>{t}</li>)}
      </ol>
    </section>
  )
}

export function Survey() {
  const [survey, setSurvey] = useState<SurveyData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSurvey().then(setSurvey, (e: Error) => setError(e.message))
  }, [])

  if (error) return <Shell demo={false}><Problem title="Couldn’t load the survey" detail={error} /></Shell>
  if (!survey) return <Shell demo={false}><p className="py-24 text-center text-muted">Loading…</p></Shell>
  const showcase = worst(survey)
  return (
    <Shell demo={survey.demo}>
      <Hero s={survey} />
      {showcase && <Showcase site={showcase} spanMs={survey.method.wait_ms} />}
      <Stats s={survey} />
      <Companies s={survey} />
      <Sites s={survey} />
      <Footnotes s={survey} />
    </Shell>
  )
}
