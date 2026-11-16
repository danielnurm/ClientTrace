import { useEffect, useRef, type ReactNode } from 'react'
import { Link } from 'react-router'
import type { Verdict } from './api'
import { VERDICT_COLOR, VERDICT_LABEL } from './search'

export function Shell({ demo, children }: { demo: boolean; children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-black/10 bg-white/80 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex h-12 max-w-[64rem] items-center justify-between px-4 text-sm sm:px-6">
          <Link to="/" className="flex items-center gap-2 font-semibold text-ink hover:no-underline">
            <img src="/favicon.svg" alt="" className="size-5" />
            Firstbite
          </Link>
          {demo && (
            <span className="text-xs text-muted" title="The API runs with DEMO_MODE=1: saved results, no live checks">
              Saved survey
            </span>
          )}
        </div>
      </header>
      <main>{children}</main>
      <footer className="bg-light">
        <div className="mx-auto max-w-[64rem] border-t border-rule px-4 py-6 text-xs text-muted sm:px-6">
          Firstbite. Built at Junction 2026, MIT licensed.{' '}
          <a href="https://github.com/danielnurm/firstbite">Source on GitHub</a>
        </div>
      </footer>
    </div>
  )
}

/** A full-width section that fades up once when it scrolls into view. */
export function Reveal({ className = '', children }: { className?: string; children: ReactNode }) {
  const ref = useRef<HTMLElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          el.classList.add('is-in')
          io.disconnect()
        }
      },
      { threshold: 0.15 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <section ref={ref} className={`reveal ${className}`}>
      {children}
    </section>
  )
}

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-current/15 px-3 py-1 text-sm font-medium">
      <span className="size-2 shrink-0 rounded-full" style={{ background: VERDICT_COLOR[verdict] }} />
      {VERDICT_LABEL[verdict]}
    </span>
  )
}

export function Problem({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="mx-auto max-w-[40rem] px-4 py-24 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-3 text-muted">{detail}</p>
    </div>
  )
}
