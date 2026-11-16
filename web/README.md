# Firstbite web

React + TypeScript + Vite + Tailwind CSS v4 frontend for the API (`api/main.py`). Two pages: the survey
(`Survey.tsx`) and one site's replay (`SitePage.tsx`).

```bash
DEMO_MODE=1 .venv/bin/uvicorn api.main:app --port 8000   # from the repo root; saved data, no network
cd web && npm install && npm run dev                       # http://localhost:5173, proxies /api to :8000
npm run lint && npm run build                              # before every commit
```

## Design

An apple.com product page whose product shot is a security tool. The reader should get the finding in seconds
and then see the proof:

- **Structure:** full-width sections alternating white, light grey (`--color-light`) and black, centred
  headlines, generous whitespace, stat tiles with 28 px corners, and footnotes for the method and limits.
- **The bold element** is the network log (`NetworkLog` in `Replay.tsx`): a dark window where each request that
  carried the search term arrives in the order and (scaled) time it happened, the term highlighted.
- **Type:** the system stack, so Apple devices show SF Pro with no font download. Big, tight, semibold headlines
  (negative tracking). Every piece of evidence is mono (`ui-monospace`, SF Mono).
- **Colours carry meaning only** (Apple system colours, tokens in `src/index.css`): red sent before consent,
  pink sent after reject, orange sent after accept, green not sent, grey for companies that need the term or
  aren't identified. Everything else is black, white and grey. Links are Apple blue.
- **Motion:** sections fade up once on scroll (`Reveal`), log lines arrive in time order. Both are off under
  `prefers-reduced-motion`.
- **Copy:** plain sentences from the evidence ("A search for “raskaustesti” reached Google Analytics before the
  cookie banner was answered"). "Sent the term to", never "illegal". Sites are named by type and country only.

## Rules

- Real data from the API only, never placeholder content. No LLM text: every sentence traces to a check.
- No gradients, glass cards, emoji icons or decorative colour.
- Check every visual change with a screenshot at desktop and mobile width.
