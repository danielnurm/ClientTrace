"""End-to-end test of the search check in a real headless browser, against the local fake pharmacy
(demo/search_site/server.py): no internet needed.

Skipped when Playwright's Chromium isn't installed, unless REQUIRE_BROWSER=1 (set in CI), where it must run.
Install it with: .venv/bin/python -m playwright install chromium
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "demo" / "search_site"))
import server as fake_site  # noqa: E402

from backend import leaks as lk  # noqa: E402


def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception as e:  # not installed: skip locally, fail in CI (see setUpClass)
        print(f"Chromium unavailable: {type(e).__name__}", file=sys.stderr)
        return False


class SearchCheckInBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _chromium_ok():
            if os.getenv("REQUIRE_BROWSER") == "1":
                raise RuntimeError("Chromium is required here (REQUIRE_BROWSER=1)")
            raise unittest.SkipTest("Playwright Chromium not installed")
        cls.server = fake_site.start()
        cls.saved = (lk.LOAD_WAIT_MS, lk.BANNER_WAIT_MS, lk.WAIT_MS)
        lk.LOAD_WAIT_MS, lk.BANNER_WAIT_MS, lk.WAIT_MS = 300, 400, 1500

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()
            cls.server.server_close()
            lk.LOAD_WAIT_MS, lk.BANNER_WAIT_MS, lk.WAIT_MS = cls.saved

    def check(self, mode: str) -> dict:
        url = f"http://127.0.0.1:{self.server.server_port}/{mode}/"
        return lk.check_search("127.0.0.1", "raskaustesti", runs=1, base_url=url, allow_private=True)

    def test_verdict_per_behaviour(self):
        # dead-search: the form only reloads the home page, so "nothing sent" would be a false all-clear
        expected = {"leak": "sent_before_consent", "clean": "sent_after_consent",
                    "ignores-reject": "sent_after_reject", "dead-search": "unknown"}
        for mode, verdict in expected.items():
            with self.subTest(mode=mode):
                row = self.check(mode)
                self.assertEqual(row["verdict"], verdict, row)

    def test_evidence_names_the_recipient_and_field(self):
        row = self.check("leak")
        rec = row["before"]["recipients"][0]
        self.assertEqual(rec["name"], "Google Analytics")
        self.assertIn("raskaustesti", rec["evidence"][0]["snippet"])
        self.assertEqual(row["after"]["answered_via"], "button")
        self.assertTrue(row["browser"].startswith("Chromium "))
        self.assertTrue(rec["counted"])

    def test_guard_blocks_private_addresses_in_the_browser(self):
        url = f"http://127.0.0.1:{self.server.server_port}/leak/"
        row = lk.check_search("127.0.0.1", "raskaustesti", runs=1, base_url=url)  # guard on, as in production
        self.assertEqual(row["before"]["status"], "error", row["before"])
        self.assertEqual(row["verdict"], "unknown")


if __name__ == "__main__":
    unittest.main()
