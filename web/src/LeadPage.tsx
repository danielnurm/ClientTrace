import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { fetchLead, type Lead, type Month } from './api'
import { monthName, pageName, whyNow } from './lib'
import { Problem, Shell, StatusMark } from './Shell'
import { Tape, TapeLegend } from './Tape'

/** The archived pages behind the tape, newest first, so every claim can be checked. */
function archiveLinks(months: Month[]) {
  return months.flatMap((m) => m.snapshots).reverse().slice(0, 6)
}

function Evidence({ lead }: { lead: Lead }) {
  const items: { text: string; href?: string }[] = []
  if (lead.competitor_running)
    items.push({ text: `${lead.competitor} runs on ${lead.competitor_pages.map(pageName).join(' and ') || 'the site'}`, href: lead.url ?? undefined })
  else items.push({ text: `${lead.competitor} is not on the site any more`, href: lead.url ?? undefined })
  for (const a of lead.alternatives) {
    if (a.same_page.length) items.push({ text: `${a.name} on the same pages: ${a.same_page.map(pageName).join(', ')}` })
    if (a.other_pages.length) items.push({ text: `${a.name} on other pages: ${a.other_pages.map(pageName).join(', ')}` })
    if (a.in_privacy_policy) items.push({ text: `The privacy policy names ${a.name}`, href: a.in_privacy_policy })
    if (a.help_centre) items.push({ text: `The help centre runs on ${a.name}`, href: lead.help_center?.url })
    if (a.since) items.push({ text: `${a.name} first seen in the archive in ${monthName(a.since)}` })
  }
  return (
    <ul className="divide-y divide-rule">
      {items.map((i) => (
        <li key={i.text} className="py-2.5">
          {i.href ? <a href={i.href}>{i.text}</a> : i.text}
        </li>
      ))}
    </ul>
  )
}

export function LeadPage() {
  const { site = '' } = useParams()
  const [lead, setLead] = useState<(Lead & { demo: boolean }) | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchLead(site).then(setLead, (e: Error) => setError(e.message))
  }, [site])

  if (error)
    return (
      <Shell demo={false}>
        <Problem title={`Couldn't load ${site}`} detail={error} />
        <p className="mt-4"><Link to="/">Back to all leads</Link></p>
      </Shell>
    )
  if (!lead) return <Shell demo={false}><p className="text-muted">Checking {site}…</p></Shell>

  const months = lead.timeline?.months ?? []
  return (
    <Shell demo={lead.demo}>
      <p className="text-sm"><Link to="/">All leads</Link></p>
      <div className="mt-4 flex flex-wrap items-baseline gap-x-5 gap-y-2">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-[2.6rem]">{lead.site}</h1>
        <StatusMark status={lead.status} competitor={lead.competitor} />
      </div>
      <p className="mt-4 max-w-[62ch] text-lg leading-relaxed">{whyNow(lead)}</p>

      <section className="mt-10 rounded-md border border-rule bg-surface p-5 sm:p-6" aria-labelledby="tape-h">
        <h2 id="tape-h" className="font-semibold">Chat on the site, month by month</h2>
        <p className="mt-1 text-sm text-muted">From the web archive. Hover a month for details; lighter months fall between archived snapshots.</p>
        {months.length ? (
          <>
            <div className="mt-5 overflow-x-auto pb-1">
              <div className="min-w-[44rem]">
                <Tape months={months} competitor={lead.competitor} size="full" />
              </div>
            </div>
            <div className="mt-4">
              <TapeLegend months={months} competitor={lead.competitor} />
            </div>
          </>
        ) : (
          <p className="mt-4 text-muted">This site has no archive history yet.</p>
        )}
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-md border border-rule bg-surface p-5 sm:p-6">
          <h2 className="font-semibold">What the live check found</h2>
          <div className="mt-2"><Evidence lead={lead} /></div>
        </section>
        <section className="rounded-md border border-rule bg-surface p-5 sm:p-6">
          <h2 className="font-semibold">Archived pages behind the timeline</h2>
          <ul className="mt-2 divide-y divide-rule">
            {archiveLinks(months).map((s) => (
              <li key={s.url} className="flex justify-between gap-4 py-2.5">
                <a href={s.url}>{s.page === '/' ? 'Home page' : s.page}</a>
                <span className="shrink-0 text-sm text-muted tabular-nums">{s.date}</span>
              </li>
            ))}
            {!archiveLinks(months).length && <li className="py-2.5 text-muted">No archived pages.</li>}
          </ul>
        </section>
      </div>
    </Shell>
  )
}
