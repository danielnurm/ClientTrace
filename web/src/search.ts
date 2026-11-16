import type { Phase, Recipient, SiteCheck, Verdict } from './api'

export const VERDICT_ORDER: Verdict[] = ['sent_before_consent', 'sent_after_consent', 'not_sent', 'unknown']

export const VERDICT_LABEL: Record<Verdict, string> = {
  sent_before_consent: 'Sent before consent',
  sent_after_consent: 'Sent after you accept',
  not_sent: 'Not sent to ad or analytics companies',
  unknown: "Couldn't check",
}

export const VERDICT_COLOR: Record<Verdict, string> = {
  sent_before_consent: 'var(--color-before)',
  sent_after_consent: 'var(--color-after)',
  not_sent: 'var(--color-not-sent)',
  unknown: 'var(--color-unknown)',
}

// The same split as SENSITIVE in backend/leaks.py: these don't need the term to run the search
const COUNTED = new Set(['advertising', 'analytics', 'session recording', 'marketing', 'personalisation'])
export const counted = (r: Recipient) => COUNTED.has(r.category)

export const PHASE_PROBLEM: Record<Exclude<Phase['status'], 'ok'>, string> = {
  blocked: 'The site showed our browser a bot check or a blank page instead of the shop.',
  error: "The site didn't load in our browser.",
  no_search: "We couldn't find the site's search.",
  no_accept: "We couldn't find the cookie banner's accept button.",
  unstable: 'The two runs disagreed, so nothing is counted.',
}

export function names(rs: Recipient[]): string {
  const n = rs.map((r) => r.name)
  return n.length <= 2 ? n.join(' and ') : `${n.slice(0, -1).join(', ')} and ${n[n.length - 1]}`
}

/** One plain sentence on what happened to the search term. */
export function finding(c: SiteCheck): string {
  const before = c.before.status === 'ok' ? c.before.recipients.filter(counted) : []
  const after = c.after.status === 'ok' ? c.after.recipients.filter(counted) : []
  const term = `“${c.term}”`
  if (c.verdict === 'sent_before_consent') {
    const own = before.some((r) => r.own_domain) ? ', partly through the site’s own domain,' : ''
    return `A search for ${term} reached ${names(before)}${own} before the cookie banner was answered.`
  }
  if (c.verdict === 'sent_after_consent') return `After accepting cookies, a search for ${term} reached ${names(after)}.`
  if (c.verdict === 'not_sent') return `A search for ${term} didn’t reach any ad or analytics company, before or after accepting cookies.`
  return `We couldn’t run the search on ${c.site}, so we can’t tell.`
}
