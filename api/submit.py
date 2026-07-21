"""Vercel serverless: POST /api/submit  multipart: sequences_fasta + params note/model"""
import email
import email.policy
import hashlib
import io
import json
import os
import random
import time
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from _shared import (
    respond, require_auth,
    append_submission, get_best, set_best,
)

TARGETS = [
    {"id": "spike_rbd"},
    {"id": "pd1"},
    {"id": "her2"},
    {"id": "tnf_alpha"},
    {"id": "pcsk9"},
    {"id": "rsv_f"},
    {"id": "flu_ha"},
    {"id": "egfr"},
]

VALID_AAS = set("ACDEFGHIKLMNPQRSTVWY")
MIN_LEN, MAX_LEN = 50, 200
SUCCESS_THRESHOLD = 0.7


def parse_fasta(text: str) -> dict:
    sequences = {}
    header = None
    parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if header:
                sequences[header] = "".join(parts).upper()
            header = line[1:].split()[0]
            parts = []
        else:
            parts.append(line)
    if header:
        sequences[header] = "".join(parts).upper()
    return sequences


def _beta_sample(alpha: float, beta_p: float, seed_int: int) -> float:
    rng = random.Random(seed_int)
    for _ in range(1000):
        u = rng.random() ** (1.0 / alpha)
        v = rng.random() ** (1.0 / beta_p)
        if u + v <= 1.0:
            return u / (u + v)
    return alpha / (alpha + beta_p)


def mock_verify(seq: str, target_id: str) -> dict:
    combined = f"{target_id}:{seq}"
    digest = hashlib.sha256(combined.encode()).hexdigest()
    seed = int(digest[:16], 16)
    iptm = round(_beta_sample(2.0, 5.0, seed), 4)
    return {"iptm": iptm, "success": iptm >= SUCCESS_THRESHOLD}


def validate_seq(seq: str, target_id: str):
    bad = set(seq) - VALID_AAS
    if bad:
        return f"invalid amino acids: {sorted(bad)}"
    if len(seq) < MIN_LEN:
        return f"too short ({len(seq)} < {MIN_LEN})"
    if len(seq) > MAX_LEN:
        return f"too long ({len(seq)} > {MAX_LEN})"
    return None


def _parse_multipart(handler: "handler") -> tuple[bytes | None, dict]:
    ct = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length)

    # Reconstruct a proper MIME message for parsing
    mime_src = f"Content-Type: {ct}\r\n\r\n".encode() + raw
    msg = email.message_from_bytes(mime_src, policy=email.policy.compat32)

    fasta_bytes = None
    params = {}
    for part in msg.walk():
        disp = part.get_param("name", header="content-disposition")
        if disp == "sequences_fasta":
            fasta_bytes = part.get_payload(decode=True)
        elif disp in ("note", "model"):
            params[disp] = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
    return fasta_bytes, params


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        user = require_auth(self)
        if not user:
            return

        qs = parse_qs(urlparse(self.path).query)
        note = qs.get("note", [""])[0]
        model = qs.get("model", [""])[0]

        fasta_bytes, mp_params = _parse_multipart(self)
        note = note or mp_params.get("note", "")
        model = model or mp_params.get("model", "")

        if not fasta_bytes:
            respond(self, 400, {"error": "sequences_fasta field required"})
            return

        fasta_text = fasta_bytes.decode("utf-8", errors="replace")
        sequences = parse_fasta(fasta_text)

        if not sequences:
            respond(self, 400, {"error": "no sequences found in FASTA"})
            return

        per_target = []
        for t in TARGETS:
            tid = t["id"]
            seq = sequences.get(tid)
            if seq is None:
                per_target.append({"target_id": tid, "iptm": 0.0, "success": False, "error": "missing"})
                continue
            err = validate_seq(seq, tid)
            if err:
                per_target.append({"target_id": tid, "iptm": 0.0, "success": False, "error": err})
                continue
            r = mock_verify(seq, tid)
            r["target_id"] = tid
            per_target.append(r)

        iptm_vals = [r["iptm"] for r in per_target]
        mean_iptm = round(sum(iptm_vals) / len(iptm_vals), 4)

        best = get_best()
        best_score = best["score"] if best else -1.0
        promoted = mean_iptm > best_score

        sub_id = uuid.uuid4().hex[:12]
        now = int(time.time())
        submission = {
            "id": sub_id,
            "user": user["name"],
            "score": mean_iptm,
            "note": note[:200],
            "model": model[:100],
            "promoted": promoted,
            "submitted_at": now,
            "per_target": per_target,
        }
        append_submission(submission)

        if promoted:
            set_best({"score": mean_iptm, "id": sub_id, "user": user["name"]})

        respond(self, 200, {
            "ok": True,
            "score": mean_iptm,
            "promoted": promoted,
            "submission_id": sub_id,
            "per_target": per_target,
        })

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass
