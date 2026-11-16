import type { Phase, PhaseKey, Recipient, SiteCheck, Verdict } from './api'

export const VERDICT_ORDER: Verdict[] = ['sent_before_consent', 'sent_after_reject', 'sent_after_consent', 'not_sent', 'unknown']

export const VERDICT_LABEL: Record<Verdict, string> = {
  sent_before_consent: 'Sent before consent',
  sent_after_reject: 'Sent after you rejected',
  sent_after_consent: 'Sent after you accepted',
  not_sent: 'Not sent',
  unknown: "Couldn't check",
}

export const VERDICT_COLOR: Record<Verdict, string> = {
  sent_before_consent: 'var(--color-before)',
  sent_after_reject: 'var(--color-reject)',
  sent_after_consent: 'var(--color-after)',
  not_sent: 'var(--color-not-sent)',
  unknown: 'var(--color-unknown)',
}

/** The three moments a visitor can be in, worst first. Old survey rows have no reject phase. */
export const PHASES: { key: PhaseKey; title: string; color: string }[] = [
  { key: 'before', title: 'Before you answer the cookie banner', color: 'var(--color-before)' },
  { key: 'reject', title: 'After you reject cookies', color: 'var(--color-reject)' },
  { key: 'after', title: 'After you accept cookies', color: 'var(--color-after)' },
]

export const phaseOf = (c: SiteCheck, key: PhaseKey): Phase | undefined => c[key]

// The backend marks each recipient (leaks.SENSITIVE); this list is only the fallback for data saved before that
const COUNTED = new Set(['advertising', 'analytics', 'session recording', 'marketing', 'personalisation'])
export const counted = (r: Recipient) => r.counted ?? COUNTED.has(r.category)

export const PHASE_PROBLEM: Record<Exclude<Phase['status'], 'ok'>, string> = {
  blocked: 'The site showed our browser a bot check or a blank page instead of the shop.',
  error: "The site didn't load in our browser.",
  no_search: "We couldn't find the site's search.",
  no_accept: "We couldn't find the cookie banner's accept button.",
  no_reject: "We couldn't find a reject button on the cookie banner.",
  unstable: 'The two runs disagreed, so nothing is counted.',
}

export const siteName = (c: SiteCheck) => c.label ?? c.site

export function names(rs: Recipient[]): string {
  const n = rs.map((r) => r.name)
  return n.length <= 2 ? n.join(' and ') : `${n.slice(0, -1).join(', ')} and ${n[n.length - 1]}`
}

const sent = (p: Phase | undefined) => (p?.status === 'ok' ? p.recipients.filter(counted) : [])

/** One plain sentence on what happened to the search term. */
export function finding(c: SiteCheck): string {
  const term = `“${c.term}”`
  switch (c.verdict) {
    case 'sent_before_consent': {
      const own = sent(c.before).some((r) => r.own_domain) ? ', partly through the site’s own domain,' : ''
      return `A search for ${term} reached ${names(sent(c.before))}${own} before the cookie banner was answered.`
    }
    case 'sent_after_reject':
      return `Even after rejecting cookies, a search for ${term} reached ${names(sent(c.reject))}.`
    case 'sent_after_consent':
      return `After accepting cookies, a search for ${term} reached ${names(sent(c.after))}.`
    case 'not_sent':
      return `A search for ${term} didn’t reach any ad or analytics company.`
    default:
      return 'We couldn’t run the search on this site, so we can’t tell.'
  }
}

/** Every request that carried the term in one phase, as log lines in time order. */
export function logLines(p: Phase | undefined) {
  if (p?.status !== 'ok') return []
  return p.recipients
    .flatMap((r) => r.evidence.map((e) => ({ ...e, who: r.name, counted: counted(r), own: r.own_domain })))
    .sort((a, b) => a.ms - b.ms)
}
