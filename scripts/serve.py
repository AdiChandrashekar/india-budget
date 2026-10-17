"""Serve the site for development, without caching.

    python scripts/serve.py [port]

`python -m http.server` sends no Cache-Control, so browsers heuristically
cache the ES modules and keep serving a stale js/app.js after it changes on
disk — which looks exactly like a code change that did not work. This sends
no-store on everything instead.

It is a development convenience only. GitHub Pages serves the same files with
its own caching, and nothing in the site depends on these headers.
"""

from __future__ import annotations

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):      # quieter than the default
        if "404" in (fmt % args):
            sys.stderr.write("404 %s\n" % (args[0] if args else ""))


def main(argv) -> None:
    port = int(argv[0]) if argv else 8124
    handler = partial(NoCacheHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print("serving %s at http://127.0.0.1:%d (no-store)" % (ROOT.name, port))
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main(sys.argv[1:])
