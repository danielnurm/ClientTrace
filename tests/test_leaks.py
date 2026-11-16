"""Offline tests for the search check: term decoding, recipients, run merging and verdicts (no browser).

Run:  .venv/bin/python -m unittest discover -s tests -t .
"""
import json
import unittest

from backend import leaks as lk
from backend import payload as pl
from backend import trackers as tr

GA4 = "https://region1.google-analytics.com/g/collect?v=2&tid=G-X&cid=123.456&dl=https%3A%2F%2Fwww.shop.de%2F%3Fq%3Dschwangerschaftstest"


class FindTermTest(unittest.TestCase):
    def test_page_url_inside_tracker_url_is_decoded_twice(self):
        hit = pl.find_term(GA4, "", "schwangerschaftstest")
        self.assertEqual(hit[0]["field"], "dl")
        self.assertIn("?q=schwangerschaftstest", hit[0]["snippet"])

    def test_space_as_plus_and_case(self):
        url = "https://www.facebook.com/tr/?id=1&ev=Search&cd[search_string]=Pregnancy+Test"
        self.assertEqual(pl.find_term(url, "", "pregnancy test")[0]["field"], "cd[search_string]")

    def test_form_body_and_ga4_batched_lines(self):
        body = "en=page_view&dl=https%3A%2F%2Fx.fi%2F\r\nen=search&ep.search_term=raskaustesti"
        self.assertEqual([h["field"] for h in pl.find_term("https://x/g/collect?v=2", body, "raskaustesti")],
                         ["ep.search_term"])

    def test_json_body_reports_the_key_path(self):
        body = json.dumps({"context": {"page": {"search": "?q=masennus"}}, "anonymousId": "abc"})
        self.assertEqual(pl.find_term("https://trk.io/v1/p", body, "masennus")[0]["field"], "context.page.search")

    def test_snippet_keeps_only_a_window_around_the_term(self):
        text = "uid=" + "9" * 100 + "&q=depression&" + "8" * 100
        s = pl.snippet(text, "depression")
        self.assertIn("depression", s)
        self.assertLess(len(s), 100)
        self.assertTrue(s.startswith("…") and s.endswith("…"))

    def test_no_term_no_hit(self):
        self.assertEqual(pl.find_term(GA4, "", "masennus"), [])


