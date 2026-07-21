"""
bind.fail CLI

Usage:
    bindfail login
    bindfail targets
    bindfail submit sequences.fasta [--note "..."] [--model "..."]
    bindfail submissions
    bindfail leaderboard
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(os.environ.get("BINDFAIL_CONFIG_DIR", Path.home() / ".config" / "bindfail"))
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_HOST = os.environ.get("BINDFAIL_HOST", "https://bindfail.up.railway.app")


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def get_api_key() -> str:
    cfg = load_config()
    key = cfg.get("api_key") or os.environ.get("BINDFAIL_API_KEY", "")
    if not key:
        click.echo("Not logged in. Run: bindfail login", err=True)
        sys.exit(1)
    return key


def get_host() -> str:
    cfg = load_config()
    return cfg.get("host") or DEFAULT_HOST


def api(method: str, path: str, auth: bool = False, **kwargs) -> dict:
    host = get_host()
    url = f"{host}{path}"
    headers = kwargs.pop("headers", {})
    if auth:
        headers["Authorization"] = f"Bearer {get_api_key()}"
    try:
        resp = requests.request(method, url, headers=headers, timeout=120, **kwargs)
    except requests.ConnectionError:
        click.echo(f"Cannot reach server at {host}", err=True)
        sys.exit(1)
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        click.echo(f"Error {resp.status_code}: {detail}", err=True)
        sys.exit(1)
    return resp.json()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
@click.version_option("0.1.0", prog_name="bindfail")
def cli():
    """bind.fail: protein binder design benchmark."""


@cli.command()
@click.option("--host", default=None, help="Server URL (overrides default)")
def login(host: Optional[str]):
    """Register or log in and save your API key."""
    if host:
        cfg = load_config()
        cfg["host"] = host
        save_config(cfg)

    h = get_host()
    click.echo(f"Server: {h}")
    action = click.prompt("Register a new account or log in?", type=click.Choice(["register", "login"]), default="register")

    if action == "register":
        name = click.prompt("Your name / team name")
        data = api("GET", f"/auth/register?name={requests.utils.quote(name)}")
        key = data["api_key"]
        click.echo(f"\nRegistered as: {data['name']}")
        click.echo(f"API key: {key}")
    else:
        key = click.prompt("API key", hide_input=True)
        data = api("POST", "/auth/login", json={"api_key": key})
        click.echo(f"\nLogged in as: {data['name']}")

    cfg = load_config()
    cfg["api_key"] = key
    if host:
        cfg["host"] = host
    save_config(cfg)
    click.echo(f"Config saved to {CONFIG_FILE}")


@cli.command()
def targets():
    """List all benchmark target proteins."""
    data = api("GET", "/targets")
    tgts = data["targets"]
    click.echo(f"\n{'ID':<14} {'Name':<28} {'PDB':<6} {'Difficulty':<12} Description")
    click.echo("-" * 90)
    for t in tgts:
        click.echo(f"{t['id']:<14} {t['name']:<28} {t['pdb']:<6} {t['difficulty']:<12} {t['description']}")
    click.echo(f"\nTotal: {len(tgts)} targets. Use these IDs as FASTA headers in your submission.")
    click.echo("\nExample FASTA:")
    for t in tgts[:2]:
        click.echo(f">  {t['id']}")
        click.echo("  ACDEFGHIKLMNPQRSTVWYACDEFGHIKLMNPQRSTVWYACDEFGHIKLMNPQRSTVWYACDE")


@cli.command()
@click.argument("fasta_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--note", default="", help="Short description of your approach")
@click.option("--model", default="", help="Model or method name")
def submit(fasta_file: str, note: str, model: str):
    """Submit a FASTA file of binder sequences for evaluation.

    The FASTA file should have one sequence per target, with the target ID
    as the header (e.g., >spike_rbd).

    Missing targets score 0 ipTM. You must include at least one valid sequence.
    """
    path = Path(fasta_file)
    click.echo(f"Submitting {path.name}...")

    params = {}
    if note:
        params["note"] = note
    if model:
        params["model"] = model

    with open(path, "rb") as fh:
        data = api(
            "POST",
            "/submit",
            auth=True,
            params=params,
            files={"sequences_fasta": (path.name, fh, "text/plain")},
        )

    score = data["score"]
    promoted = data["promoted"]

    status = "PROMOTED to leaderboard" if promoted else "not promoted (did not beat current best)"
    click.echo(f"\nScore: {score:.4f}  ({status})")
    click.echo(f"Submission ID: {data['submission_id']}")
    click.echo("\nPer-target results:")
    click.echo(f"  {'Target':<14} {'ipTM':>6}  {'Success':>8}  Note")
    click.echo("  " + "-" * 50)
    for r in data.get("per_target", []):
        success_str = "YES" if r.get("success") else "no"
        err = r.get("error", "")
        note_str = f"  [{err}]" if err else ""
        click.echo(f"  {r['target_id']:<14} {r['iptm']:>6.4f}  {success_str:>8}{note_str}")


@cli.command()
def submissions():
    """Show your submission history."""
    data = api("GET", "/submissions", auth=True)
    subs = data["submissions"]
    if not subs:
        click.echo("No submissions yet.")
        return

    click.echo(f"\n{'ID':<20} {'Score':>7}  {'Promoted':>9}  {'Note'}")
    click.echo("-" * 70)
    for s in subs:
        import datetime
        dt = datetime.datetime.fromtimestamp(s["submitted_at"]).strftime("%Y-%m-%d %H:%M")
        promoted = "yes" if s.get("promoted") else "no"
        note = s.get("note", "")[:30]
        click.echo(f"  {s['id']:<18} {s['score']:>7.4f}  {promoted:>9}  {note}  ({dt})")


@cli.command()
def leaderboard():
    """Show the current leaderboard."""
    data = api("GET", "/leaderboard")
    board = data["leaderboard"]
    total = data.get("total_submissions", 0)
    best = data.get("best_score")

    if not board:
        click.echo("Leaderboard is empty. Be the first to submit!")
        return

    click.echo(f"\nbind.fail leaderboard  ({total} total submissions)")
    click.echo(f"Best score: {best:.4f}  (threshold: 0.7000)\n")
    click.echo(f"  {'Rank':<5} {'User':<24} {'Score':>7}  {'Model':<20}  Note")
    click.echo("  " + "-" * 75)
    for entry in board:
        model = (entry.get("model") or "")[:18]
        note = (entry.get("note") or "")[:28]
        click.echo(f"  {entry['rank']:<5} {entry['user']:<24} {entry['score']:>7.4f}  {model:<20}  {note}")
