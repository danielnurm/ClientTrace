import { useState, type FormEvent } from 'react'
import { postCheck, type SiteCheck } from './api'
import { Shell } from './Shell'
import { SiteResult } from './SitePage'

/** Live check of any site: runs the same browser check as the survey (about a minute). */
export function Check() {
  const [site, setSite] = useState('')
  const [term, setTerm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SiteCheck | null>(null)

  function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    postCheck(site, term)
      .then(setResult, (err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <Shell demo={false}>
      <h1 className="text-3xl font-semibold tracking-tight sm:text-[2.4rem]">Check a site</h1>
      <p className="mt-3 max-w-[60ch] text-muted">
        We search the site for your term four times in a fresh browser, twice before and twice after accepting cookies, and show who
        receives it. It takes about a minute.
      </p>
      <form onSubmit={submit} className="mt-8 flex max-w-[44rem] flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex flex-1 flex-col gap-1.5 text-sm">
          Site
          <input
            required
            value={site}
            onChange={(e) => setSite(e.target.value)}
            placeholder="pharmacy.example"
            className="rounded-sm border border-rule bg-surface px-3 py-2 text-base"
          />
        </label>
        <label className="flex flex-1 flex-col gap-1.5 text-sm">
          Search for
          <input
            required
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="pregnancy test"
            className="rounded-sm border border-rule bg-surface px-3 py-2 text-base"
          />
        </label>
        <button type="submit" disabled={busy} className="rounded-sm bg-action px-4 py-2 font-medium text-white disabled:opacity-60">
          {busy ? 'Checking…' : 'Check'}
        </button>
      </form>
      {error && <p className="mt-6 max-w-[60ch] rounded-md border border-rule bg-surface p-4">{error}</p>}
      {result && <div className="mt-12"><SiteResult check={result} /></div>}
    </Shell>
  )
}
