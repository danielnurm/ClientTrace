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

## Competitor alerts (live)

The second tab answers the question a customer-success team at a chat vendor
actually has: **which of our customers have started running a competitor's chat
next to ours?** Two chat tools on one site is often a trial or a migration in
progress, months before the customer cancels. But many such sightings are
harmless (a different tool in the online shop than in customer service), so
every competitor found is checked before it raises an alarm.

For each customer site, all live and without API credits:

1. the home page and its Google Tag Manager containers (many sites load their chat there)
2. up to two customer-service pages: is the competitor on the **same page** as our chat?
3. the privacy or cookie policy: does it **name** the competitor?
4. the help centre's hosting: does it run on the competitor?
5. the homepage in the Wayback Machine, if cached: **since when** has each tool been there?

Each customer gets a plain-language status:

| Status | When | What to do |
|---|---|---|
| 🔴 Likely switching | same page as ours **and** privacy policy or help centre points to the competitor, or our chat disappeared since the last check | contact this week |
| 🟠 Possibly trialling | same page as ours, **or** named in the privacy policy | check in soon |
| 🟡 Worth a look | only on other pages than ours | usually nothing |
| ⚫ Already on a competitor | our chat is gone, a competitor's runs | win-back |
| 🟢 Healthy | only our chat | – |
| ⚪ Can't tell | nothing detected or the site isn't reachable | check by hand |

The page shows one bar for the whole customer base, which competitors show up
on your customers' sites, and a card per customer with the evidence and links.
**Check now** stores every check in `data/sites/<site>_live.json`, so the next
check shows what changed since the previous one.

From the command line:

```bash
python -m backend.site_tech check tokmanni.fi fennia.fi          # live check, ~1 s
python -m backend.site_tech supplier giosg.com Giosg tokmanni.fi fennia.fi
python -m backend.churn_watch customers Giosg tokmanni.fi fennia.fi elisa.fi   # with precision checks
python -m backend.wayback fennia.fi 2021 --site-history          # archive, a few minutes
```

**Live demo of a switch.** A fake customer site whose chat you switch mid-pitch:

```bash
python -m http.server 8765 -d demo/customer_site      # terminal 1
python -m backend.site_tech watch http://localhost:8765 --interval 3   # terminal 2
python demo/switch_chat.py intercom                   # terminal 3: giosg | intercom | zendesk | none
```

Or add `http://localhost:8765` to the site list in the dashboard and press
**Check now** before and after switching.

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
- **Site histories** (which products a homepage ran, per quarter) are cached in
  `data/sites/<domain>_history.json`; `tokmanni.fi`, `fennia.fi`,
  `lahitapiola.fi` and `elisa.fi` are included. Live checks are free (plain
  HTTP, no API) and kept locally in `data/sites/<site>_live.json` (not in git).
  Customer domains found by search cost one Context.dev request each and are
  cached in `data/sites/domains.json`.
- The dashboard also keeps results in memory for an hour per URL and year.

`kone.com` with 2023 is already cached in the repository, including the site
checks, so it works without Context.dev or Wayback requests. If `OPENAI_API_KEY` is set, the comparison
still makes one OpenAI request.

## Project layout

```
app.py                     Streamlit entry point
frontend/                  dashboard, data loading, demo data
backend/context_api.py     current customers (Context.dev)
backend/wayback.py         historical customers and site histories (Wayback Machine)
backend/site_tech.py       live product detection (page + Tag Manager), supplier report
demo/                      fake customer site for the live switch demo
tests/                     offline unit tests: python -m unittest discover tests
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
- Competitor alerts: products loaded through Google Tag Manager are visible live,
  but their history isn't, because Tag Manager containers are almost never
  archived. In our test of 17 Finnish sites a chat widget was in the page HTML
  on 3 and only in Tag Manager on 1–3 more. Some sites (e.g. alko.fi) block
  automated requests.
- Results depend on how the page is built. Logo walls with no alt text end up
  with names guessed from the image file names.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
