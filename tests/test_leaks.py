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

    def test_failed_phase_is_never_clean(self):
        runs = [{"searched": False, "error": None, "accepted": None, "carriers": {}}] * 2
        self.assertEqual(lk._phase(runs, accept=False)["status"], "no_search")
        runs = [{"searched": "url", "error": None, "accepted": False, "carriers": {}}] * 2
        self.assertEqual(lk._phase(runs, accept=True)["status"], "no_accept")
        runs = [{"searched": None, "error": None, "accepted": None, "blocked": True, "carriers": {}}] * 2
        self.assertEqual(lk._phase(runs, accept=False)["status"], "blocked")

    def test_bot_wall_is_blocked(self):
        self.assertTrue(lk.blocked(403, "Just a moment...", "Checking your browser"))
        self.assertTrue(lk.blocked(200, "Access Denied", "x"))
        self.assertTrue(lk.blocked(200, "", "  "))
        self.assertFalse(lk.blocked(200, "Apoteket", "Välkommen"))

    def test_accept_text_in_nordic_and_german(self):
        for t in ["Tillåt alla", "Acceptér alle", "Alles akzeptieren", "Hyväksy kaikki", "Accept all cookies"]:
            self.assertRegex(t, lk.ACCEPT_TEXT)
        self.assertNotRegex("Endast nödvändiga", lk.ACCEPT_TEXT)

    def test_summary_counts_companies_per_phase(self):
        rows = [{"site": "a.fi", "verdict": "sent_before_consent",
                 "before": {"recipients": [{**_rec("GA", "analytics"), "own_domain": True}]},
                 "after": {"recipients": [_rec("GA", "analytics"), _rec("Meta Pixel")]}},
                {"site": "b.fi", "verdict": "not_sent", "before": {"recipients": []}, "after": {"recipients": []}}]
        s = lk.summarise(rows)
        self.assertEqual(s["verdicts"], {"sent_before_consent": 1, "not_sent": 1})
        self.assertEqual(s["own_domain"], ["a.fi"])
        self.assertEqual([(c["name"], c["before"], c["total"]) for c in s["companies"]], [("GA", 1, 1), ("Meta Pixel", 0, 1)])


if __name__ == "__main__":
    unittest.main()
