import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { fetchLeads, type Lead, type LeadReport } from './api'
import { since, STATUS_COLOR, STATUS_ORDER, statusLabel } from './lib'
import { Problem, Shell, StatusMark } from './Shell'
import { Tape } from './Tape'

function headline(r: LeadReport): string {
  const n = (s: keyof LeadReport['summary']) => r.summary[s] ?? 0
  const moving = n('leaving') + n('trialling')
  const lead = moving === 1 ? '1 is changing its chat right now' : `${moving} are changing their chat right now`
  const switched = n('switched') ? `, and ${n('switched')} already switched` : ''
  return `Of ${r.leads.length} ${r.competitor} customers, ${lead}${switched}.`
}

function Row({ lead }: { lead: Lead }) {
  return (
    <li className="border-t border-rule first:border-t-0">
      <Link
        to={`/lead/${lead.site}`}
        className="grid grid-cols-[1fr_auto] items-center gap-x-6 gap-y-2 px-4 py-4 text-ink no-underline hover:bg-paper sm:grid-cols-[12rem_14rem_1fr_9rem_6rem] sm:px-5"
      >
        <span className="font-semibold">{lead.site}</span>
        <StatusMark status={lead.status} competitor={lead.competitor} />
        <span className="col-span-2 sm:col-span-1">
          {lead.timeline ? <Tape months={lead.timeline.months} competitor={lead.competitor} /> : <span className="text-sm text-muted">No archive</span>}
        </span>
        <span className="text-sm">{lead.switching_to ?? <span className="text-muted">–</span>}</span>
        <span className="text-sm text-muted tabular-nums sm:text-right">{since(lead) ?? '–'}</span>
      </Link>
    </li>
  )
}

export function Leads() {
  const [report, setReport] = useState<LeadReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchLeads().then(setReport, (e: Error) => setError(e.message))
  }, [])

  if (error) return <Shell demo={false}><Problem title="Couldn't load the leads" detail={error} /></Shell>
  if (!report) return <Shell demo={false}><p className="text-muted">Checking the sites…</p></Shell>

  const counts = STATUS_ORDER.filter((s) => report.summary[s])
  return (
    <Shell demo={report.demo}>
      <h1 className="max-w-[24ch] text-3xl font-semibold leading-tight tracking-tight sm:text-[2.6rem]">{headline(report)}</h1>
      <p className="mt-3 max-w-[60ch] text-muted">
        Checked on their own websites: which chat runs, on which pages, and what the web archive shows month by month.
        Open a site to see the proof.
      </p>

      <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Leads by status">
        {counts.map((s) => (
          <li key={s} className="flex items-center gap-2">
            <span className="size-2.5 rounded-full" style={{ background: STATUS_COLOR[s] }} />
            <span className="font-semibold tabular-nums">{report.summary[s]}</span>
            {statusLabel(s, report.competitor).replace(/^\w/, (c) => c.toLowerCase())}
          </li>
        ))}
      </ul>

      <section className="mt-5 rounded-md border border-rule bg-surface">
        <div className="hidden grid-cols-[12rem_14rem_1fr_9rem_6rem] gap-x-6 border-b border-rule px-5 py-2.5 text-sm text-muted sm:grid">
          <span>Site</span>
          <span>Status</span>
          <span>Chat on the site, last 3 years</span>
          <span>Switching to</span>
          <span className="text-right">Since</span>
        </div>
        <ol>
          {report.leads.map((l) => (
            <Row key={l.site} lead={l} />
          ))}
        </ol>
      </section>
    </Shell>
  )
}
