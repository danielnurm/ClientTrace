import type { Lead, LeadStatus, TapeClass } from './api'

// Hottest first, the same order as backend/leads.py
export const STATUS_ORDER: LeadStatus[] = ['leaving', 'trialling', 'switched', 'weak', 'locked_in', 'unknown']

export function statusLabel(status: LeadStatus, competitor: string): string {
  return {
    leaving: `Leaving ${competitor}`,
    trialling: 'Trialling another chat',
    switched: 'Already switched',
    weak: 'Weak signal',
    locked_in: `Staying on ${competitor}`,
    unknown: "Can't tell",
  }[status]
}

export const STATUS_COLOR: Record<LeadStatus, string> = {
  leaving: 'var(--color-leaving)',
  trialling: 'var(--color-trialling)',
  switched: 'var(--color-switched)',
  weak: 'var(--color-weak)',
  locked_in: 'var(--color-locked)',
  unknown: 'var(--color-unknown)',
}

// Chat tape: the timeline was built for the competitor, so "ours" is the competitor (the incumbent).
export const TAPE: Record<TapeClass, { fill: string; hatch?: boolean; label: (c: string) => string }> = {
  ours_only: { fill: 'var(--color-tape-incumbent)', label: (c) => `${c} only` },
  both: { fill: 'var(--color-tape-overlap)', label: (c) => `${c} and another chat` },
  competitor_only: { fill: 'var(--color-tape-alternative)', label: () => 'Another chat only' },
  competitor_ours_hidden: {
    fill: 'var(--color-tape-alternative)',
    hatch: true,
    label: (c) => `Another chat, ${c} loaded out of sight`,
  },
  chat_hidden: { fill: 'var(--color-tape-hidden)', hatch: true, label: () => 'Chat loaded out of sight' },
  none_detected: { fill: 'var(--color-tape-none)', label: () => 'No chat found' },
  no_snapshot: { fill: 'transparent', label: () => 'Not archived' },
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2026-04-11" or "2026-04" → "Apr 2026" */
export function monthName(date: string | null | undefined): string | null {
  if (!date) return null
  const [y, m] = date.split('-')
  return `${MONTHS[Number(m) - 1]} ${y}`
}

/** A page path in words: "/" is the home page. */
export const pageName = (p: string) => (p === '/' ? 'the home page' : p)

/** When the alternative first showed up: live evidence first, then the archive. Only for leads that are moving. */
export function since(lead: Lead): string | null {
  if (!['leaving', 'trialling', 'switched'].includes(lead.status)) return null
  return monthName(lead.alternatives[0]?.since) ?? monthName(lead.timeline?.summary.first_competitor_seen)
}

/** One plain sentence for the seller: why this lead matters now. Built from the evidence only. */
export function whyNow(lead: Lead): string {
  const c = lead.competitor
  const alt = lead.alternatives[0]
  const pages = alt?.same_page.length ? ` on ${alt.same_page.map(pageName).join(' and ')}` : ''
  const when = since(lead) ? ` since ${since(lead)}` : ''
  switch (lead.status) {
    case 'leaving':
      return lead.dropped_since_last_check
        ? `${c} disappeared from the site since the last check, and ${alt?.name ?? 'another chat'} runs instead. The move is happening now.`
        : `${alt?.name} runs next to ${c}${pages}, and the ${alt?.in_privacy_policy ? 'privacy policy' : 'help centre'} already points to it. A move is under way.`
    case 'trialling':
      return `${alt?.name} runs next to ${c}${pages}${when}. They are comparing tools, so this is the moment to be in the conversation.`
    case 'switched':
      return `${c} is no longer on the site and ${alt?.name ?? 'another chat'} runs instead${when}. They picked a new tool; ask how the move went.`
    case 'weak':
      return `${alt?.name} appears only on other pages than ${c}, often another part of the business. Worth a look, not a call.`
    case 'locked_in':
      return lead.timeline?.summary.moving_to_us
        ? `${c} arrived in ${monthName(lead.timeline.summary.ours_first_seen)}. They chose it recently, so expect no change soon.`
        : `Only ${c} runs on the site. No sign of a change yet.`
    case 'unknown':
      return lead.error
        ? `The site couldn't be checked (${lead.error}).`
        : 'No chat tool is visible. It may load after cookie consent or behind a login, so check by hand.'
  }
}
