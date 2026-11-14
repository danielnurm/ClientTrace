"""Offline tests for the churn early warning (precision checks).

Run:  .venv/bin/python -m unittest discover -s tests -t .
"""
import unittest
from unittest import mock

from backend import churn_watch as cw


def live(products, found_in, gtm_ids=()):
    return {"site": "x.fi", "url": "https://www.x.fi/", "checked_at": "2026-11-14T12:00:00+00:00",
            "latency_ms": 5, "products": products, "found_in": found_in, "gtm_ids": list(gtm_ids)}


class PagesTest(unittest.TestCase):
    HOME = ('<a href="/asiakaspalvelu">Asiakaspalvelu</a> <a href="/yhteystiedot">Yhteystiedot</a>'
            '<a href="/tuotteet">Tuotteet</a> <a href="https://facebook.com/x">FB</a>'
            '<a href="/tietosuoja">Tietosuoja</a> <a href="/evasteet">Evästeet</a>')

    def test_service_pages_most_specific_first(self):
        self.assertEqual(cw.service_pages(self.HOME, "https://www.x.fi/"),
                         ["https://www.x.fi/asiakaspalvelu", "https://www.x.fi/yhteystiedot"])

    def test_privacy_pages_prefer_privacy_over_cookies(self):
        self.assertEqual(cw.privacy_pages(self.HOME, "https://www.x.fi/")[0], "https://www.x.fi/tietosuoja")

    def test_other_sites_are_ignored(self):
        self.assertNotIn("https://facebook.com/x", cw.service_pages(self.HOME, "https://www.x.fi/"))


class HelpPlatformTest(unittest.TestCase):
    def test_zendesk_from_address(self):
        self.assertEqual(cw.help_platform("https://support.x.com/hc/en-us", ""), "Zendesk")

    def test_intercom_with_old_zendesk_links_is_intercom(self):
        # the Vanta case: an Intercom help centre still links to old /hc/en-us/ articles
        page = ('<link href="https://static.intercomassets.com/assets/x.css">'
                '<a href="https://help.x.com/hc/en-us/articles/360052045891">old</a>')
        self.assertEqual(cw.help_platform("https://help.x.com/en/", page), "Intercom")

    def test_unknown_platform(self):
        self.assertIsNone(cw.help_platform("https://help.x.com/", "<html>custom</html>"))


class DisclosureTest(unittest.TestCase):
    def test_named_in_privacy_policy(self):
        page = mock.Mock(ok=True, text="<p>Käytämme chat-palveluun Salesforce Inc:n palvelua.</p>" + " " * 300,
                         url="https://www.x.fi/tietosuoja")
        with mock.patch.object(cw, "_get", return_value=page):
            self.assertEqual(cw.disclosures(["https://www.x.fi/tietosuoja"], ["Salesforce chat", "Giosg"]),
                             {"Salesforce chat": "https://www.x.fi/tietosuoja"})

    def test_names_inside_scripts_do_not_count(self):
        page = mock.Mock(ok=True, text='<script>var a="giosg"</script><p>Tietosuoja</p>' + " " * 300,
                         url="https://www.x.fi/tietosuoja")
        with mock.patch.object(cw, "_get", return_value=page):
            self.assertEqual(cw.disclosures(["https://www.x.fi/tietosuoja"], ["Giosg"]), {})


class PageProductsTest(unittest.TestCase):
    def test_gtm_tool_counts_on_pages_that_load_the_container(self):
        lv = live(["Giosg", "Salesforce chat"], {"Giosg": "gtm", "Salesforce chat": "html"}, ["GTM-AAAA111"])
        home = 'GTM-AAAA111 <script src="https://x.salesforceliveagent.com/a.js"></script>'
        contact = mock.Mock(ok=True, text="GTM-AAAA111 contact page" + " " * 300)
        with mock.patch.object(cw, "_get", return_value=contact):
            on = cw.page_products(lv, home, ["https://www.x.fi/yhteystiedot"])
        self.assertEqual(on["Giosg"], ["/", "/yhteystiedot"])
        self.assertEqual(on["Salesforce chat"], ["/"])


