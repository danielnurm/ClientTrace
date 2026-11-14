# Contributing

## Roles

Each part has an owner. Ask the owner before changing their files.

1. Current customers (Context.dev) – `backend/context_api.py`
2. Historical customers (Wayback Machine) – `backend/wayback.py`
3. Comparison + AI – `analysis/`
4. Dashboard – `app.py`, `frontend/`

## Agreed functions

Do not change names or formats without asking the team first.

```python
# backend/context_api.py
get_current_customers(url: str) -> list[dict]

# backend/wayback.py
get_historical_customers(url: str, year: int) -> list[dict]

# analysis/comparison.py
compare_customers(old: list[dict], new: list[dict]) -> dict
# returns {"lost": [...], "retained": [...], "added": [...]}
```

`compare_customers` also accepts plain name lists and then returns names.

A customer always has this format:

```json
{"name": "Nokia", "logo_url": "https://...", "source_url": "https://..."}
```

`logo_url` can be an empty string if there's no logo.

## Conventions

- Return `[]` when nothing was found, not `None` and not an exception.
- Raise a clear exception when something actually fails (missing key, network
  error). The dashboard catches it and shows the reason.
- Always pass a `timeout=` to network calls.
- Modules must be importable without side effects: no network calls and no
  Streamlit calls at import time. Put demo code under
  `if __name__ == "__main__":`.
- Backend and analysis code doesn't import `streamlit`.
- Use English for code, comments and commit messages.

## Git workflow

- No direct pushes to `main`. Everyone works on their own branch.
- Run `git pull origin main` before you start working.
- When your part works, open a pull request. Someone takes a quick look, then
  merge.
- Keep commits small, one change per commit.

## API keys

API keys go only in `.env`, never in the code, commits or PR descriptions.
`.env` is in `.gitignore`. `.env.example` lists the variables without values.

If a key leaks, revoke it in the provider's dashboard right away and create a
new one.

## API usage

Context.dev, OpenAI and Exa cost credits.

- Don't call them in loops or automated tests. Use mock data or fake the API
  function in tests.
- Each new company costs 1-4 Context.dev requests. Results are cached in
  `data/current/`, so repeat runs are free.
- The competitor search (`backend/competitor_search.py`) makes about 7 requests
  per lost customer. Don't run it on long lists.
- `try_api.py`, `try_scrape.py` and `collect_data.py` call Context.dev every
  time they run. They're named so `pytest` won't pick them up. Keep new
  scripts like these out of `test_*.py`.

## Testing the dashboard

Run it headless without a browser:

```python
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py", default_timeout=60).run()
at.text_input[0].input("kone.com")
at.button[0].click().run()
assert not at.exception
```

`kone.com` / 2023 is cached, so this makes no API calls.
