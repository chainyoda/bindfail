"""Vercel serverless: GET /api/submissions  (requires auth, returns caller's submissions)"""
from http.server import BaseHTTPRequestHandler
from _shared import respond, require_auth, get_submissions


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        user = require_auth(self)
        if not user:
            return
        all_subs = get_submissions()
        mine = [s for s in all_subs if s.get("user") == user["name"]]
        mine.sort(key=lambda s: s["submitted_at"], reverse=True)
        respond(self, 200, {"submissions": mine})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass
