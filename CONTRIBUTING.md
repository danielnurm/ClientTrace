# Contributing

## Layout

| Part | Files |
|---|---|
| Search check (browser, phases, verdicts, survey, anonymisation) | `backend/leaks.py` |
| Finding the term in a request | `backend/payload.py` |
| Who a request goes to (tracker and company list) | `backend/trackers.py` |
| API | `api/main.py` |
| Web app | `web/` (design rules in `web/README.md`) |
| Fake pharmacy for tests and demos | `demo/search_site/server.py` |

## Data rules

- **Never commit a surveyed site's name.** Named results live only in `data/leaks/` (gitignored). The published
  `data/leaks_survey.json` is written by `anonymise()`. Before committing data, check that no domain or brand from
  `data/leaks/sites_named.json` appears in it (the anonymise test shows how).
- Wording describes what was observed ("sent the term to", "before the cookie banner was answered"), never
  legal conclusions.
- Live checks only from your own machine (`ALLOW_LIVE=1`), one site at a time, no more than three sites in parallel
  in a survey.

## Conventions

- Network calls always pass a `timeout=`. Failures are reported (status `error`, `blocked`), never retried around
  a bot wall.
- Modules import without side effects: no network or browser at import time.
- A new test counts only after it has been seen failing once on broken behaviour.
- English for code, comments and commit messages; Conventional Commits (`feat:`, `fix:`, `docs:`).

## Git workflow

- No direct pushes to `main`. Work on a branch and open a pull request; squash-merge when CI is green.
- Keep commits small, one change per commit.

## Testing

```bash
.venv/bin/python -m unittest discover -s tests -t .   # unit tests + the browser test against the fake pharmacy
cd web && npm run lint && npm run build
```

The browser test needs Playwright's Chromium (`.venv/bin/python -m playwright install chromium`); without it the
test is skipped locally, while CI sets `REQUIRE_BROWSER=1` so it must run there.
