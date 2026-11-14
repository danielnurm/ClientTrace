# Labelling guide: is this customer moving away?

This guide defines the ground truth for evaluating Competitor alerts. The
question the evaluation answers is: **when ClientTrace (or a naive competitor
alert) says a customer needs attention, how often is that right, and how many
real cases does it miss?**

Labels are a person's judgement from public evidence, not the truth about
contracts. That's the honest limit of this evaluation; write the reasoning down
so anyone can check it.

## 1. What you label

One row = **one customer site, from one vendor's point of view, on one date.**

- *Vendor* = the company whose customer-success team would read the alert
  (e.g. Giosg). The site is in the data set because it runs, or ran, that
  vendor's chat.
- A site with two chat tools gets **one row per vendor** whose customer it is.
  fennia.fi runs Giosg and Salesforce chat → one row from Giosg's view, one
  from Salesforce's.
- *Date* = the day you label. Websites change; the label is about that day.

## 2. Rules for labelling

1. **Label blind.** Don't run ClientTrace on the site and don't look at its
   status before you've written your label. Predictions live in a separate
   file (`predictions_*.csv`) and are only joined when metrics are computed.
2. **Look at the site yourself, in a normal browser.** Accept the cookie banner,
   open the home page and the customer-service / contact page, and note which
   chat appears where.
3. **Use only public evidence**, and record it (section 5).
4. **Time-box: 10 minutes per row.** If you can't decide in 10 minutes, the
   label is `unsure`. Don't guess.
5. **Write one sentence of reasoning** for every row. A label without a reason
   can't be checked.

## 3. The label: `state`

Pick exactly one, from the vendor's point of view.

| state | Means | Typical evidence |
|---|---|---|
| `healthy` | Customer uses the vendor's chat; no competitor chat with the same job | only the vendor's chat on the service pages |
| `evaluating` | A competitor's chat does **the same job** on the same audience, next to the vendor's, and it looks new | both offered on the customer-service page; competitor appeared recently in the archive; a pilot announcement |
| `migrating_away` | Clear move from the vendor to a competitor is under way | competitor on most pages, vendor left on a few; news or job ads about the new tool; privacy policy names the competitor as the new provider |
| `gone` | The vendor's chat is no longer on the site, a competitor's is | competitor only; vendor's script gone from all checked pages |
| `moving_to_us` | The vendor is the **new** tool next to an older competitor | vendor's chat appeared later in the archive than the competitor's |
| `complementary` | Two tools do **different jobs** and are meant to work together | an AI bot that hands over to a live-agent platform (e.g. Boost.ai bot + Puzzel agents); one tool only for logged-in customers |
| `separate_sections` | Different tools in different parts of the business | shop uses one chat, customer service another; B2B site vs consumer site |
| `leftover` | A competitor's script is loaded but does nothing visible | script in the HTML or Tag Manager, but no widget anywhere |
| `unsure` | Can't tell in 10 minutes from public evidence | – |

**The binary target** used for precision and recall:

- **needs attention** = `evaluating` or `migrating_away`
- **doesn't need attention** = `healthy`, `complementary`, `separate_sections`, `leftover`, `moving_to_us`
- `gone` is evaluated separately (is "already on a competitor" right?)
- `unsure` rows are excluded from the metrics and their count is reported.

### Hard cases

- **AI bot + human chat from two vendors.** If the bot visibly hands the
  conversation over to the other tool, it's `complementary`, even though both
  count as "chat". This is common in Nordic banking and insurance.
- **Same tool, different instance** (e.g. two Boost.ai bots for private and
  business customers) isn't a competitor at all. Note it and label `healthy`.
- **Our tool hidden by consent.** If a chat only appears after accepting
  cookies, accept them and look again before deciding.
- **Logged-in areas.** You can't see them; don't assume. Label from what is public.

## 4. Optional fields

- `direction`: who is replacing whom, if visible: `to_competitor`,
  `to_vendor`, `none`, `unknown`.
- `confidence`: `high` (two or more independent pieces of evidence agree),
  `medium` (one clear piece), `low` (a hint only).

## 5. Evidence

List the URLs you based the label on, separated by `;`. Good evidence, roughly
strongest first:

1. what you saw on the live page (write the page URL and where the chat appears)
2. archive snapshots showing when a tool appeared or disappeared
3. the privacy or cookie policy naming a provider
4. a press release, news story or job ad about the chat tool
5. the help centre's platform

## 6. Second opinion

At least **20 rows should be labelled by two people independently**
(`labeller` differs). The agreement between them (Cohen's kappa) tells how
reliable the labels themselves are. Disagreements are discussed and the agreed
label goes into `final_state`; both originals stay in the file.

## 7. Data format: `eval/labels.csv`

UTF-8 CSV, one row per (site, vendor, date). Columns:

| column | required | example | meaning |
|---|---|---|---|
| `id` | yes | `fennia.fi\|Giosg` | site and vendor, unique together with `labelled_at` |
| `site` | yes | `fennia.fi` | domain, no `https://` or `www.` |
| `vendor` | yes | `Giosg` | product name exactly as in `backend/site_tech.SIGNATURES` |
| `state` | yes | `evaluating` | one value from section 3 |
| `direction` | no | `unknown` | section 4 |
| `confidence` | no | `medium` | section 4 |
| `competitors` | no | `Salesforce chat` | other chat tools you saw, `;`-separated |
| `evidence_urls` | yes | `https://www.fennia.fi/;https://web.archive.org/...` | section 5 |
| `reason` | yes | `Both chats offered on the contact page; Salesforce new since Mar 2026` | one sentence |
| `labeller` | yes | `daniel` | who labelled |
| `labelled_at` | yes | `2026-11-15` | date of the label = date the site was looked at |
| `minutes` | no | `8` | time spent |
| `final_state` | no | `evaluating` | agreed label when two people labelled the row |

Predictions go into a separate file with the same `id` and `labelled_at`, so
the labels stay blind:

`eval/predictions_<method>.csv`: `id, labelled_at, method, predicted_status, needs_attention`

where `method` is e.g. `naive` (any competitor chat detected) or `clienttrace`
(likely switching or possibly trialling), and `needs_attention` is `yes` / `no`.

## 8. Which sites to include

Make the set as unbiased as you can:

- **Every site** in the candidate list that runs, or ran, the vendor's chat,
  not only the interesting ones. Healthy customers are needed to measure false
  alarms.
- Candidate sources: the vendors' own customer pages, the Nordic bank and
  insurer list, and sites found by the live scan.
- Write down how each site got into the list (`notes` in the candidate file),
  so the selection itself can be judged.

The honest limit: positives that no method can see (for example a chat that
only loads after login) aren't in the set at all, so recall is measured only
among cases a public-web method could possibly find.
