"""Vercel serverless: GET /api/register?name=<name>"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from _shared import respond, create_user


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        names = qs.get("name", [])
        if not names or not names[0].strip():
            respond(self, 400, {"error": "name is required"})
            return
        name = names[0].strip()[:64]
        user = create_user(name)
        respond(self, 200, {"api_key": user["api_key"], "name": user["name"]})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass
