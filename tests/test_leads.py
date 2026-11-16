"""Offline tests for sales leads (churn_watch rows seen from the competitor's side).

Run:  .venv/bin/python -m unittest discover -s tests -t .
"""
import unittest
from unittest import mock

from backend import leads


def row(status, rivals=(), ours=True, dropped=False, timeline=None, site="x.fi"):
    return {"site": site, "url": f"https://{site}/", "status": status, "ours": ours, "our_pages": ["/"],
            "rivals": list(rivals), "dropped_since_last_check": dropped, "timeline": timeline,
            "products": ["Giosg"], "help_center": None}


def rival(name, same_page=(), other_pages=(), privacy=None, help_centre=False, since=None):
    return {"name": name, "same_page": list(same_page), "other_pages": list(other_pages),
            "in_privacy_policy": privacy, "help_centre": help_centre, "since": since}


class ToLeadTest(unittest.TestCase):
    def test_statuses_map_to_lead_statuses(self):
        cases = {"likely_switching": "leaving", "possibly_trialling": "trialling", "on_competitor": "switched",
                 "worth_a_look": "weak", "healthy": "locked_in", "moving_to_us": "locked_in",
                 "unknown": "unknown", "unreachable": "unknown"}
        for churn, lead in cases.items():
            self.assertEqual(leads.to_lead(row(churn), "Giosg")["status"], lead, churn)

    def test_switching_to_is_the_strongest_alternative(self):
        r = row("likely_switching", [rival("Zendesk", other_pages=["/shop"]),
                                     rival("Intercom", same_page=["/"], privacy="https://x.fi/privacy")])
        self.assertEqual(leads.to_lead(r, "Giosg")["switching_to"], "Intercom")

    def test_no_switching_to_for_weak_signals(self):
        r = row("worth_a_look", [rival("Zendesk", other_pages=["/shop"])])
        self.assertIsNone(leads.to_lead(r, "Giosg")["switching_to"])

    def test_competitor_vanished_since_last_check_is_leaving(self):
        r = row("on_competitor", [rival("Intercom", same_page=["/"])], ours=False, dropped=True)
        self.assertEqual(leads.to_lead(r, "Giosg")["status"], "leaving")

    def test_timeline_for_another_product_is_ignored(self):
        self.assertIsNone(leads.to_lead(row("healthy", timeline={"product": "Intercom"}), "Giosg")["timeline"])
        self.assertIsNotNone(leads.to_lead(row("healthy", timeline={"product": "Giosg"}), "Giosg")["timeline"])


class FindLeadsTest(unittest.TestCase):
    def test_hottest_first_with_summary(self):
        report = {"customers": [row("healthy", site="a.fi"), row("possibly_trialling", site="b.fi"),
                                row("likely_switching", [rival("Intercom", same_page=["/"])], site="c.fi")]}
        with mock.patch.object(leads.cw, "churn_report", return_value=report) as cr:
            rep = leads.find_leads("Giosg", ["a.fi", "b.fi", "c.fi"])
        cr.assert_called_once_with(["a.fi", "b.fi", "c.fi"], "Giosg", record=False)
        self.assertEqual([l["site"] for l in rep["leads"]], ["c.fi", "b.fi", "a.fi"])
        self.assertEqual(rep["summary"], {"leaving": 1, "trialling": 1, "locked_in": 1})


class CompetitorCustomersTest(unittest.TestCase):
    def test_customers_without_a_domain_are_left_out(self):
        resolved = [{"name": "A", "domain": "a.fi"}, {"name": "B", "domain": None, "verdict": "error", "error": "x"}]
        with mock.patch.object(leads.st, "resolve_customers", return_value=resolved):
            self.assertEqual(leads.competitor_customers("https://giosg.com"), [{"name": "A", "domain": "a.fi"}])


if __name__ == "__main__":
    unittest.main()
