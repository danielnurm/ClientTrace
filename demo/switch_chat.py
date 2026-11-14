"""Live demo: a fake customer site whose chat widget you switch during the pitch.

Terminal 1 (serve the fake customer site):
    .venv/bin/python -m http.server 8765 -d demo/customer_site
Terminal 2 (ClientTrace watches it):
    .venv/bin/python -m backend.site_tech watch http://localhost:8765 --interval 3
Terminal 3 (the "customer" switches vendor):
    .venv/bin/python demo/switch_chat.py intercom      # or giosg | zendesk | none

The page only contains the vendors' embed tags (with placeholder ids); it is
never opened in a browser, ClientTrace just reads the HTML like any real site.
"""
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent / "customer_site" / "index.html"

SNIPPETS = {
    "giosg": '<script>(function(w,t,f){var s="script",o="_giosg",h="https://service.giosg.com",e,n;'
             'e=t.createElement(s);e.async=1;e.src=h+"/live2/"+f;}(window,document,"demo-org-id"));</script>',
    "intercom": '<script>window.intercomSettings={app_id:"demo123"};</script>\n'
                '<script async src="https://widget.intercom.io/widget/demo123"></script>',
    "zendesk": '<script id="ze-snippet" src="https://static.zdassets.com/ekr/snippet.js?key=demo-key"></script>',
    "none": "",
}

PAGE = """<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<title>Demo Oy – asiakassivu</title>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-DEMO"></script>
</head>
<body>
<h1>Demo Oy</h1>
<p>Fake customer website for the ClientTrace live demo. Chat vendor: {vendor}.</p>
{snippet}
</body>
</html>
"""


def switch(vendor: str) -> None:
    if vendor not in SNIPPETS:
        sys.exit(f"unknown vendor {vendor!r}, choose from: {', '.join(SNIPPETS)}")
    SITE.parent.mkdir(parents=True, exist_ok=True)
    SITE.write_text(PAGE.format(vendor=vendor, snippet=SNIPPETS[vendor]), encoding="utf-8")
    print(f"demo customer site now runs: {vendor}")


if __name__ == "__main__":
    switch(sys.argv[1] if len(sys.argv) > 1 else "giosg")
