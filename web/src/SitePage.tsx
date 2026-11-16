import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { fetchSite, type Recipient, type SiteCheck } from './api'
import { Highlight, Replay } from './Replay'
import { counted, finding, VERDICT_COLOR, VERDICT_LABEL } from './search'
import { Problem, Shell } from './Shell'

export function VerdictMark({ check }: { check: SiteCheck }) {
  const color = VERDICT_COLOR[check.verdict]
  return (
    <span className="flex items-center gap-2 text-sm font-medium" style={{ color }}>
      <span className="size-2.5 shrink-0 rounded-full" style={{ background: color }} />
      {VERDICT_LABEL[check.verdict]}
    </span>
  )
}

function Evidence({ r, term }: { r: Recipient; term: string }) {
  const e = r.evidence[0]
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-semibold">{r.name}</span>
        <span className="text-sm text-muted">{r.category}</span>
        {r.own_domain && <span className="text-sm font-medium text-before">through the site’s own domain</span>}
      </div>
      {e && (
        <>
          <p className="mt-1.5 break-all font-mono text-[13px] leading-relaxed">
            <span className="text-muted">{r.fields.join(', ')} = </span>
            <Highlight text={e.snippet} term={term} />
          </p>
          <p className="mt-1 break-all text-xs text-muted">
            {(e.ms / 1000).toFixed(1)} s after the search, to {e.url}
          </p>
        </>
      )}
    </li>
  )
}

/** Everything one check found: the sentence, the replay and the evidence behind it. Used by the site page and live check. */
export function SiteResult({ check }: { check: SiteCheck }) {
  const phases = [
    { key: 'before', title: 'Before you answer the cookie banner', phase: check.before },
    { key: 'after', title: 'After you accept cookies', phase: check.after },
  ] as const
  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-[2.6rem]">{check.site}</h1>
        <VerdictMark check={check} />
      </div>
      <p className="mt-4 max-w-[62ch] text-lg leading-relaxed">{finding(check)}</p>

      <section className="mt-10 rounded-md border border-rule bg-surface p-5 sm:p-6" aria-labelledby="replay-h">
        <h2 id="replay-h" className="font-semibold">Who received “{check.term}”, second by second</h2>
        <p className="mt-1 text-sm text-muted">
          Each mark is a request that carried the term, from the moment the search started. Counted only if it happened in both runs.
        </p>
        <div className="mt-6"><Replay check={check} /></div>
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {phases.map(({ key, title, phase }) => (
          <section key={key} className="rounded-md border border-rule bg-surface p-5 sm:p-6">
            <h2 className="font-semibold">{title}: the evidence</h2>
            {phase.status === 'ok' && phase.recipients.length ? (
              <ul className="mt-1 divide-y divide-rule">
                {[...phase.recipients].sort((a, b) => Number(counted(b)) - Number(counted(a))).map((r) => (
                  <Evidence key={r.name} r={r} term={check.term} />
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-muted">{phase.status === 'ok' ? 'Nothing carried the term.' : 'Not checked (see above).'}</p>
            )}
            {phase.seen_once.length > 0 && (
              <p className="mt-3 text-sm text-muted">Seen in only one run, not counted: {phase.seen_once.join(', ')}.</p>
            )}
          </section>
        ))}
      </div>
      <p className="mt-6 max-w-[70ch] text-sm text-muted">
        Checked {check.checked_at.slice(0, 10)} in a fresh browser with no cookies. Only a short window around the term is kept from each
        request, so no identifiers are stored. Something wrong? <a href="https://github.com/danielnurm/ClientTrace/issues">Open an issue</a>.
      </p>
    </>
  )
}

export function SitePage() {
  const { site = '' } = useParams()
  const [check, setCheck] = useState<(SiteCheck & { demo: boolean }) | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSite(site).then(setCheck, (e: Error) => setError(e.message))
  }, [site])

  if (error)
    return (
      <Shell demo={false}>
        <Problem title={`Couldn't load ${site}`} detail={error} />
        <p className="mt-4"><Link to="/">All sites</Link></p>
      </Shell>
    )
  if (!check) return <Shell demo={false}><p className="text-muted">Loading {site}…</p></Shell>
  return (
    <Shell demo={check.demo}>
      <p className="text-sm"><Link to="/">All sites</Link></p>
      <div className="mt-4"><SiteResult check={check} /></div>
    </Shell>
  )
}