class AssessTest(unittest.TestCase):
    def status(self, products, on_pages, help=None, disclosed=None):
        lv = live(products, {p: "html" for p in products})
        return cw.assess("Giosg", lv, on_pages, help, disclosed or {})["status"]

    def test_healthy(self):
        self.assertEqual(self.status(["Giosg", "Hotjar"], {"Giosg": ["/"]}), "healthy")  # Hotjar isn't chat

    def test_on_competitor(self):
        self.assertEqual(self.status(["Genesys"], {"Genesys": ["/"]}), "on_competitor")

    def test_unknown(self):
        self.assertEqual(self.status([], {}), "unknown")

    def test_other_section_is_only_worth_a_look(self):
        self.assertEqual(self.status(["Giosg", "Genesys"], {"Giosg": ["/kauppa"], "Genesys": ["/asiakaspalvelu"]}),
                         "worth_a_look")

    def test_same_page_is_possibly_trialling(self):
        self.assertEqual(self.status(["Giosg", "Genesys"], {"Giosg": ["/"], "Genesys": ["/"]}), "possibly_trialling")

    def test_privacy_policy_alone_is_possibly_trialling(self):
        self.assertEqual(self.status(["Giosg", "Genesys"], {"Giosg": ["/a"], "Genesys": ["/b"]},
                                     disclosed={"Genesys": "https://www.x.fi/tietosuoja"}), "possibly_trialling")

    def test_same_page_plus_privacy_policy_is_likely_switching(self):
        self.assertEqual(self.status(["Giosg", "Genesys"], {"Giosg": ["/"], "Genesys": ["/"]},
                                     disclosed={"Genesys": "https://www.x.fi/tietosuoja"}), "likely_switching")

    def test_same_page_plus_help_centre_is_likely_switching(self):
        self.assertEqual(self.status(["Giosg", "Zendesk"], {"Giosg": ["/"], "Zendesk": ["/"]},
                                     help={"url": "https://help.x.fi/hc/fi", "platform": "Zendesk"}), "likely_switching")

    def test_evidence_lists_pages(self):
        lv = live(["Giosg", "Genesys"], {"Giosg": "html", "Genesys": "html"})
        a = cw.assess("Giosg", lv, {"Giosg": ["/", "/a"], "Genesys": ["/", "/b"]}, None, {}, {"Genesys": "2026-04-11"})
        self.assertEqual(a["rivals"][0], {"name": "Genesys", "same_page": ["/"], "other_pages": ["/b"],
                                          "in_privacy_policy": None, "help_centre": False, "since": "2026-04-11"})


class CheckCustomerTest(unittest.TestCase):
    def run_check(self, before, after):
        lv = live(after, {p: "html" for p in after})
        stored = {"changes": cw.st.diff_products(before, after), "previous": {"checked_at": "2026-11-13T12:00:00+00:00"}}
        with mock.patch.object(cw.st, "check_site", return_value=lv), \
                mock.patch.object(cw, "_get", return_value=None), \
                mock.patch.object(cw, "help_center", return_value=None), \
                mock.patch.object(cw.st, "_cached_history", return_value=None), \
                mock.patch.object(cw.st, "store_check", return_value=stored):
            return cw.check_customer("x.fi", "Giosg")

    def test_our_tool_disappearing_next_to_a_rival_is_likely_switching(self):
        r = self.run_check(["Giosg", "Genesys"], ["Genesys"])
        self.assertEqual((r["status"], r["dropped_since_last_check"]), ("likely_switching", True))

    def test_timeline_turns_overlap_into_moving_to_us(self):
        lv = live(["Giosg", "Genesys"], {"Giosg": "html", "Genesys": "html"})
        tl = {"summary": {"moving_to_us": True}}
        with mock.patch.object(cw.st, "check_site", return_value=lv), \
                mock.patch.object(cw, "_get", return_value=None), \
                mock.patch.object(cw, "help_center", return_value=None), \
                mock.patch.object(cw.st, "_cached_history", return_value=None), \
                mock.patch("backend.switch_timeline.cached", return_value=tl):
            r = cw.check_customer("x.fi", "Giosg", record=False)
        self.assertEqual(r["status"], "moving_to_us")

    def test_unreachable_site_is_a_row_not_a_crash(self):
        with mock.patch.object(cw.st, "check_site", side_effect=ValueError("403")):
            self.assertEqual(cw.check_customer("x.fi", "Giosg")["status"], "unreachable")


if __name__ == "__main__":
    unittest.main()
