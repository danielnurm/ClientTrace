"""Offline tests for the month-by-month switch timeline and its chart.

Run:  .venv/bin/python -m unittest discover -s tests -t .
"""
import unittest

from backend import switch_timeline as stl
from frontend import switch_chart as sc


def months(*spec):
    """spec: (month, class, vendors) tuples → timeline months."""
    return [{"month": m, "class": c, "vendors": v, "snapshots": [{"page": "/", "url": f"https://web.archive.org/{m}",
                                                                  "products": v}] if c != stl.NO_SNAPSHOT else [],
             "inferred": False} for m, c, v in spec]


class ClassifyTest(unittest.TestCase):
    def test_classes(self):
        c = stl.classify
        self.assertEqual(c(["Giosg"], "Giosg", False), stl.OURS_ONLY)
        self.assertEqual(c(["Giosg", "Intercom"], "Giosg", False), stl.BOTH)
        self.assertEqual(c(["Intercom"], "Giosg", False), stl.COMPETITOR_ONLY)
        self.assertEqual(c(["Hotjar"], "Giosg", False), stl.NONE_DETECTED)  # analytics isn't a chat rival
        self.assertEqual(c(None, "Giosg", False), stl.NO_SNAPSHOT)

    def test_tag_manager_hidden_never_claims_competitor_only(self):
        # the Fennia case: Giosg loads through Tag Manager, the archive only sees Salesforce chat
        self.assertEqual(stl.classify(["Salesforce chat"], "Giosg", True), stl.COMPETITOR_OURS_HIDDEN)
        self.assertEqual(stl.classify([], "Giosg", True), stl.OURS_HIDDEN)


class MonthsTest(unittest.TestCase):
    def test_month_range(self):
        r = stl.month_range("2026-02", 4)
        self.assertEqual(r, ["2025-11", "2025-12", "2026-01", "2026-02"])

    def test_refine_only_where_class_changes(self):
        sampled = {"2025-01": stl.OURS_ONLY, "2025-04": stl.OURS_ONLY, "2025-07": stl.BOTH}
        available = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06", "2025-07"]
        self.assertEqual(stl.months_to_refine(sampled, available), ["2025-05", "2025-06"])


class DeriveTest(unittest.TestCase):
    def test_completed_switch_with_warning_time(self):
        d = stl.derive(months(("2025-01", stl.OURS_ONLY, ["Giosg"]), ("2025-02", stl.BOTH, ["Giosg", "Intercom"]),
                              ("2025-05", stl.BOTH, ["Giosg", "Intercom"]), ("2025-06", stl.COMPETITOR_ONLY, ["Intercom"])),
                       "Giosg")
        self.assertEqual(d["first_competitor_seen"], "2025-02")
        self.assertEqual(d["ours_last_seen"], "2025-05")
        self.assertEqual(d["switch"], {"from": "Giosg", "to": ["Intercom"], "window": ["2025-05", "2025-06"]})
        self.assertEqual(d["warning_months"], 3)

    def test_hidden_ours_is_never_a_switch(self):
        d = stl.derive(months(("2025-01", stl.OURS_HIDDEN, []),
                              ("2025-02", stl.COMPETITOR_OURS_HIDDEN, ["Salesforce chat"])), "Giosg")
        self.assertIsNone(d["switch"])
        self.assertIsNone(d["warning_months"])
        self.assertTrue(d["ours_hidden"])

    def test_inferred_months_dont_move_the_dates(self):
        ms = months(("2025-01", stl.OURS_ONLY, ["Giosg"]), ("2025-04", stl.COMPETITOR_ONLY, ["Genesys"]))
        filler = {**ms[0], "month": "2025-03", "inferred": True, "snapshots": []}
        d = stl.derive([ms[0], filler, ms[1]], "Giosg")
        self.assertEqual(d["switch"]["window"], ["2025-01", "2025-04"])

    def test_no_snapshots(self):
        d = stl.derive([{"month": "2025-01", "class": stl.NO_SNAPSHOT, "vendors": [], "snapshots": []}], "Giosg")
        self.assertEqual((d["switch"], d["first_competitor_seen"], d["changed"]), (None, None, False))

    def test_assemble_fills_gaps_between_agreeing_months_only(self):
        window = ["2025-01", "2025-02", "2025-03"]
        fetched = {"2025-01": [{"page": "/", "date": "2025-01-10", "url": "u1", "products": ["Giosg"]}],
                   "2025-03": [{"page": "/", "date": "2025-03-10", "url": "u3", "products": ["Giosg"]}]}
        live = {"checked_at": "2025-03-14T00:00:00+00:00", "products": ["Giosg"], "found_in": {"Giosg": "html"}}
        tl = stl.assemble("x.fi", "Giosg", window, fetched, live, False, ["https://www.x.fi/"])
        self.assertEqual([(m["month"], m["class"], m["inferred"]) for m in tl["months"]],
                         [("2025-01", stl.OURS_ONLY, False), ("2025-02", stl.OURS_ONLY, True), ("2025-03", stl.OURS_ONLY, False)])


