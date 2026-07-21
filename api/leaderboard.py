"""
Vercel serverless function: GET /api/leaderboard

Proxies to the Railway judge server. Falls back to empty data if unreachable.
"""

import json
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler

JUDGE_URL = "https://bindfail.up.railway.app"

EMPTY_RESPONSE = {
    "leaderboard": [],
    "history": [],
    "best_score": None,
    "total_submissions": 0,
}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = self._fetch_leaderboard()
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=30")
        self.end_headers()
        self.wfile.write(body)

    def _fetch_leaderboard(self) -> dict:
        try:
            req = urllib.request.Request(
                f"{JUDGE_URL}/leaderboard",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read())
        except Exception:
            return EMPTY_RESPONSE

    def log_message(self, *args):
        pass
