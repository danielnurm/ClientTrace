# ClientTrace web

React + TypeScript + Vite + Tailwind CSS v4 frontend for the lead API (`api/main.py`).

```bash
DEMO_MODE=1 .venv/bin/uvicorn api.main:app --port 8000   # from the repo root; saved data, no network
cd web && npm install && npm run dev                       # http://localhost:5173, proxies /api to :8000
npm run lint && npm run build                              # before every commit
```

## Design

A seller at a chat-software company wants one thing: which of a competitor's customers are changing their
chat right now, and the proof. The page is quiet so the proof stands out:

- **The chat tape** is the one bold element: one cell per month showing which chat ran on the site, from the
  web archive. Everything else is plain text, hairline rules and a single table.
- **Colours** (tokens in `src/index.css`): cool grey-blue paper, slate ink, one action blue for links and focus.
  Status and tape colours carry meaning only: red-orange leaving, amber trialling or overlap, slate switched,
  green staying.
- **Type:** Schibsted Grotesk, one family; tabular figures only where numbers line up.
- **Copy:** plain sentences from the evidence ("Salesforce chat runs next to Giosg on the home page since
  Apr 2026"). No LLM, so every sentence is traceable to a check.

## Rules (keep it from looking generated)

- No gradients, glass, emoji icons, shadows on cards, all-caps labels, "A · B · C" meta strings or "→" links.
- Real data from the API only; never placeholder content.
- A colour must mean something. Don't add one for decoration.
- Check every visual change with a screenshot at desktop and mobile width.
