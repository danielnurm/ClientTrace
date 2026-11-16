# Firstbite web

React + TypeScript + Vite + Tailwind CSS v4 frontend for the API (`api/main.py`).

```bash
DEMO_MODE=1 .venv/bin/uvicorn api.main:app --port 8000   # from the repo root; saved data, no network
cd web && npm install && npm run dev                       # http://localhost:5173, proxies /api to :8000
npm run lint && npm run build                              # before every commit
```

## Design

A reader wants one thing: who received what I searched for on this site, and the proof. The page is quiet so the
proof stands out:

- **The search replay** (`Replay.tsx`) is the one bold element on a site page: one lane per company, a mark for
  every request that carried the term, 0 to 6 s after the search, before and after accepting cookies. The
  evidence below it shows the exact field with the term highlighted. Everything else is plain text, hairline
  rules and a single table.
- The original sales-lead views (`/leads`, with **the chat tape** as their bold element) are kept out of the
  main navigation.
- **Colours** (tokens in `src/index.css`): cool grey-blue paper, slate ink, one action blue for links and focus.
  Search-check colours carry meaning only: red-orange sent before consent, amber sent after accepting, green
  not sent, grey needed for the search or not identified. Lead and tape colours as before.
- **Type:** Schibsted Grotesk, one family; tabular figures only where numbers line up.
- **Copy:** plain sentences from the evidence ("A search for “raskaustesti” reached Google Analytics before the
  cookie banner was answered"). "Sent the term to", never "illegal". No LLM, so every sentence is traceable to
  a check.

## Rules (keep it from looking generated)

- No gradients, glass, emoji icons, shadows on cards, all-caps labels, "A · B · C" meta strings or "→" links.
- Real data from the API only; never placeholder content.
- A colour must mean something. Don't add one for decoration.
- Check every visual change with a screenshot at desktop and mobile width.