class ChartTest(unittest.TestCase):
    def entry(self, site, status, *spec):
        ms = months(*spec)
        return {"site": site, "status": status,
                "timeline": {"months": ms, "summary": stl.derive(ms, "Giosg"),
                             "live": {"checked_at": "2026-11-14T12:00:00+00:00"}}}

    def switched(self):
        return self.entry("a.fi", "on_competitor", ("2026-01", stl.OURS_ONLY, ["Giosg"]),
                          ("2026-02", stl.BOTH, ["Giosg", "Intercom"]), ("2026-05", stl.BOTH, ["Giosg", "Intercom"]),
                          ("2026-06", stl.COMPETITOR_ONLY, ["Intercom"]))

    def test_segments_merge_runs(self):
        segs = sc.segments(self.switched()["timeline"]["months"])
        self.assertEqual([(s["class"], s["start"], s["end"]) for s in segs],
                         [(stl.OURS_ONLY, "2026-01", "2026-01"), (stl.BOTH, "2026-02", "2026-05"),
                          (stl.COMPETITOR_ONLY, "2026-06", "2026-06")])

    def test_switch_label(self):
        self.assertEqual(sc.switch_text(self.switched()["timeline"]["summary"], "Giosg"),
                         "Giosg → Intercom · May–Jun 2026 · 3 mo warning")

    def test_headline_counts_only_real_switches(self):
        quiet = self.entry("b.fi", "healthy", ("2026-01", stl.OURS_ONLY, ["Giosg"]))
        self.assertEqual(sc.headline([self.switched(), quiet], "Giosg"),
                         "In 1 of 1 completed switch the competitor appeared on the site 3+ months before Giosg was removed.")
        self.assertEqual(sc.headline([quiet], "Giosg"), "No completed switches found in the archived period.")

    def test_figure_rows_in_given_order(self):
        quiet = self.entry("b.fi", "healthy", ("2026-01", stl.OURS_ONLY, ["Giosg"]))
        fig = sc.figure([self.switched(), quiet], "Giosg", {"on_competitor": "⚫", "healthy": "🟢"})
        self.assertEqual(list(fig.layout.yaxis.categoryarray), ["⚫ a.fi", "🟢 b.fi"])
        self.assertEqual(fig.layout.height, 90 + sc.ROW_HEIGHT * 2)
        self.assertEqual(len(fig.layout.annotations), 2)  # the switch label + "Last live check"

    def test_legend_lists_only_present_classes(self):
        self.assertEqual(sc.legend_classes([self.switched()]), [stl.OURS_ONLY, stl.BOTH, stl.COMPETITOR_ONLY])


if __name__ == "__main__":
    unittest.main()
