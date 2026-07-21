"""
bind.fail judge server

Run locally:
    uvicorn server.main:app --reload

Environment variables:
    BINDFAIL_DATA   directory for persistent JSON storage (default: ./data)
    BINDFAIL_REAL   set to "1" to use real AF2-Multimer verifier
"""

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("BINDFAIL_DATA", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
SUBMISSIONS_FILE = DATA_DIR / "submissions.json"

USE_REAL = os.environ.get("BINDFAIL_REAL", "0") == "1"

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def _write_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def load_users() -> dict:
    return _read_json(USERS_FILE, {})


def save_users(users: dict):
    _write_json(USERS_FILE, users)


def load_submissions() -> list:
    return _read_json(SUBMISSIONS_FILE, [])


def save_submissions(subs: list):
    _write_json(SUBMISSIONS_FILE, subs)


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

TARGETS_PATH = Path(__file__).parent.parent / "targets" / "targets.json"

def load_targets() -> list:
    with open(TARGETS_PATH) as f:
        return json.load(f)

TARGETS = load_targets()
TARGET_IDS = {t["id"] for t in TARGETS}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="bind.fail", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    users = load_users()
    if token not in users:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return users[token]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True, "service": "bind.fail"}


@app.get("/auth/register")
def register(name: str = Query(..., min_length=1, max_length=64)):
    name = name.strip()
    if not re.match(r'^[\w\- ]+$', name):
        raise HTTPException(status_code=400, detail="Name contains invalid characters")

    users = load_users()
    # Check for duplicate name
    for u in users.values():
        if u["name"].lower() == name.lower():
            raise HTTPException(status_code=409, detail="Name already taken")

    api_key = "bf_" + secrets.token_hex(24)
    users[api_key] = {
        "name": name,
        "api_key": api_key,
        "created_at": time.time(),
    }
    save_users(users)
    return {"api_key": api_key, "name": name}


class LoginRequest(BaseModel):
    api_key: str


@app.post("/auth/login")
def login(req: LoginRequest):
    users = load_users()
    if req.api_key not in users:
        raise HTTPException(status_code=401, detail="Invalid API key")
    u = users[req.api_key]
    return {"name": u["name"], "api_key": u["api_key"]}


@app.get("/targets")
def get_targets():
    return {"targets": TARGETS}


@app.get("/benchmark")
def get_benchmark():
    return {
        "name": "bind.fail",
        "version": "0.1.0",
        "targets": TARGETS,
        "success_threshold": 0.7,
        "sequence_length": {"min": 50, "max": 200},
        "scoring": "mean ipTM across all 8 targets",
        "submission_format": "FASTA with one sequence per target; header = target_id",
    }


@app.post("/submit")
async def submit(
    sequences_fasta: UploadFile = File(...),
    note: Optional[str] = Query(None, max_length=500),
    model: Optional[str] = Query(None, max_length=128),
    user: dict = Depends(get_current_user),
):
    from verifier.verify import verify_fasta

    raw = await sequences_fasta.read()
    try:
        fasta_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="FASTA file must be UTF-8 encoded")

    if not fasta_text.strip():
        raise HTTPException(status_code=400, detail="FASTA file is empty")

    result = verify_fasta(fasta_text, use_real=USE_REAL)

    submissions = load_submissions()

    # Find best promoted score for this user (for reference) and globally
    promoted = [s for s in submissions if s.get("promoted")]
    best_score = max((s["score"] for s in promoted), default=None)

    # Strict promotion: only appears on leaderboard if strictly better than current best
    is_promoted = best_score is None or result["score"] > best_score

    entry = {
        "id": secrets.token_hex(8),
        "user": user["name"],
        "score": result["score"],
        "per_target": result["per_target"],
        "note": note or "",
        "model": model or "",
        "submitted_at": time.time(),
        "promoted": is_promoted,
        "mock": result["per_target"][0].get("mock", True) if result["per_target"] else True,
    }

    # If newly promoted, demote previous leader
    if is_promoted:
        for s in submissions:
            if s.get("promoted"):
                s["promoted"] = False

    submissions.append(entry)
    save_submissions(submissions)

    return {
        "ok": True,
        "promoted": is_promoted,
        "score": result["score"],
        "per_target": result["per_target"],
        "submission_id": entry["id"],
    }


@app.get("/leaderboard")
def leaderboard():
    submissions = load_submissions()

    promoted = sorted(
        [s for s in submissions if s.get("promoted")],
        key=lambda s: s["score"],
        reverse=True,
    )

    history = sorted(submissions, key=lambda s: s["submitted_at"], reverse=True)

    return {
        "leaderboard": [
            {
                "rank": i + 1,
                "user": s["user"],
                "score": s["score"],
                "note": s["note"],
                "model": s["model"],
                "submitted_at": s["submitted_at"],
                "per_target": s["per_target"],
            }
            for i, s in enumerate(promoted)
        ],
        "history": [
            {
                "user": s["user"],
                "score": s["score"],
                "submitted_at": s["submitted_at"],
                "promoted": s["promoted"],
            }
            for s in history[:100]
        ],
        "best_score": promoted[0]["score"] if promoted else None,
        "total_submissions": len(submissions),
    }


@app.get("/submissions")
def my_submissions(user: dict = Depends(get_current_user)):
    submissions = load_submissions()
    mine = [s for s in submissions if s["user"] == user["name"]]
    mine.sort(key=lambda s: s["submitted_at"], reverse=True)
    return {"submissions": mine}