class RecipientTest(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(tr.recipient("https://abc-dsn.algolia.net/1/indexes")["category"], "site search")
        self.assertEqual(tr.recipient("https://track.adform.net/Serving/")["name"], "Adform")
        self.assertEqual(tr.recipient("https://www.google.com/rmkt/collect/1/")["name"], "Google Ads")
        self.assertEqual(tr.recipient("https://pagead2.googlesyndication.com/pagead/landing?x")["name"], "Google Ads")
        self.assertEqual(tr.recipient("https://widget.trustpilot.com/x")["category"], "reviews")
        self.assertEqual(tr.recipient("https://bam.eu01.nr-data.net/1/x")["category"], "site monitoring")
        self.assertEqual(tr.recipient("https://api.unknown-co.io/x"),
                         {"name": "api.unknown-co.io", "category": "other company", "own_domain": False})

    def test_site_search_request_is_not_a_recipient_but_own_domain_tagging_is(self):
        reqs = [{"ms": 10, "url": "https://www.shop.de/search?q=test", "body": ""},
                {"ms": 20, "url": "https://metrics.shop.de/g/collect?v=2&dl=https%3A%2F%2Fshop.de%2F%3Fq%3Dtest"},
                {"ms": 30, "url": "https://abc-dsn.algolia.net/1/indexes/*/queries", "body": '{"query":"test"}'}]
        found = lk.carriers("shop.de", reqs, "test")
        self.assertEqual(sorted(found), ["Algolia", "Google Analytics"])
        self.assertTrue(found["Google Analytics"]["own_domain"])
        self.assertEqual(found["Google Analytics"]["fields"], ["dl"])


def _rec(name, category="advertising"):
    return {"name": name, "category": category, "own_domain": False, "fields": ["dl"], "evidence": [], "first_ms": 5}


class MergeAndVerdictTest(unittest.TestCase):
    def test_only_recipients_in_every_run_count(self):
        stable, once = lk.merge_runs([{"Meta Pixel": _rec("Meta Pixel"), "Adform": _rec("Adform")},
                                      {"Meta Pixel": _rec("Meta Pixel")}])
        self.assertEqual([s["name"] for s in stable], ["Meta Pixel"])
        self.assertEqual(once, ["Adform"])

    def _row(self, before, after, b_status="ok", a_status="ok"):
        return {"before": {"status": b_status, "recipients": before}, "after": {"status": a_status, "recipients": after}}

    def test_verdicts(self):
        self.assertEqual(lk.verdict(self._row([_rec("GA", "analytics")], [])), "sent_before_consent")
        self.assertEqual(lk.verdict(self._row([], [_rec("Meta Pixel")])), "sent_after_consent")
        self.assertEqual(lk.verdict(self._row([_rec("Algolia", "site search")], [])), "not_sent")
        self.assertEqual(lk.verdict(self._row([_rec("x.io", "other company")], [])), "not_sent")
        self.assertEqual(lk.verdict(self._row([_rec("Trustpilot", "reviews")], [])), "not_sent")
        self.assertEqual(lk.verdict(self._row([], [], "no_search", "no_search")), "unknown")
        self.assertEqual(lk.verdict(self._row([], [], "ok", "no_accept")), "unknown")

    def test_sent_after_reject_ranks_above_accept(self):
        row = {**self._row([], [_rec("Meta Pixel")]), "reject": {"status": "ok", "recipients": [_rec("GA", "analytics")]}}
        self.assertEqual(lk.verdict(row), "sent_after_reject")
        row["reject"] = {"status": "ok", "recipients": []}
        self.assertEqual(lk.verdict(row), "sent_after_consent")

    def test_failed_phase_is_never_clean(self):
        runs = [{"searched": False, "error": None, "answered": None, "carriers": {}}] * 2
        self.assertEqual(lk._phase(runs, None)["status"], "no_search")
        runs = [{"searched": "url", "error": None, "answered": None, "carriers": {}}] * 2
        self.assertEqual(lk._phase(runs, "accept")["status"], "no_accept")
        self.assertEqual(lk._phase(runs, "reject")["status"], "no_reject")
        runs = [{"searched": None, "error": None, "answered": None, "blocked": True, "carriers": {}}] * 2
        self.assertEqual(lk._phase(runs, None)["status"], "blocked")

    def test_phase_records_how_the_banner_was_answered(self):
        runs = [{"searched": "url", "error": None, "answered": "api", "carriers": {}}] * 2
        self.assertEqual(lk._phase(runs, "accept")["answered_via"], "api")

    def test_bot_wall_is_blocked(self):
        self.assertTrue(lk.blocked(403, "Just a moment...", "Checking your browser"))
        self.assertTrue(lk.blocked(200, "Access Denied", "x"))
        self.assertTrue(lk.blocked(200, "", "  "))
        self.assertFalse(lk.blocked(200, "Apotek Ängen", "Välkommen"))

    def test_accept_text_in_nordic_and_german(self):
        for t in ["Tillåt alla", "Acceptér alle", "Alles akzeptieren", "Hyväksy kaikki", "Accept all cookies"]:
            self.assertRegex(t, lk.ACCEPT_TEXT)
        self.assertNotRegex("Endast nödvändiga", lk.ACCEPT_TEXT)

    def test_reject_text_in_nordic_and_german(self):
        for t in ["Hylkää kaikki", "Endast nödvändiga", "Afvis alle", "Alle ablehnen", "Reject all", "Kun nødvendige"]:
            self.assertRegex(t, lk.REJECT_TEXT)
        self.assertNotRegex("Hyväksy kaikki", lk.REJECT_TEXT)

    def test_summary_counts_companies_per_phase(self):
        rows = [{"site": "a.fi", "verdict": "sent_before_consent",
                 "before": {"recipients": [{**_rec("GA", "analytics"), "own_domain": True}]},
                 "after": {"recipients": [_rec("GA", "analytics"), _rec("Meta Pixel")]}},
                {"site": "b.fi", "verdict": "not_sent", "before": {"recipients": []}, "after": {"recipients": []}}]
        s = lk.summarise(rows)
        self.assertEqual(s["verdicts"], {"sent_before_consent": 1, "not_sent": 1})
        self.assertEqual(s["own_domain"], ["a.fi"])
        self.assertEqual([(c["name"], c["before"], c["total"]) for c in s["companies"]], [("GA", 1, 1), ("Meta Pixel", 0, 1)])

    def test_after_reject_counts_every_site_that_sent_it(self):
        rows = [{"site": "a.fi", "verdict": "sent_before_consent", "before": {"recipients": [_rec("GA", "analytics")]},
                 "reject": {"status": "ok", "recipients": [_rec("GA", "analytics")]}},
                {"site": "b.fi", "verdict": "not_sent", "before": {"recipients": []},
                 "reject": {"status": "ok", "recipients": []}},
                {"site": "c.fi", "verdict": "unknown", "before": {"recipients": []},
                 "reject": {"status": "no_reject", "recipients": []}}]
        self.assertEqual(lk.summarise(rows)["after_reject"], {"checked": 2, "sent": 1})


class AnonymiseTest(unittest.TestCase):
    def test_no_site_name_or_brand_survives(self):
        ev = {"ms": 5, "url": "https://sst.apotekangen.se/g/collect",
              "snippet": "dl=https://www.apotekangen.se/sok?q=graviditetstest&cid=1daPZ5JrXaSkEF9rNh5fFmkL"}
        rec = {**_rec("GA", "analytics"), "own_domain": True, "evidence": [ev]}
        row = {"site": "apotekangen.se", "country": "se", "kind": "pharmacy", "term": "graviditetstest",
               "verdict": "sent_before_consent", "before": {"status": "ok", "recipients": [rec]}}
        other = {"site": "apotekangen.dk", "country": "dk", "kind": "pharmacy", "term": "graviditetstest",
                 "verdict": "not_sent", "before": {"status": "ok", "recipients": []}}
        rep = {"method": {"regulators": {}}, "summary": {"own_domain": ["apotekangen.se"]}, "sites": [row, other]}
        out = lk.anonymise(rep)
        text = str(out)
        self.assertNotIn("apotekangen", text.lower())
        self.assertNotIn("1daPZ5JrXaSkEF9rNh5fFmkL", text)  # session id masked
        self.assertIn("graviditetstest", text)              # the search term stays readable
        self.assertNotIn("regulators", out["method"])
        labels = {r["site"]: r["label"] for r in out["sites"]}
        self.assertEqual(labels, {"se-pharmacy-a": "Online pharmacy, Sweden (A)",
                                  "dk-pharmacy-a": "Online pharmacy, Denmark (A)"})
        self.assertEqual(out["summary"]["own_domain"], ["se-pharmacy-a"])

    def test_brand_in_another_spelling_leaves_only_the_term(self):
        ev = {"ms": 5, "url": "https://www.google-analytics.com/g/collect", "field": "dt",
              "snippet": "Haku: 23 tulosta hakuehdolla \"raskaustesti\" – Pilleri Plus"}
        row = {"site": "pilleriplus.fi", "country": "fi", "kind": "pharmacy", "term": "raskaustesti",
               "verdict": "sent_before_consent",
               "before": {"status": "ok", "recipients": [{**_rec("GA", "analytics"), "evidence": [ev]}]}}
        out = lk.anonymise({"method": {}, "summary": {"own_domain": []}, "sites": [row]})
        snippet = out["sites"][0]["before"]["recipients"][0]["evidence"][0]["snippet"]
        self.assertEqual(snippet, "…raskaustesti…")
        self.assertNotIn("pilleri", str(out).lower())


if __name__ == "__main__":
    unittest.main()
