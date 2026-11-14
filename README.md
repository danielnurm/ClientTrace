# ClientTrace

See which customers a company has quietly stopped showing on its website.

Give ClientTrace a company URL and a year. It reads the company's customer or
reference page as it is today, finds the same page in the Wayback Machine for
that year, and shows which customers have disappeared, which are still listed
and which are new.

A missing logo is not proof that a customer left. Sites get redesigned and case
studies get rotated out. Treat the results as leads to look into, not as facts.

## How it works

1. **Current customers.** The site's customer page (`/customers`, `/references`,
   `/case-studies`, ...) is scraped with Context.dev.
   See `backend/context_api.py`.
2. **Historical customers.** The same page is looked up in the Wayback Machine
   for the chosen year. See `backend/wayback.py`.
3. **Comparison.** Names are normalized (legal suffixes like Oy/Inc, accents,
   small spelling differences) and matched. With an OpenAI key the matching is
   done by `gpt-4o-mini`, without one a rule-based matcher is used.
   See `analysis/comparison.py`.
4. **Site check.** Each customer that disappeared from the customer page is
   searched for on the rest of the company's site with Context.dev. Every hit
   is fetched to make sure the page is still live and names the customer. A
   customer that's still mentioned somewhere was probably just rotated out;
   one that's gone from the whole site is the stronger signal.
   See `find_site_mentions` in `backend/context_api.py`.
5. **Dashboard.** A Streamlit app with a one-line summary, evidence for each
   lost customer (archived page and date, current page, where it's still
   mentioned) and a table of all customers. See `app.py` and `frontend/`.

If fetching the current or historical customers fails, the dashboard switches
to demo data and shows a warning with the reason, so you always know whether
you're looking at real results. If only the comparison fails, a simpler exact
name match is used and a note says so.

## Setup

Tested with Python 3.9.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then add your keys to `.env`:

| Variable              | Needed for                                   | Required |
|-----------------------|----------------------------------------------|----------|
| `CONTEXT_DEV_API_KEY` | scraping the current customer page           | yes      |
| `OPENAI_API_KEY`      | AI-based name matching                       | no       |
| `EXA_API_KEY`         | competitor search (not in the dashboard yet) | no       |

The Wayback Machine doesn't need a key.

## Running

```bash
streamlit run app.py
```

Open http://localhost:8501, enter a company website (for example `kone.com`)
and pick the year to compare against.

If you know the address of the customer page, enter it directly, e.g.
`https://www.kone.com/en/references/`. It's faster and uses fewer API requests.

## Caching and API usage

- **Current customers** are cached per company in `data/current/<domain>.json`.
  A new company costs 1-4 Context.dev requests, after that it's read from the
  file. Delete the file to fetch it again.
- **Historical customers** are cached per company and year in
  `data/historical/<domain>_<year>.json`. The first
  fetch for a company can take several minutes, because the Wayback Machine
  rate-limits requests. To fetch ahead of time:
  ```bash
  python -m backend.wayback kone.com 2023
  ```
- **Timelines** (the customer page every six months, to see when each customer
  appeared and disappeared) are cached in `data/timeline/<domain>_<year>.json`.
  Fetching one takes a few minutes:
  ```bash
  python -m backend.wayback kone.com 2023 --timeline
  ```
- **Site checks** are cached per company in `data/mentions/<domain>.json`.
  Each lost customer costs one search, plus a page fetch when a hit can't be
  verified with a plain request.
- The dashboard also keeps results in memory for an hour per URL and year.

`kone.com` with 2023 is already cached in the repository, including the site
checks, so it works without Context.dev or Wayback requests. If `OPENAI_API_KEY` is set, the comparison
still makes one OpenAI request.

## Project layout

```
app.py                     Streamlit entry point
frontend/                  dashboard, data loading, demo data
backend/context_api.py     current customers (Context.dev)
backend/wayback.py         historical customers (Wayback Machine)
backend/competitor_search.py
analysis/comparison.py     matching old and new customers
analysis/ai_analysis.py    comparison + competitor evidence per customer
data/                      cached results
```

## Limitations

- Only dedicated customer pages are checked. Logos shown on the front page
  only are not picked up.
- Some companies list projects or buildings instead of client companies.
  KONE's references are a good example.
- The site check only looks at the main domain (`kone.com`, `www.kone.com`).
  Mentions on other subdomains, such as distributor portals, are ignored.
- Results depend on how the page is built. Logo walls with no alt text end up
  with names guessed from the image file names.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
