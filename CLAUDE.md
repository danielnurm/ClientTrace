@README.md

# Instructions for Claude

The README above is the team contract. This file adds what Claude needs on top of it.
If anything here conflicts with the README, the README wins — ask the user.

## Hard rules
- Never push to `main`, merge PRs, force-push, or delete branches unless the user explicitly asks in this session.
- Never rename or change the signature/return format of the agreed functions in README.
  Need a change? Stop and tell the user to agree it with the team first.
- Only edit files owned by the user's role (see README "Roles"). Ask which role the user has
  if it isn't clear. Reading other roles' files is fine; editing them is not.
- Never put API keys, tokens or URLs with secrets in code, commits, logs or PR text. Read them
  from `.env` via `python-dotenv` (`os.getenv`). Never print or commit `.env`.
- Don't add dependencies without adding them to `requirements.txt` in the same commit, and mention it in the PR.

## Workflow
1. `git checkout main && git pull origin main`, then branch: `git checkout -b <role>-<topic>`.
2. Small, focused commits. One concern per commit.
3. Verify (see Testing) before committing.
4. Push with `git push -u origin <branch>` and open a PR to `main` — only when asked.

## Environment
- Python **3.9** (macOS system Python), venv at `.venv/`:
  `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Streamlit resolves to **1.50** on 3.9. Don't use APIs that only exist in newer Streamlit.
- Python 3.9 gotchas: no `X | None` in runtime-evaluated annotations (use `Optional[X]` or
  `from __future__ import annotations`), no `match` statements.
- Always run tools through the venv: `.venv/bin/python`, `.venv/bin/streamlit`.

## Architecture
```
app.py                     Streamlit entry: form (url, year) → run_analysis → render
frontend/data_source.py    run_analysis(): calls roles 1–3, falls back per step on failure
frontend/mock_data.py      demo customers (same format as README)
frontend/dashboard.py      render(data): metrics, chart, table
backend/context_api.py     role 1 – get_current_customers
backend/wayback.py         role 2 – get_historical_customers
analysis/comparison.py     role 3 – compare_customers
analysis/ai_analysis.py, analysis/customer_extraction.py, backend/competitor_search.py
                           no agreed interface yet — ask before wiring into the dashboard
```

## Code conventions
- Every customer is exactly `{"name", "logo_url", "source_url"}` (strings; `logo_url` may be `""`).
  Return `[]` for "found nothing" — not `None`, not an exception.
- Backend/analysis functions must be importable without side effects (no network calls or
  Streamlit calls at import time) and must not import `streamlit`.
- Network calls: always set a `timeout=`, and raise a clear exception on failure — the
  dashboard catches it and shows the reason.
- The dashboard must keep running when any role's function is missing, unfinished or fails.
  New integrations go through `_try()` in `frontend/data_source.py` with a demo fallback,
  and the fallback reason is shown in the "demo data" notes.
- Paid APIs (Context.dev) cost credits: don't call them in loops or tests; use mock data,
  and keep `@st.cache_data` on the analysis call.
- Match the surrounding style: short functions, brief comments, English identifiers.

## Testing
- Headless app check (no browser needed):
  ```python
  from streamlit.testing.v1 import AppTest
  at = AppTest.from_file("app.py", default_timeout=60).run()
  at.text_input[0].input("example.com"); at.button[0].click().run()
  assert not at.exception
  ```
- Backend/analysis: call the function directly from `.venv/bin/python` and check the
  output matches the customer format above.
- Manual: `.venv/bin/streamlit run app.py` → http://localhost:8501.
- Report results honestly: say what was run, what passed, and what still uses demo data.
