# ClientTrace

See which of your customers are moving to a competitor, from their own websites.

ClientTrace is for customer-success and sales teams at companies that sell
customer chat (Giosg, Boost.ai, Puzzel, ...). Give it your product and your
customers' websites. It checks each site live, finds competitors' chat tools,
and only raises an alarm when more evidence points the same way, because most
competitor sightings are harmless. Every alert comes with a plain-language
status, what to do, and links to the proof.

## How it works

ClientTrace answers the question a customer-success team at a chat vendor
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
| 🔵 Moving to us | the archive shows our chat arrived after the competitor's older one | help them finish the move |
| 🟢 Healthy | only our chat | – |
| ⚪ Can't tell | nothing detected or the site isn't reachable | check by hand |

Chat vendors recognised include Giosg, Genesys, Salesforce chat, Zendesk, Intercom and
the Nordic Boost.ai, Puzzel, Humany and Leadoo, each signature verified on a real site.
On 37 Nordic banks and insurers a chat tool was visible on 15; the largest banks
(Nordea, OP, Swedbank, SEB, Handelsbanken, DNB) load their chat in a way the page and
Tag Manager don't show, so they appear as *can't tell*.

The page shows one bar for the whole customer base, which competitors show up
on your customers' sites, **how customers switch** (which chat ran on each site,
month by month, from the archive, with the warning time before a switch), and a
card per customer with the evidence and links. Archive timelines are built once
and cached:

```bash
python -m backend.switch_timeline build Giosg tokmanni.fi fennia.fi omasp.fi   # a few minutes per site
```
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

Or keep `http://localhost:8765` in the site list in the dashboard and press
**Check now** before and after switching.

## Setup

Tested with Python 3.9.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Competitor alerts need no API keys: live checks are plain HTTP and the Wayback
Machine is free. Keys in `.env` are only needed for:

| Variable              | Needed for                                                        | Required |
|-----------------------|-------------------------------------------------------------------|----------|
| `CONTEXT_DEV_API_KEY` | reading a customer page (an empty customer list, or the second tab) | no       |
| `OPENAI_API_KEY`      | AI-based name matching in the second tab                          | no       |
| `EXA_API_KEY`         | competitor search (not in the dashboard)                          | no       |

## Running

```bash
streamlit run app.py
```

Open http://localhost:8501. **Competitor alerts** opens with a demo list of
Finnish customer sites; press **Check now**.

## Why logo pages mislead (the second tab)

The obvious way to spot a lost customer is to compare a company's customer or
reference page with the same page in the Wayback Machine. ClientTrace started
there, and the measurements are why the product checks the customer's own site
instead:

- **kone.com:** 19 references disappeared since 2023. The archive history showed
  all of them were still on the site until spring 2026, when KONE moved its
  references to a new site. Lost customers: **0**.
- **zendesk.com:** 4 customers whose stories disappeared all still run Zendesk's
  help centre today. Lost customers: **0**.

The second tab keeps that comparison to show the difference (try `kone.com`
and 2023). How it works:

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
app.py                       Streamlit entry point
frontend/switches.py         Competitor alerts view
frontend/switch_chart.py     'How customers switch' chart (Plotly)
frontend/                    second tab: dashboard, data loading, demo data
backend/site_tech.py         live product detection (page + Tag Manager), supplier report
backend/churn_watch.py       precision checks and statuses for competitor alerts
backend/switch_timeline.py   month-by-month chat history from the Wayback Machine
backend/context_api.py       customer pages and site search (Context.dev)
backend/wayback.py           Wayback Machine helpers, historical customers, site histories
analysis/                    name matching and competitor evidence (second tab)
demo/                        fake customer site for the live switch demo
tests/                       offline unit tests: python -m unittest discover -s tests -t .
data/                        cached results
```

## Limitations

- Competitor alerts can't see logged-in areas or tools that load only after
  cookie consent, so *can't tell* never means *doesn't use*. On 37 Nordic banks
  and insurers a chat tool was visible on 15.
- The second tab only checks dedicated customer pages. Logos shown on the front page
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
