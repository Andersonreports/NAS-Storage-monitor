#!/usr/bin/env python3
"""Dashboard web server (stdlib only).

  python3 server.py            # serves http://0.0.0.0:8080 (see config.json)

API:
  GET /api/summary?days=90           NAS list, latest numbers, daily history
  GET /api/users?nas=X&day=Y         per-user usage on a day (+ change vs 1d / 7d / 30d)
  GET /api/user_history?nas=X&user=U&days=90
"""
import datetime as dt
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from db import BASE_DIR, connect, load_config

CFG = load_config()


def days_ago(day, n):
    return (dt.date.fromisoformat(day) - dt.timedelta(days=n)).isoformat()


def summary(conn, days):
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    out = []
    for nas in CFG["nas"]:
        name = nas["name"]
        rows = conn.execute(
            "SELECT day, total_bytes, used_bytes, free_bytes FROM nas_snapshot "
            "WHERE nas=? AND day>=? ORDER BY day", (name, since)).fetchall()
        latest = conn.execute(
            "SELECT * FROM nas_snapshot WHERE nas=? ORDER BY day DESC LIMIT 1", (name,)).fetchone()
        item = {"name": name, "path": nas["path"], "history": [dict(r) for r in rows], "latest": None}
        if latest:
            item["latest"] = dict(latest)
            item["users"] = conn.execute(
                "SELECT COUNT(*) FROM user_usage WHERE nas=? AND day=?", (name, latest["day"])).fetchone()[0]

            def used_on_or_before(d):
                r = conn.execute("SELECT day, used_bytes FROM nas_snapshot WHERE nas=? AND day<=? "
                                 "ORDER BY day DESC LIMIT 1", (name, d)).fetchone()
                return dict(r) if r else None

            item["prev"] = {k: used_on_or_before(days_ago(latest["day"], n))
                            for k, n in (("d1", 1), ("d7", 7), ("d30", 30))}
        out.append(item)
    return {"nas": out, "thresholds": CFG.get("thresholds", {"warning": 80, "critical": 90}),
            "today": dt.date.today().isoformat()}


def users(conn, nas, day):
    if not day:
        r = conn.execute("SELECT MAX(day) FROM user_usage WHERE nas=?", (nas,)).fetchone()
        day = r[0]
    if not day:
        return {"day": None, "days": [], "users": []}
    cur = {r["user"]: dict(r) for r in conn.execute(
        "SELECT user, bytes, files FROM user_usage WHERE nas=? AND day=?", (nas, day))}

    def snapshot_before(n):
        r = conn.execute("SELECT MAX(day) FROM user_usage WHERE nas=? AND day<=?",
                         (nas, days_ago(day, n))).fetchone()
        if not r[0]:
            return {}
        return {x["user"]: x["bytes"] for x in conn.execute(
            "SELECT user, bytes FROM user_usage WHERE nas=? AND day=?", (nas, r[0]))}

    for key, n in (("d1", 1), ("d7", 7), ("d30", 30)):
        prev = snapshot_before(n)
        for u, rec in cur.items():
            rec[key] = rec["bytes"] - prev[u] if prev and u in prev else None
    available = [r[0] for r in conn.execute(
        "SELECT DISTINCT day FROM user_usage WHERE nas=? ORDER BY day DESC", (nas,))]
    return {"day": day, "days": available,
            "users": sorted(cur.values(), key=lambda r: -r["bytes"])}


def user_history(conn, nas, user, days):
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    return {"user": user, "history": [dict(r) for r in conn.execute(
        "SELECT day, bytes, files FROM user_usage WHERE nas=? AND user=? AND day>=? ORDER BY day",
        (nas, user, since))]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(BASE_DIR, "dashboard.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            conn = connect(CFG["db"])
            try:
                days = int(q.get("days", 90))
                if u.path == "/api/summary":
                    return self._send(200, summary(conn, days))
                if u.path == "/api/users":
                    return self._send(200, users(conn, q["nas"], q.get("day")))
                if u.path == "/api/user_history":
                    return self._send(200, user_history(conn, q["nas"], q["user"], days))
            finally:
                conn.close()
            self._send(404, {"error": "not found"})
        except (KeyError, ValueError) as e:
            self._send(400, {"error": f"bad request: {e}"})

    def log_message(self, fmt, *args):
        pass


def main():
    host = CFG.get("server", {}).get("host", "0.0.0.0")
    port = int(os.environ.get("PORT", CFG.get("server", {}).get("port", 8080)))
    print(f"NAS storage dashboard on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
