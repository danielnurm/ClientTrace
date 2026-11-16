import type { Phase, SiteCheck } from './api'
import { counted, logLines, PHASE_PROBLEM, PHASES, phaseOf } from './search'

const SPAN_MS = 6000 // what the check records after the search starts (WAIT_MS in backend/leaks.py)
const PLAYBACK_MS = 3000 // the log replays those 6 s in 3 s

/** The search term marked inside a request, so the reader sees exactly where it travelled. */
export function Highlight({ text, term }: { text: string; term: string }) {
  const variants = [term, term.replace(/ /g, '-'), term.replace(/ /g, '+'), term.replace(/ /g, '%20')]
    .map((v) => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const parts = text.split(new RegExp(`(${variants.join('|')})`, 'i'))
  return (
    <>
      {parts.map((p, i) =>
        i % 2 ? (
          <mark key={i} className="rounded-[3px] bg-before/25 px-0.5 text-white">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  )
}

/** A dark network-panel window: one line per request that carried the term, arriving in real time order. */
export function NetworkLog({ phase, term, color, title }: { phase: Phase | undefined; term: string; color: string; title: string }) {
  const lines = logLines(phase)
  return (
    <div className="overflow-hidden rounded-2xl border border-rule-dark bg-panel text-left shadow-2xl shadow-black/40">
      <div className="flex items-center gap-3 border-b border-rule-dark px-4 py-3">
        <span className="flex gap-1.5" aria-hidden>
          <span className="size-3 rounded-full bg-[#ff5f57]" />
          <span className="size-3 rounded-full bg-[#febc2e]" />
          <span className="size-3 rounded-full bg-[#28c840]" />
        </span>
        <span className="truncate font-mono text-xs text-muted-dark">{title}</span>
      </div>
      {phase?.status !== 'ok' ? (
        <p className="px-4 py-6 font-mono text-sm text-muted-dark">{phase ? PHASE_PROBLEM[phase.status] : 'Not checked in this survey.'}</p>
      ) : lines.length === 0 ? (
        <p className="px-4 py-6 font-mono text-sm text-muted-dark">No other company received the term.</p>
      ) : (
        <ol className="divide-y divide-rule-dark font-mono text-[12.5px] leading-relaxed">
          {lines.map((l, i) => (
            <li
              key={i}
              className="arrive grid grid-cols-[4.2rem_1fr] gap-x-3 px-4 py-2.5 sm:grid-cols-[4.5rem_11rem_1fr]"
              style={{ animationDelay: `${(Math.min(l.ms, SPAN_MS) / SPAN_MS) * PLAYBACK_MS}ms` }}
            >
              <span className="tabular-nums text-muted-dark">{(l.ms / 1000).toFixed(3)}s</span>
              <span className="flex items-center gap-2 truncate font-semibold text-white">
                <span className="size-2 shrink-0 rounded-full" style={{ background: l.counted ? color : 'var(--color-weak)' }} />
                {l.who}
              </span>
              <span className="col-span-2 break-all text-[#d1d1d6] sm:col-span-1">
                <span className="text-muted-dark">{l.field}=</span>
                <Highlight text={l.snippet} term={term} />
                {l.own && <span className="ml-2 text-before">via the site’s own domain</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/** Timeline lanes: when each company received the term, per phase, from the moment the search started. */
export function Lanes({ check }: { check: SiteCheck }) {
  return (
    <div className="space-y-10">
      {PHASES.map(({ key, title, color }) => {
        const phase = phaseOf(check, key)
        if (!phase) return null
        return (
          <div key={key}>
            <h3 className="text-sm font-semibold text-white">{title}</h3>
            {phase.status !== 'ok' ? (
              <p className="mt-2 text-sm text-muted-dark">{PHASE_PROBLEM[phase.status]}</p>
            ) : phase.recipients.length === 0 ? (
              <p className="mt-2 text-sm text-muted-dark">No other company received the term.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {phase.recipients.map((r) => (
                  <li key={r.name} className="grid grid-cols-[8.5rem_1fr] items-center gap-3 sm:grid-cols-[12rem_1fr]">
                    <span className="truncate text-sm text-[#d1d1d6]" title={r.name}>{r.name}</span>
                    <svg viewBox="0 0 600 14" preserveAspectRatio="none" className="h-3.5 w-full" aria-label={`${r.name}: first at ${(r.first_ms / 1000).toFixed(1)} s`}>
                      <line x1="0" x2="600" y1="7" y2="7" stroke="var(--color-rule-dark)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
                      {[...new Set(r.evidence.map((e) => e.ms))].map((ms) => (
                        <rect key={ms} x={(Math.min(Math.max(ms, 0), SPAN_MS) / SPAN_MS) * 596} y="0" width="4" height="14" rx="2"
                          fill={counted(r) ? color : 'var(--color-weak)'} />
                      ))}
                    </svg>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
      <div className="grid grid-cols-[8.5rem_1fr] gap-3 sm:grid-cols-[12rem_1fr]" aria-hidden>
        <span />
        <div className="flex justify-between text-xs tabular-nums text-muted-dark">
          {[0, 1, 2, 3, 4, 5, 6].map((s) => <span key={s}>{s} s</span>)}
        </div>
      </div>
    </div>
  )
}
