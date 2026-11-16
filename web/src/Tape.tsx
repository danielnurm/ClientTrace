import type { Month, TapeClass } from './api'
import { monthName, TAPE } from './lib'

interface Props {
  months: Month[]
  competitor: string
  /** compact: the row strip in the lead list; full: the detail view with year marks */
  size?: 'compact' | 'full'
}

/** The chat tape: one cell per month showing which chat ran on the site, from the archive. */
export function Tape({ months, competitor, size = 'compact' }: Props) {
  const full = size === 'full'
  const cell = full ? 22 : 6
  const gap = full ? 2 : 1
  const height = full ? 40 : 14
  const width = months.length * (cell + gap) - gap
  const label = `${monthName(months[0]?.month)} to ${monthName(months.at(-1)?.month)}`

  return (
    <svg
      viewBox={`0 0 ${width} ${height + (full ? 20 : 0)}`}
      width={full ? '100%' : width}
      height={full ? undefined : height}
      role="img"
      aria-label={`Chat on the site each month, ${label}`}
      className="block overflow-visible"
    >
      <defs>
        <pattern id={`hatch-${size}`} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="4" height="4" fill="transparent" />
          <line x1="0" y1="0" x2="0" y2="4" stroke="white" strokeWidth="1.5" />
        </pattern>
      </defs>
      {months.map((m, i) => {
        const style = TAPE[m.class]
        const x = i * (cell + gap)
        return (
          <g key={m.month}>
            <title>{`${monthName(m.month)}: ${style.label(competitor)}${m.inferred ? ' (between archived snapshots)' : ''}`}</title>
            <rect
              x={x}
              y={0}
              width={cell}
              height={height}
              fill={style.fill}
              stroke={m.class === 'no_snapshot' ? 'var(--color-rule)' : 'none'}
              strokeDasharray={m.class === 'no_snapshot' ? '2 2' : undefined}
              opacity={m.inferred ? 0.75 : 1}
            />
            {style.hatch && <rect x={x} y={0} width={cell} height={height} fill={`url(#hatch-${size})`} />}
            {full && m.month.endsWith('-01') && (
              <text x={x} y={height + 15} fontSize="11" fill="var(--color-muted)">
                {m.month.slice(0, 4)}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

/** Legend for the classes that actually appear, in tape order. */
export function TapeLegend({ months, competitor }: { months: Month[]; competitor: string }) {
  const seen = [...new Set(months.map((m) => m.class))] as TapeClass[]
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
      {seen.map((cls) => (
        <li key={cls} className="flex items-center gap-2">
          <svg width="12" height="12" aria-hidden>
            <rect width="12" height="12" fill={TAPE[cls].fill} stroke={cls === 'no_snapshot' ? 'var(--color-rule)' : 'none'} />
            {TAPE[cls].hatch && <rect width="12" height="12" fill="url(#hatch-full)" />}
          </svg>
          {TAPE[cls].label(competitor)}
        </li>
      ))}
    </ul>
  )
}
