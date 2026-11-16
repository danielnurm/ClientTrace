"""Offline tests for the web API (endpoint functions called directly, no server, no browser).

Run:  .venv/bin/python -m unittest discover -s tests -t .
"""
import os
import socket
import unittest
from unittest import mock

from fastapi import HTTPException

from api import main

SURVEY = {"summary": {"sites": 1}, "sites": [{"site": "de-pharmacy-a", "verdict": "sent_before_consent"}]}
LIVE = {"DEMO_MODE": "", "ALLOW_LIVE": "1"}


def _resolves_to(*ips):
    return mock.patch.object(main.socket, "getaddrinfo",
                             return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips])


class SurveyApiTest(unittest.TestCase):
    def test_survey_and_one_site(self):
        with mock.patch.object(main, "load_survey", return_value=SURVEY):
            self.assertEqual(main.get_survey()["summary"]["sites"], 1)
            self.assertEqual(main.get_site("de-pharmacy-a")["verdict"], "sent_before_consent")
            with self.assertRaises(HTTPException) as e:
                main.get_site("nope")
        self.assertEqual(e.exception.status_code, 404)

    def test_broken_survey_hides_the_error_detail(self):
        with mock.patch.object(main.search_leaks, "SURVEY_FILE") as f:
            f.read_text.side_effect = OSError("/secret/path/leaks_survey.json")
            with self.assertRaises(HTTPException) as e:
                main.load_survey()
        self.assertEqual(e.exception.status_code, 503)
        self.assertNotIn("/secret", e.exception.detail)


class LiveCheckTest(unittest.TestCase):
    def test_off_by_default_and_in_demo_mode(self):
        for env in ({"DEMO_MODE": "", "ALLOW_LIVE": ""}, {"DEMO_MODE": "1", "ALLOW_LIVE": "1"}):
            with mock.patch.dict(os.environ, env), mock.patch.object(main.search_leaks, "check_search") as live:
                with self.assertRaises(HTTPException) as e:
                    main.post_check("a.fi", "masennus")
            self.assertEqual(e.exception.status_code, 403)
            live.assert_not_called()

    def test_runs_on_a_public_host_and_hides_failures(self):
        with mock.patch.dict(os.environ, LIVE), _resolves_to("93.184.216.34"), \
                mock.patch.object(main.search_leaks, "check_search", return_value={"site": "a.fi"}) as live:
            self.assertFalse(main.post_check(" https://www.A.fi/ ", " masennus ")["demo"])
        live.assert_called_once_with("www.a.fi", "masennus")
        with mock.patch.dict(os.environ, LIVE), _resolves_to("93.184.216.34"), \
                mock.patch.object(main.search_leaks, "check_search", side_effect=RuntimeError("boom at /etc")):
            with self.assertRaises(HTTPException) as e:
                main.post_check("a.fi", "x")
        self.assertEqual(e.exception.status_code, 502)
        self.assertNotIn("boom", e.exception.detail)

    def test_term_length(self):
        with mock.patch.dict(os.environ, LIVE):
            for term in ("", "   ", "x" * 61):
                with self.assertRaises(HTTPException) as e:
                    main.post_check("a.fi", term)
                self.assertEqual(e.exception.status_code, 422)


class PublicHostTest(unittest.TestCase):
    def test_rejects_internal_targets(self):
        cases = {
            "localhost": None, "http://shop.fi": None, "127.0.0.1": None, "169.254.169.254": None,
            "printer.local": None, "intranet": None,
            "evil.example": "127.0.0.1", "meta.example": "169.254.169.254", "lan.example": "10.0.0.5",
            "mixed.example": ("93.184.216.34", "192.168.1.2"),
        }
        for site, ips in cases.items():
            ips = (ips,) if isinstance(ips, str) else ips or ("93.184.216.34",)
            with _resolves_to(*ips), self.assertRaises(ValueError, msg=site):
                main.public_host(site)

    def test_accepts_a_public_site(self):
        with _resolves_to("93.184.216.34"):
            self.assertEqual(main.public_host("Example-Apotheke.de"), "example-apotheke.de")

    def test_unresolvable_name(self):
        with mock.patch.object(main.socket, "getaddrinfo", side_effect=socket.gaierror("nope")):
            with self.assertRaises(ValueError):
                main.public_host("no-such-site.example")


if __name__ == "__main__":
    unittest.main()
