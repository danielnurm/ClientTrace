"""A fake pharmacy with a cookie banner, a site search and a fake tracker, for testing and demoing the search check
offline. Three behaviours, one per path:

  /leak/            sends every search to the "tracker", banner or not
  /clean/           sends it only after the visitor accepts cookies
  /ignores-reject/  sends it after accept and after reject alike

The tracker lives on http://localhost:<port>/g/collect (the shape of a Google Analytics hit) while the shop is
served on http://127.0.0.1:<port>/, so the browser treats them as two different sites.

Run:  python demo/search_site/server.py 8766
Then: .venv/bin/python -c "from backend import leaks; import json; print(json.dumps(leaks.check_search(
          '127.0.0.1', 'raskaustesti', base_url='http://127.0.0.1:8766/leak/')['verdict']))"
"""
from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

MODES = ("leak", "clean", "ignores-reject")

HOME = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Demo Pharmacy</title></head><body>
<h1>Demo Pharmacy</h1>
<div id="banner"><p>We use cookies.</p>
<button id="onetrust-accept-btn-handler">Accept all</button>
<button id="onetrust-reject-all-handler">Reject all</button></div>
<form action="search" method="get"><input type="search" name="q"><button>Search</button></form>
<script>
for (const [id, value] of [["onetrust-accept-btn-handler", "yes"], ["onetrust-reject-all-handler", "no"]])
  document.getElementById(id).onclick = () => { localStorage.setItem("consent", value); document.getElementById("banner").remove() };
</script></body></html>"""

RESULTS = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Search</title></head><body>
<h1>Results for {term}</h1><p>3 products found.</p>
<script>
const consent = localStorage.getItem("consent");
const send = {{"leak": true, "clean": consent === "yes", "ignores-reject": consent !== null}}["{mode}"];
if (send) fetch("http://localhost:{port}/g/collect?v=2&en=search&ep.search_term=" + encodeURIComponent({term_js}),
                {{mode: "no-cors"}});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == "/g/collect":
            return self._send(204, "")
        mode, _, page = parts.path.strip("/").partition("/")
        if mode not in MODES:
            return self._send(404, "not found")
        if page == "search":
            term = parse_qs(parts.query).get("q", [""])[0]
            safe = term.replace("<", "&lt;").replace(">", "&gt;")
            term_js = '"' + term.replace("\\", "\\\\").replace('"', '\\"') + '"'
            return self._send(200, RESULTS.format(term=safe, mode=mode, port=self.server.server_port, term_js=term_js))
        return self._send(200, HOME)

    def _send(self, status: int, body: str):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # quiet: the checker's requests aren't interesting here
        pass


def start(port: int = 0) -> ThreadingHTTPServer:
    """Serve in a background thread; port 0 picks a free one (server.server_port)."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    srv = start(int(sys.argv[1]) if len(sys.argv) > 1 else 8766)
    print(f"Demo pharmacy on http://127.0.0.1:{srv.server_port}/{{{','.join(MODES)}}}/ (Ctrl+C to stop)")
    threading.Event().wait()
