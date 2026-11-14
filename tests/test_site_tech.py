"""Offline tests for product detection, change detection and site history.

Run:  .venv/bin/python -m unittest discover tests
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import site_tech as st
from backend.wayback import summarize_site_history


def cap(date, *products):
    return {"date": date, "url": f"https://web.archive.org/web/{date.replace('-', '')}/x", "products": list(products)}


class DetectTest(unittest.TestCase):
    def test_script_host_in_html(self):
        html = '<script async src="https://widget.intercom.io/widget/abc"></script>'
        self.assertEqual(st.detect_products(html), ["Intercom"])

    def test_escaped_gtm_container(self):
        # GTM containers escape slashes: https:\/\/service.giosg.com
        js = r'var g=\"https:\/\/service.giosg.com\";d.src=g+\"\/live2\/\"'
        self.assertEqual(st.detect_products(js), ["Giosg"])

    def test_brand_name_in_text_is_not_a_hit(self):
        self.assertEqual(st.detect_products("<p>We moved from Intercom and Giosg to Zendesk</p>"), [])

    def test_custom_signature_lists(self):
        self.assertEqual(st.detect_products("x cdn.example-chat.io y", {"Ex": {"category": "chat", "patterns": ["cdn.example-chat.io"]}}), ["Ex"])

    def test_site_key(self):
        self.assertEqual(st._site_key("https://www.tokmanni.fi/"), "tokmanni.fi")
        self.assertEqual(st._site_key("http://localhost:8765"), "localhost_8765")
        self.assertEqual(st._site_url("tokmanni.fi"), "https://www.tokmanni.fi/")


class DiffTest(unittest.TestCase):
    def test_switch_within_category(self):
        d = st.diff_products(["Giosg", "Hotjar"], ["Intercom", "Hotjar"])
        self.assertEqual(d["switches"], [{"from": "Giosg", "to": "Intercom", "category": "chat"}])

    def test_different_categories_are_not_a_switch(self):
        d = st.diff_products(["Giosg"], ["Hotjar"])
        self.assertEqual((d["added"], d["removed"], d["switches"]), (["Hotjar"], ["Giosg"], []))


class CheckSiteTest(unittest.TestCase):
    def test_reads_html_and_gtm(self):
        html = '<script src="https://static.zdassets.com/ekr/snippet.js"></script> GTM-ABC1234'
        gtm = r'\"https:\/\/service.giosg.com\"'

        def fake_get(url, **kw):
            r = mock.Mock(status_code=200)
            r.text = gtm if "googletagmanager" in url else html
            r.raise_for_status = lambda: None
            return r

        with mock.patch.object(st.requests, "get", side_effect=fake_get):
            r = st.check_site("example.com")
        self.assertEqual(r["products"], ["Giosg", "Zendesk"])
        self.assertEqual(r["found_in"], {"Zendesk": "html", "Giosg": "gtm"})
        self.assertEqual(r["gtm_ids"], ["GTM-ABC1234"])


class HistoryTest(unittest.TestCase):
    def test_single_missing_capture_is_not_removal(self):
        # Tokmanni 2022-01: Giosg missing from one capture, back in the next one
        h = summarize_site_history([cap("2021-07-01", "Giosg"), cap("2022-01-05"), cap("2022-07-01", "Giosg")])
        self.assertEqual(h["products"]["Giosg"]["status"], "present")
        self.assertEqual(h["switches"], [])

    def test_missing_from_newest_capture_only_is_unconfirmed(self):
        h = summarize_site_history([cap("2024-01-01", "Giosg"), cap("2024-04-01")])
        self.assertEqual(h["products"]["Giosg"]["status"], "unconfirmed")

    def test_switch_after_two_missing_captures(self):
        h = summarize_site_history([cap("2024-01-01", "Giosg"), cap("2024-04-01", "Intercom"),
                                    cap("2024-07-01", "Intercom")])
        self.assertEqual(h["products"]["Giosg"]["missing_since"], "2024-04-01")
        self.assertEqual(h["switches"][0]["from"], "Giosg")
        self.assertEqual(h["switches"][0]["between"], ["2024-01-01", "2024-04-01"])

    def test_failed_captures_are_ignored(self):
        caps = [cap("2024-01-01", "Giosg"), {"date": "2024-04-01", "url": "u", "error": "refused"},
                cap("2024-07-01", "Giosg")]
        self.assertEqual(summarize_site_history(caps)["products"]["Giosg"]["status"], "present")


class ReportTest(unittest.TestCase):
    def live(self, found_in, checked="2026-11-14T12:00:00+00:00"):
        return {"site": "x.fi", "url": "https://www.x.fi/", "checked_at": checked,
                "products": sorted(found_in), "found_in": found_in}

    def test_fennia_like_new_competitor(self):
        # Salesforce new in the archive (HTML), Giosg only visible live through GTM
        hist = {"captures": [cap("2026-01-02"), cap("2026-07-10", "Salesforce chat")],
                **summarize_site_history([cap("2026-01-02"), cap("2026-07-10", "Salesforce chat")])}
        r = st.site_report("x.fi", live=self.live({"Salesforce chat": "html", "Giosg": "gtm"}), history=hist)
        self.assertEqual(r["products"]["Giosg"]["confidence"], "medium")
        self.assertIsNone(r["products"]["Giosg"]["since"])
        self.assertEqual(r["signals"], [{"type": "new_competitor", "category": "chat", "new": "Salesforce chat",
                                         "since": "2026-07-10", "alongside": ["Giosg"], "confidence": "low"}])

    def test_confirmed_switch_is_high_confidence(self):
        caps = [cap("2024-01-01", "Giosg"), cap("2024-04-01", "Intercom"), cap("2024-07-01", "Intercom")]
        hist = {"captures": caps, **summarize_site_history(caps)}
        r = st.site_report("x.fi", live=self.live({"Intercom": "html"}), history=hist)
        self.assertEqual(r["signals"][0]["type"], "switch")
        self.assertEqual(r["signals"][0]["confidence"], "high")
        self.assertEqual(r["products"]["Giosg"]["status"], "removed")

    def test_old_parallel_tools_are_not_a_signal(self):
        caps = [cap("2022-01-01", "Hotjar"), cap("2023-01-01", "Hotjar", "Microsoft Clarity")]
        hist = {"captures": caps, **summarize_site_history(caps)}
        r = st.site_report("x.fi", live=self.live({"Hotjar": "html", "Microsoft Clarity": "html"}), history=hist)
        self.assertEqual(r["signals"], [])



class SupplierTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(st, "DOMAINS_CACHE", self.tmp / "domains.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_domain_lookup_skips_social_and_supplier(self):
        calls = []

        def fake_search(q, **kw):
            calls.append(q)
            return {"results": [{"url": "https://www.linkedin.com/company/x"},
                                {"url": "https://www.giosg.com/customers/x"},
                                {"url": "https://www.x-oy.fi/"}]}
        self.assertEqual(st.find_customer_domain("X Oy", "giosg.com", fake_search), "x-oy.fi")
        self.assertEqual(st.find_customer_domain("X Oy", "giosg.com", fake_search), "x-oy.fi")
        self.assertEqual(len(calls), 1)  # second call comes from the cache

    def test_verdicts(self):
        live = {
            "a.fi": {"site": "a.fi", "url": "https://www.a.fi/", "checked_at": "2026-11-14T12:00:00+00:00",
                     "latency_ms": 5, "products": ["Giosg"], "found_in": {"Giosg": "html"}},
            "b.fi": {"site": "b.fi", "url": "https://www.b.fi/", "checked_at": "2026-11-14T12:00:00+00:00",
                     "latency_ms": 5, "products": [], "found_in": {}},
            "c.fi": {"site": "c.fi", "url": "https://www.c.fi/", "error": "HTTPError: 403"},
        }
        with mock.patch.object(st, "check_sites", return_value=live), \
                mock.patch.object(st, "_cached_history", return_value=None):
            r = st.supplier_report("giosg.com", "Giosg", customers=[
                {"name": "A", "domain": "a.fi"}, {"name": "B", "domain": "b.fi"}, {"name": "C", "domain": "c.fi"}])
        self.assertEqual(r["summary"], {"still_running": 1, "not_detected": 1, "error": 1})

    def test_customer_link_gives_domain_without_search(self):
        live = {"tokmanni.fi": {"site": "tokmanni.fi", "error": "skipped"}}
        with mock.patch.object(st, "check_sites", return_value=live) as cs, \
                mock.patch.object(st, "find_customer_domain") as fd:
            st.supplier_report("giosg.com", "Giosg",
                               customers=[{"name": "T", "source_url": "https://www.tokmanni.fi/", "logo_url": ""}])
        fd.assert_not_called()
        cs.assert_called_once_with(["tokmanni.fi"])


if __name__ == "__main__":
    unittest.main()
