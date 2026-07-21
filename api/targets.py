"""Vercel serverless function: GET /api/targets — returns targets inline."""

import json
from http.server import BaseHTTPRequestHandler

TARGETS = [
    {"id": "spike_rbd",  "name": "SARS-CoV-2 Spike RBD",  "pdb": "6M0J", "chain": "E", "description": "COVID-19 receptor binding domain",   "difficulty": "medium"},
    {"id": "pd1",        "name": "PD-1",                   "pdb": "4ZQK", "chain": "A", "description": "Cancer immune checkpoint",           "difficulty": "medium"},
    {"id": "her2",       "name": "HER2",                   "pdb": "1N8Z", "chain": "B", "description": "Breast cancer receptor",             "difficulty": "medium"},
    {"id": "tnf_alpha",  "name": "TNF-α",             "pdb": "1TNF", "chain": "A", "description": "Inflammatory disease target",        "difficulty": "hard"},
    {"id": "pcsk9",      "name": "PCSK9",                  "pdb": "2P4E", "chain": "A", "description": "Cholesterol regulation",             "difficulty": "medium"},
    {"id": "rsv_f",      "name": "RSV F protein site II",  "pdb": "4MMV", "chain": "A", "description": "Respiratory syncytial virus",        "difficulty": "medium"},
    {"id": "flu_ha",     "name": "Influenza H3 HA",        "pdb": "3LZG", "chain": "A", "description": "Influenza hemagglutinin",            "difficulty": "medium"},
    {"id": "egfr",       "name": "EGFR",                   "pdb": "1IVO", "chain": "A", "description": "Lung/colorectal cancer receptor",    "difficulty": "medium"},
]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"targets": TARGETS}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
