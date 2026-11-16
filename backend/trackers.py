"""Tracker and consent-tool definitions for the consent check (backend/consent.py).

Each tracker lists regexes matched against a request URL (lower-case, scheme stripped):
  send   the request transmits data about the visit (a beacon, pixel or collect call)
  load   the request only loads the tracker's script (the visitor's IP still reaches the vendor)
and cookie-name regexes for the cookies it sets. `note` explains a known nuance.

Consent tools are never violations; they're how a site asks for consent.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlsplit

TRACKERS: dict[str, dict] = {
    "Google Analytics": {
        "category": "analytics",
        # /g/collect?v=2 and /gtag/js?id=G- also match server-side tagging on the site's own domain
        "send": [r"google-analytics\.com/(g/|j/)?collect", r"/g/collect\?v=2"],
        "load": [r"googletagmanager\.com/gtag/js", r"google-analytics\.com/analytics\.js", r"/gtag/js\?id=g-"],
        "cookies": [r"^_ga($|_)", r"^_gid$", r"^_gat", r"^FPID$", r"^FPLC$"],
        "domains": ["google-analytics.com", "analytics.google.com", "googletagmanager.com"],
    },
    "Google Ads": {
        "category": "advertising",
        "send": [r"googleads\.g\.doubleclick\.net/pagead", r"googleadservices\.com/pagead/conversion/",
                 r"google\.[a-z.]+/pagead/1p-", r"google\.[a-z.]+/(ccm|rmkt|gmp)/", r"doubleclick\.net/activity",
                 r"googlesyndication\.com/(pagead|ccm)/"],
        "load": [r"googleadservices\.com/pagead/conversion_async\.js"],
        "cookies": [r"^_gcl_", r"^IDE$", r"^test_cookie$", r"^FPAU$", r"^FPGCL"],
    },
    "Meta Pixel": {
        "category": "advertising",
        "send": [r"facebook\.com/tr[/?]"],
        "load": [r"connect\.facebook\.net/.*/fbevents\.js", r"connect\.facebook\.net/signals/"],
        "cookies": [r"^_fbp$", r"^fr$"],
    },
    "LinkedIn Insight": {
        "category": "advertising",
        "send": [r"px\.ads\.linkedin\.com", r"linkedin\.com/px/"],
        "load": [r"snap\.licdn\.com/li\.lms-analytics"],
        "cookies": [r"^li_sugr$", r"^bcookie$", r"^lidc$", r"^UserMatchHistory$", r"^AnalyticsSyncHistory$"],
    },
    "TikTok Pixel": {
        "category": "advertising",
        "send": [r"analytics\.tiktok\.com/api/"],
        "load": [r"analytics\.tiktok\.com/i18n/pixel"],
        "cookies": [r"^_ttp$"],
    },
    "X (Twitter) Ads": {
        "category": "advertising",
        "send": [r"t\.co/i/adsct", r"analytics\.twitter\.com", r"ads-api\.twitter\.com"],
        "load": [r"static\.ads-twitter\.com"],
        "cookies": [r"^personalization_id$", r"^muc_ads$"],
    },
    "Microsoft Ads": {
        "category": "advertising",
        "send": [r"bat\.bing\.com/action"],
        "load": [r"bat\.bing\.com/bat\.js"],
        "cookies": [r"^_uetsid$", r"^_uetvid$", r"^MUID$"],
    },
    "Snap Pixel": {
        "category": "advertising",
        "send": [r"tr\.snapchat\.com"],
        "load": [r"sc-static\.net/scevent"],
        "cookies": [r"^_scid"],
    },
    "Hotjar": {
        "category": "session recording",
        "send": [r"in\.hotjar\.com", r"content\.hotjar\.io", r"metrics\.hotjar\.io"],
        "load": [r"static\.hotjar\.com"],
        "cookies": [r"^_hj"],
    },
    "Microsoft Clarity": {
        "category": "session recording",
        "send": [r"clarity\.ms/collect"],
        "load": [r"clarity\.ms/tag/", r"clarity\.ms/s/"],
        "cookies": [r"^_clck$", r"^_clsk$", r"^CLID$"],
    },
    "HubSpot": {
        "category": "marketing",
        "send": [r"track(-[a-z0-9]+)?\.hubspot\.com/__pt", r"forms\.hscollectedforms\.net"],
        "load": [r"js\.hs-analytics\.net", r"js\.hs-scripts\.com", r"js\.hsadspixel\.net"],
        "cookies": [r"^__hstc$", r"^hubspotutk$", r"^__hssc$"],
    },
    "AudienceProject": {
        "category": "advertising",
        "send": [r"dnt-userreport\.com/hit", r"userreport\.com/hit"],
        "load": [r"dnt-userreport\.com/.*launcher", r"cdn\.userreport\.com"],
        "cookies": [],
    },
    "Prebid ad auction": {
        "category": "advertising",
        "send": [r"/openrtb2/auction", r"prebid-server"],
        "load": [r"prebid[^/]*\.js"],
        "cookies": [],
    },
    "Adform": {
        "category": "advertising",
        "send": [r"track\.adform\.net", r"a2\.adform\.net"],
        "load": [r"s2\.adform\.net"],
        "cookies": [],
    },
    "Exactag": {
        "category": "advertising",
        "send": [r"exactag\.com"],
        "load": [],
        "cookies": [],
    },
    "TVSquared": {
        "category": "advertising",
        "send": [r"tvsquared\.com"],
        "load": [],
        "cookies": [],
    },
    "CrossEngage": {
        "category": "marketing",
        "send": [r"crossengage\.io"],
        "load": [],
        "cookies": [],
    },
    "Sleeknote": {
        "category": "marketing",
        "send": [r"analytics\.sleeknote\.com"],
        "load": [r"sleeknotecustomerscripts\.sleeknote\.com"],
        "cookies": [],
    },
    "Contentsquare": {
        "category": "session recording",
        "send": [r"contentsquare\.net", r"c\.az\.contentsquare"],
        "load": [r"t\.contentsquare\.net/uxa/"],
        "cookies": [r"^_cs_"],
    },
    "Matomo": {
        "category": "analytics",
        "send": [r"/matomo\.php", r"/piwik\.php"],
        "load": [r"/matomo\.js", r"/piwik\.js"],
        "cookies": [r"^_pk_"],
        "note": "Matomo can be configured to run without cookies and without consent, so check its settings.",
    },
}

CONSENT_TOOLS: dict[str, list[str]] = {
    "Cookiebot": [r"consent(cdn)?\.cookiebot\.(com|eu)"],
    "OneTrust": [r"cdn\.cookielaw\.org", r"optanon", r"onetrust\.com"],
    "Usercentrics": [r"usercentrics\.eu"],
    "CookieInformation": [r"cookieinformation\.com"],
    "CookieYes": [r"cookieyes\.com"],
    "Didomi": [r"privacy-center\.org", r"didomi\.io"],
    "Sourcepoint": [r"sp-prod\.net", r"sourcepoint", r"privacy-mgmt\.com"],
    "Gravito": [r"gravito\.net"],
    "Quantcast Choice": [r"quantcast\.mgr\.consensu\.org", r"cmp\.quantcast\.com"],
    "consentmanager": [r"consentmanager\.net"],
}

# Companies that aren't trackers but can still receive what a visitor searches for. A site-search provider needs
# the term to run the search, so it's shown apart from advertising and analytics.
SERVICES: dict[str, dict] = {
    "Algolia": {"category": "site search", "hosts": ["algolia.net", "algolia.io", "algolianet.com"]},
    "Klevu": {"category": "site search", "hosts": ["klevu.com", "ksearchnet.com"]},
    "Doofinder": {"category": "site search", "hosts": ["doofinder.com"]},
    "Loop54": {"category": "site search", "hosts": ["loop54.com"]},
    "Elastic": {"category": "site search", "hosts": ["elastic-cloud.com", "found.io"]},
    "Giosg": {"category": "chat", "hosts": ["giosg.com"]},
    "Intercom": {"category": "chat", "hosts": ["intercom.io", "intercomcdn.com"]},
    "Zendesk": {"category": "chat", "hosts": ["zendesk.com", "zopim.com"]},
    "AddSearch": {"category": "site search", "hosts": ["addsearch.com"]},
    "Rek.ai": {"category": "site search", "hosts": ["rekai.se"]},
    "LiveChat": {"category": "chat", "hosts": ["livechatinc.com"]},
    "Trustpilot": {"category": "reviews", "hosts": ["trustpilot.com"]},
    "New Relic": {"category": "site monitoring", "hosts": ["nr-data.net", "newrelic.com"]},
    "Azure Application Insights": {"category": "site monitoring", "hosts": ["applicationinsights.azure.com"]},
    "Monsido": {"category": "site monitoring", "hosts": ["monsido.com"]},
    "Emarsys": {"category": "marketing", "hosts": ["scarabresearch.com", "emarsys.net"]},
    "Brevo": {"category": "marketing", "hosts": ["brevo.com", "sendinblue.com"]},
    "Frosmo": {"category": "personalisation", "hosts": ["frosmo.com"]},
    "Kameleoon": {"category": "personalisation", "hosts": ["kameleoon.io", "kameleoon.eu"]},
    "AB Tasty": {"category": "personalisation", "hosts": ["abtasty.com"]},
    "Rebuy": {"category": "personalisation", "hosts": ["rebuyengine.com"]},
    "Nosto": {"category": "personalisation", "hosts": ["nosto.com"]},
    "Dynamic Yield": {"category": "personalisation", "hosts": ["dynamicyield.com"]},
}

_TRACKER_RX = {name: {k: [re.compile(p) for p in t[k]] for k in ("send", "load", "cookies")}
               for name, t in TRACKERS.items()}
_CONSENT_RX = {name: [re.compile(p) for p in ps] for name, ps in CONSENT_TOOLS.items()}


def _bare(url: str) -> str:
    return re.sub(r"^https?://", "", url.lower())


def consent_mode_denied(url: str) -> bool:
    """Google Consent Mode: gcs=G100 means analytics and ads storage are denied (a cookieless ping)."""
    return parse_qs(urlsplit(url).query).get("gcs", [""])[0] == "G100"


def classify_request(url: str) -> Optional[dict]:
    """{"tracker", "category", "kind": send|load|ping, "own_domain"} for a tracker request, else None.
    "ping" is a Google request sent with consent denied (Consent Mode): no cookies, debated legally.
    "own_domain" is True when the call goes through the site's own server (server-side tagging)."""
    bare = _bare(url)
    for name, rx in _TRACKER_RX.items():
        for kind in ("send", "load"):
            if any(r.search(bare) for r in rx[kind]):
                if kind == "send" and name.startswith("Google") and consent_mode_denied(url):
                    kind = "ping"
                host = urlsplit(url).netloc.lower()
                domains = TRACKERS[name].get("domains")
                own = bool(domains) and not any(host.endswith(d) for d in domains)
                return {"tracker": name, "category": TRACKERS[name]["category"], "kind": kind, "own_domain": own}
    return None


def classify_cookie(name: str) -> Optional[str]:
    """The tracker that sets a cookie with this name, else None."""
    for tracker, rx in _TRACKER_RX.items():
        if any(r.search(name) for r in rx["cookies"]):
            return tracker
    return None


def recipient(url: str) -> dict:
    """Who receives a request: {"name", "category", "own_domain"}. Unknown companies are named by host, not hidden."""
    hit = classify_request(url)
    if hit:
        return {"name": hit["tracker"], "category": hit["category"], "own_domain": hit["own_domain"]}
    host = urlsplit(url).netloc.lower().split(":")[0]
    for name, svc in SERVICES.items():
        if any(host == h or host.endswith("." + h) for h in svc["hosts"]):
            return {"name": name, "category": svc["category"], "own_domain": False}
    tool = consent_tool(url)
    if tool:
        return {"name": tool, "category": "consent tool", "own_domain": False}
    return {"name": host[4:] if host.startswith("www.") else host, "category": "other company", "own_domain": False}


def consent_tool(url: str) -> Optional[str]:
    bare = _bare(url)
    return next((name for name, rx in _CONSENT_RX.items() if any(r.search(bare) for r in rx)), None)
