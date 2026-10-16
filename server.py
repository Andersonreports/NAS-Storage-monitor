#!/usr/bin/env python3
"""Office dashboard server (stdlib only). Serves index.html plus live data.json from the database.

  python3 server.py            # http://0.0.0.0:8080 (see config.json)
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from db import BASE_DIR, build_data, load_config

CFG = load_config()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path == "/data.json":
            data = build_data(CFG)
            return self._send(200, json.dumps(data, separators=(",", ":")).encode(), "application/json")
        self._send(404, b"not found", "text/plain")

    def log_message(self, fmt, *args):
        pass


def main():
    host = CFG.get("server", {}).get("host", "0.0.0.0")
    port = int(os.environ.get("PORT", CFG.get("server", {}).get("port", 8080)))
    print(f"NAS storage dashboard on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
