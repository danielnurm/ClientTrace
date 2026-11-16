import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { LeadStatus } from './api'
import { STATUS_COLOR, statusLabel } from './lib'

export function Shell({ demo, children }: { demo: boolean; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-[72rem] px-4 pb-16 sm:px-8">
      <header className="flex items-center justify-between gap-4 py-6">
        <Link to="/" className="flex items-center gap-2.5 font-semibold text-ink no-underline">
          <img src="/favicon.svg" alt="" className="size-6" />
          ClientTrace
        </Link>
        {demo && (
          <span className="rounded-sm border border-rule bg-surface px-2 py-1 text-xs text-muted" title="Served from a saved check (data/leads_demo.json)">
            Saved demo data
          </span>
        )}
      </header>
      <main>{children}</main>
    </div>
  )
}

export function StatusMark({ status, competitor }: { status: LeadStatus; competitor: string }) {
  return (
    <span className="flex items-center gap-2 text-sm font-medium" style={{ color: STATUS_COLOR[status] }}>
      <span className="size-2.5 shrink-0 rounded-full" style={{ background: STATUS_COLOR[status] }} />
      {statusLabel(status, competitor)}
    </span>
  )
}

export function Problem({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="max-w-[60ch] rounded-md border border-rule bg-surface p-6">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-muted">{detail}</p>
    </div>
  )
}
