"""Offline tests for the consent check: tracker classification and verdicts (no browser).

Run:  .venv/bin/python -m unittest discover -s tests -t .
"""
import unittest

from backend import consent as c
from backend import trackers as tr


class ClassifyTest(unittest.TestCase):
    def test_send_versus_load(self):
        self.assertEqual(tr.classify_request("https://www.facebook.com/tr/?id=1&ev=PageView")["kind"], "send")
        self.assertEqual(tr.classify_request("https://connect.facebook.net/en_US/fbevents.js")["kind"], "load")

    def test_consent_mode_denied_is_a_ping(self):
        hit = tr.classify_request("https://region1.google-analytics.com/g/collect?v=2&tid=G-X&gcs=G100")
        self.assertEqual(hit["kind"], "ping")
        granted = tr.classify_request("https://region1.google-analytics.com/g/collect?v=2&tid=G-X&gcs=G111")
        self.assertEqual(granted["kind"], "send")

    def test_server_side_tagging_on_own_domain(self):
        hit = tr.classify_request("https://metrics.example.fi/g/collect?v=2&tid=G-ABC")
        self.assertEqual((hit["tracker"], hit["kind"], hit["own_domain"]), ("Google Analytics", "send", True))
        self.assertFalse(tr.classify_request("https://www.google-analytics.com/g/collect?v=2")["own_domain"])

    def test_tag_manager_loader_and_consent_tools_are_not_trackers(self):
        self.assertIsNone(tr.classify_request("https://www.googletagmanager.com/gtm.js?id=GTM-X"))
        self.assertIsNone(tr.classify_request("https://consent.cookiebot.com/uc.js"))
        self.assertEqual(tr.consent_tool("https://consent.cookiebot.com/uc.js"), "Cookiebot")
        self.assertEqual(tr.consent_tool("https://cdn.privacy-mgmt.com/unified/x.js"), "Sourcepoint")

    def test_cookies(self):
        self.assertEqual(tr.classify_cookie("_ga_6FS4Z2"), "Google Analytics")
        self.assertEqual(tr.classify_cookie("_fbp"), "Meta Pixel")
        self.assertIsNone(tr.classify_cookie("session_id"))


class AnalyseTest(unittest.TestCase):
    def test_tracks_when_data_sent(self):
        a = c.analyse([{"ms": 120, "url": "https://www.facebook.com/tr/?ev=PageView"},
                       {"ms": 40, "url": "https://consent.cookiebot.com/uc.js"}], [])
        self.assertEqual(c.verdict(a["trackers"]), "tracks_before_consent")
        self.assertEqual(a["consent_tool"], {"name": "Cookiebot", "ms": 40})
        self.assertEqual(a["trackers"][0]["first_ms"], 120)

    def test_cookie_alone_counts(self):
        a = c.analyse([], [{"name": "_ga", "domain": ".x.fi"}])
        self.assertEqual(c.verdict(a["trackers"]), "tracks_before_consent")

    def test_script_only_is_loads(self):
        a = c.analyse([{"ms": 300, "url": "https://bat.bing.com/bat.js"}], [])
        self.assertEqual(c.verdict(a["trackers"]), "loads_before_consent")

    def test_pings_and_matomo_are_not_counted(self):
        a = c.analyse([{"ms": 50, "url": "https://region1.google-analytics.com/g/collect?v=2&gcs=G100"},
                       {"ms": 80, "url": "https://stats.x.fi/matomo.php?idsite=1"}], [])
        self.assertEqual(c.verdict(a["trackers"]), "clean")
        self.assertEqual(len(a["pings"]), 1)
        self.assertFalse(a["trackers"][0]["counted"])
        self.assertIn("without consent", a["trackers"][0]["note"])

    def test_evidence_drops_query_strings(self):
        a = c.analyse([{"ms": 10, "url": "https://www.facebook.com/tr/?id=123&ud[em]=hash"}], [])
        self.assertEqual(a["trackers"][0]["evidence"][0]["url"], "https://www.facebook.com/tr/")


if __name__ == "__main__":
    unittest.main()
