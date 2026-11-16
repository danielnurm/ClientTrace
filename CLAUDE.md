@README.md
@CONTRIBUTING.md

# Instructions for Claude

CONTRIBUTING.md above is the team contract. This file adds what Claude needs on top of it.

## Hard rules
- Never push to `main`, merge PRs, force-push, or delete branches unless the user explicitly asks in this session.
- Never commit a surveyed site's name (see CONTRIBUTING.md "Data rules"); `data/leaks/` stays gitignored.
- Never point the browser at internal hosts: live checks go through `public_host()` in `api/main.py`.
- Never put secrets in code, commits, logs or PR text. Don't print or commit `.env`.
- Don't add dependencies without adding them to `requirements.txt` / `web/package.json` in the same commit.

## Environment
- Python 3.12, venv at `.venv/`: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`,
  then `.venv/bin/python -m playwright install chromium`.
- Always run tools through the venv: `.venv/bin/python`, `.venv/bin/uvicorn`.

## Commands
- Tests: `.venv/bin/python -m unittest discover -s tests -t .`
- Web: `cd web && npm run lint && npm run build`, plus a screenshot at desktop and mobile width for any UI change.
- Demo: `DEMO_MODE=1 .venv/bin/uvicorn api.main:app --port 8000` and `cd web && npm run dev`.
- One live check: `.venv/bin/python -m backend.leaks check <site> <term>`.
- Survey (live, ~30 min): `.venv/bin/python -m backend.leaks survey --refresh`.

## Gotchas
<!-- Same mistake twice: if a script can detect it, make it a check; otherwise add one line here. -->
