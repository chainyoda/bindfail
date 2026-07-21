"""
Shared helpers for Vercel serverless functions.
Vercel runs each api/*.py as a separate function — this file is NOT a function
because it starts with underscore. Import it from other api/ files.
"""

import hashlib
import json
import os
import time
import uuid
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
from typing import Any

# ---------------------------------------------------------------------------
# Vercel KV (Redis) via REST API
# ---------------------------------------------------------------------------

def _kv_url() -> str:
    return os.environ.get("KV_REST_API_URL", "").rstrip("/")

def _kv_token() -> str:
    return os.environ.get("KV_REST_API_TOKEN", "")

def _kv_available() -> bool:
    return bool(_kv_url() and _kv_token())

def _kv_req(method: str, path: str, body: Any = None) -> Any:
    url = f"{_kv_url()}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {_kv_token()}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def kv_get(key: str) -> Any:
    if not _kv_available():
        return None
    result = _kv_req("GET", f"/get/{key}")
    return result.get("result")

def kv_set(key: str, value: Any) -> None:
    if not _kv_available():
        return
    encoded = json.dumps(value)
    _kv_req("POST", "/set", [key, encoded])

def kv_lpush(key: str, value: Any) -> None:
    if not _kv_available():
        return
    encoded = json.dumps(value)
    _kv_req("POST", "/lpush", [key, encoded])

def kv_lrange(key: str, start: int = 0, stop: int = -1) -> list:
    if not _kv_available():
        return []
    result = _kv_req("POST", "/lrange", [key, start, stop])
    items = result.get("result") or []
    return [json.loads(i) for i in items]

# ---------------------------------------------------------------------------
# Convenience wrappers over the KV schema
# ---------------------------------------------------------------------------

def get_user(api_key: str):
    raw = kv_get(f"user:{api_key}")
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw

def create_user(name: str) -> dict:
    api_key = "bf_" + uuid.uuid4().hex
    user = {"name": name, "id": uuid.uuid4().hex, "api_key": api_key}
    kv_set(f"user:{api_key}", user)
    return user

def append_submission(sub: dict) -> None:
    kv_lpush("submissions", sub)

def get_submissions() -> list:
    return kv_lrange("submissions", 0, 999)

def get_best() -> dict | None:
    raw = kv_get("best_score")
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw

def set_best(sub: dict) -> None:
    kv_set("best_score", sub)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def respond(handler: BaseHTTPRequestHandler, status: int, body: dict,
            cache: str = "no-store") -> None:
    data = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", cache)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
    handler.end_headers()
    handler.wfile.write(data)

def parse_bearer(handler: BaseHTTPRequestHandler) -> str | None:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None

def require_auth(handler: BaseHTTPRequestHandler):
    key = parse_bearer(handler)
    if not key:
        respond(handler, 401, {"error": "missing bearer token"})
        return None
    user = get_user(key)
    if not user:
        respond(handler, 401, {"error": "invalid api key"})
        return None
    return user
