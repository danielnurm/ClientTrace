import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { fetchSite, type SiteCheck } from './api'
import { Lanes, NetworkLog } from './Replay'
import { finding, PHASES, phaseOf, siteName } from './search'
import { Problem, Reveal, Shell, VerdictPill } from './Shell'

const ANSWERED = {
  button: 'the consent tool’s own button',
  text: 'a button found by its label',
  api: 'the consent tool’s own JavaScript call (no button could be clicked)',
}

export function SitePage() {
  const { site = '' } = useParams()
  const [check, setCheck] = useState<(SiteCheck & { demo: boolean }) | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSite(site).then(setCheck, (e: Error) => setError(e.message))
  }, [site])

  if (error) return <Shell demo={false}><Problem title="Couldn’t load this site" detail={error} /></Shell>
  if (!check) return <Shell demo={false}><p className="py-24 text-center text-muted">Loading…</p></Shell>
  const phases = PHASES.filter(({ key }) => phaseOf(check, key))
  return (
    <Shell demo={check.demo}>
      <Reveal className="px-4 pb-16 pt-14 text-center sm:pt-20">
        <p className="text-sm"><Link to="/">‹ All sites</Link></p>
        <p className="mt-8 font-mono text-sm text-muted">search: “{check.term}”</p>
        <h1 className="mx-auto mt-3 max-w-[20ch] text-4xl font-semibold leading-tight tracking-[-0.03em] sm:text-6xl">{siteName(check)}</h1>
        <div className="mt-6"><VerdictPill verdict={check.verdict} /></div>
        <p className="mx-auto mt-6 max-w-[40rem] text-xl leading-relaxed text-muted">{finding(check)}</p>
      </Reveal>

      <Reveal className="dark bg-black px-4 py-20 text-white">
        <div className="mx-auto max-w-[56rem]">
          <h2 className="text-3xl font-semibold tracking-[-0.02em] sm:text-4xl">Second by second.</h2>
          <p className="mt-3 max-w-[40rem] text-muted-dark">
            Each mark is a request that carried the term, from the moment the search started. Counted only if it happened in every run.
          </p>
          <div className="mt-10"><Lanes check={check} /></div>
        </div>
      </Reveal>

      <section className="dark bg-black px-4 pb-24 text-white">
        <div className="mx-auto max-w-[56rem] space-y-8">
          <h2 className="text-3xl font-semibold tracking-[-0.02em] sm:text-4xl">The evidence.</h2>
          {phases.map(({ key, title, color }) => {
            const phase = phaseOf(check, key)
            return (
              <Reveal key={key}>
                <NetworkLog phase={phase} term={check.term} color={color} title={title} />
                {phase && phase.seen_once.length > 0 && (
                  <p className="mt-2 text-sm text-muted-dark">Seen in only one run, not counted: {phase.seen_once.join(', ')}.</p>
                )}
                {phase?.answered_via && (
                  <p className="mt-2 text-sm text-muted-dark">Banner answered with {ANSWERED[phase.answered_via]}.</p>
                )}
              </Reveal>
            )
          })}
        </div>
      </section>

      <section className="bg-light px-4 py-8">
        <p className="mx-auto max-w-[56rem] text-xs leading-relaxed text-muted">
          Checked {check.checked_at.slice(0, 10)}{check.browser && ` in ${check.browser}`}, a fresh browser with no cookies for every run.
          Only a short window around the term is kept from each request; identifiers are masked. The site is anonymised on purpose.
        </p>
      </section>
    </Shell>
  )
}
