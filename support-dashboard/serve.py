"""Local server for the support-performance dashboard - a live Creatio pull behind Refresh.

Run:  python3 serve.py          (Python 3.11+, standard library only - no pip install)
Then open http://localhost:8791

Endpoints:
  GET  /                -> index.html (the dashboard)
  GET  /api/status      -> whether Creatio credentials are configured
  GET  /api/metrics     -> live pull from Creatio, aggregated JSON (?from=&to=&team=)
  POST /api/config      -> set Creatio credentials (validated by a real login; held in memory only)

Credentials are entered in the UI and held ONLY in this process's memory for the session
(never written to disk, never logged, cleared on restart). The browser only ever sees the
aggregate numbers. Falls back to a local .env if the owner has one.
"""

from __future__ import annotations

import json
import os
import re
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import metrics

HERE = Path(__file__).resolve().parent
PORT = 8791

# Creds entered via the UI, held ONLY in this process's memory (never written to disk / logged).
_creds: dict | None = None

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clean_date(v: str | None) -> str | None:
    v = (v or "").strip()
    return v if _DATE_RE.match(v) else None


def _have_creds() -> bool:
    if _creds:
        return True
    try:
        metrics.load_env()
        return True
    except Exception:
        return False


def _default_range() -> tuple[str, str]:
    """Month-to-date by default (matches how the spreadsheet is run each month)."""
    today = date.today()
    return today.replace(day=1).isoformat(), today.isoformat()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep the console quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        q = self.path.split("?", 1)[1] if "?" in self.path else ""
        import urllib.parse
        params = urllib.parse.parse_qs(q)

        if path == "/api/status":
            self._json(200, {"configured": _have_creds(), "default_range": _default_range()})
            return

        if path == "/api/metrics":
            if not _have_creds():
                self._json(400, {"error": "no_credentials"})
                return
            df = _clean_date(params.get("from", [""])[0])
            dt = _clean_date(params.get("to", [""])[0])
            if not (df and dt):
                df, dt = _default_range()
            team_only = params.get("team", ["1"])[0] != "0"
            level = (params.get("level", ["all"])[0] or "all").strip()
            if level not in ("all", "1", "2", "3"):
                level = "all"
            try:
                print(f"Pulling metrics from Creatio (from={df} to={dt} team_only={team_only} "
                      f"level={level}) ...")
                data = metrics.collect(_creds, df, dt, team_only, None if level == "all" else level)
                t = data["totals"]
                print(f"  {t['closed']} closed, {t['survey_responses']} surveys, "
                      f"adoption {t['adoption_rate']}")
                self._json(200, data)
            except Exception as e:
                traceback.print_exc()
                self._json(500, {"error": str(e)})
            return

        # static files (index.html and any siblings)
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (HERE / rel).resolve()
        if (HERE not in f.parents and f != HERE / rel) or not f.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = {".html": "text/html", ".js": "application/javascript",
                 ".css": "text/css", ".json": "application/json"}.get(f.suffix,
                                                                       "application/octet-stream")
        self._send(200, f.read_bytes(), ctype + "; charset=utf-8")

    def do_POST(self) -> None:
        global _creds
        if self.path != "/api/config":
            self._json(404, {})
            return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or "{}")
        url = (body.get("url") or "").strip().rstrip("/")
        user = (body.get("user") or "").strip()
        pw = body.get("pass") or ""
        sat = (body.get("satisfaction_field") or "").strip()
        if not (url and user and pw):
            self._json(400, {"error": "URL, user and password are all required."})
            return
        # Validate by doing a real login before we store anything.
        try:
            metrics.login(url, user, pw)
        except Exception as e:
            self._json(400, {"error": f"Login failed: {e}"})
            return
        _creds = {"CREATIO_URL": url, "CREATIO_USER": user, "CREATIO_PASS": pw}
        if sat:
            _creds["CREATIO_SATISFACTION_FIELD"] = sat
        self._json(200, {"ok": True})


def main() -> None:
    # 127.0.0.1 only by default: this dashboard reads PROD support data (customer + case info).
    # Set HOST=0.0.0.0 to expose on your LAN; never put it behind a public tunnel without auth.
    host = os.environ.get("HOST", "127.0.0.1")
    srv = ThreadingHTTPServer((host, PORT), Handler)
    where = "http://localhost" if host == "127.0.0.1" else "http://<this-PC-LAN-IP>"
    print(f"Support dashboard: {where}:{PORT}  (bind {host}, Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
