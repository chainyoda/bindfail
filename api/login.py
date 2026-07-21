"""Vercel serverless: POST /api/login  body: {"api_key": "..."}"""
import json
from http.server import BaseHTTPRequestHandler
from _shared import respond, get_user


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            respond(self, 400, {"error": "invalid JSON"})
            return
        api_key = body.get("api_key", "").strip()
        user = get_user(api_key)
        if not user:
            respond(self, 401, {"error": "invalid api key"})
            return
        respond(self, 200, {"name": user["name"], "ok": True})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass
