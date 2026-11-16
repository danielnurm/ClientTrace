import type { Phase, Recipient, SiteCheck } from './api'
import { counted, PHASE_PROBLEM } from './search'

const SPAN_MS = 6000 // what the check records after the search starts (WAIT_MS in backend/leaks.py)

function Lane({ r, color }: { r: Recipient; color: string }) {
  const fill = counted(r) ? color : 'var(--color-weak)'
  const times = [...new Set(r.evidence.map((e) => e.ms))]
  return (
    <li className="grid grid-cols-[9rem_1fr] items-center gap-3 sm:grid-cols-[12rem_1fr]">
      <span className="truncate text-sm" title={r.name}>
        {r.name}
      </span>
      <svg viewBox="0 0 600 16" preserveAspectRatio="none" className="h-4 w-full" aria-label={`${r.name}: first at ${(r.first_ms / 1000).toFixed(1)} s`}>
        <line x1="0" x2="600" y1="8" y2="8" stroke="var(--color-rule)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        {times.map((ms) => (
          <rect key={ms} x={Math.min(Math.max(ms, 0), SPAN_MS) / SPAN_MS * 596} y="1" width="4" height="14" rx="1" fill={fill} />
        ))}
      </svg>
    </li>
  )
}

function Axis() {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-3 sm:grid-cols-[12rem_1fr]" aria-hidden>
      <span />
      <div className="flex justify-between text-xs text-muted tabular-nums">
        {[0, 1, 2, 3, 4, 5, 6].map((s) => (
          <span key={s}>{s} s</span>
        ))}
      </div>
    </div>
  )
}

function Strip({ title, phase, color }: { title: string; phase: Phase; color: string }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      {phase.status !== 'ok' ? (
        <p className="mt-2 text-sm text-muted">{PHASE_PROBLEM[phase.status]}</p>
      ) : phase.recipients.length ? (
        <>
          <ul className="mt-3 space-y-2">
            {phase.recipients.map((r) => (
              <Lane key={r.name} r={r} color={color} />
            ))}
          </ul>
          <div className="mt-2"><Axis /></div>
        </>
      ) : (
        <p className="mt-2 text-sm text-muted">No other company received the term.</p>
      )}
    </div>
  )
}

/** Two strips from the moment the search starts: before the banner is answered, and after accepting it. */
export function Replay({ check }: { check: SiteCheck }) {
  return (
    <div className="space-y-8">
      <Strip title="Before you answer the cookie banner" phase={check.before} color="var(--color-before)" />
      <Strip title="After you accept cookies" phase={check.after} color="var(--color-after)" />
      <p className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5"><span className="h-3 w-1 rounded-[1px] bg-before" />Ad or analytics company, before consent</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-1 rounded-[1px] bg-after" />Ad or analytics company, after accepting</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-1 rounded-[1px] bg-weak" />Needed for the search, or not identified</span>
      </p>
    </div>
  )
}

/** The snippet with the term marked, so the reader sees exactly where it travelled. */
export function Highlight({ text, term }: { text: string; term: string }) {
  const variants = [term, term.replace(/ /g, '-'), term.replace(/ /g, '+')].map((v) => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const parts = text.split(new RegExp(`(${variants.join('|')})`, 'i'))
  return (
    <>
      {parts.map((p, i) =>
        i % 2 ? <mark key={i} className="rounded-[2px] bg-term px-0.5 text-ink">{p}</mark> : <span key={i}>{p}</span>,
      )}
    </>
  )
}
