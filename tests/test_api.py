"""Offline tests for the web API (endpoint functions called directly, no server).

Run:  .venv/bin/python -m unittest discover -s tests -t .
"""
import os
import unittest
from unittest import mock

from fastapi import HTTPException

from api import main

SNAPSHOT = {"competitor": "Giosg", "summary": {"trialling": 1}, "leads": [{"site": "fennia.fi", "status": "trialling"}]}


class DemoModeTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DEMO_MODE": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_leads_come_from_the_snapshot_without_network(self):
        with mock.patch.object(main, "load_snapshot", return_value=SNAPSHOT), \
                mock.patch.object(main.leads, "find_leads") as live:
            rep = main.get_leads()
        live.assert_not_called()
        self.assertTrue(rep["demo"])
        self.assertEqual(rep["leads"][0]["site"], "fennia.fi")

    def test_unknown_site_is_404(self):
        with mock.patch.object(main, "load_snapshot", return_value=SNAPSHOT):
            with self.assertRaises(HTTPException) as e:
                main.get_lead("nope.fi")
        self.assertEqual(e.exception.status_code, 404)


class LiveModeTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DEMO_MODE": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sites_are_split_and_default_to_demo_list(self):
        with mock.patch.object(main.leads, "find_leads", return_value={"leads": []}) as live:
            main.get_leads("Intercom", " a.fi, b.fi ,")
            main.get_leads("Giosg")
        self.assertEqual(live.call_args_list[0].args, ("Intercom", ["a.fi", "b.fi"]))
        self.assertEqual(live.call_args_list[1].args, ("Giosg", main.DEMO_SITES))

    def test_failure_is_a_clear_502(self):
        with mock.patch.object(main.leads, "find_leads", side_effect=RuntimeError("boom")):
            with self.assertRaises(HTTPException) as e:
                main.get_leads()
        self.assertEqual(e.exception.status_code, 502)
        self.assertIn("boom", e.exception.detail)


if __name__ == "__main__":
    unittest.main()
