"""
bind.fail verifier

Mock mode (default): draws ipTM scores from Beta(2,5) with a seed derived
from the sequence hash, giving reproducible but plausible-looking scores.
Most designs land in 0.3-0.6; genuine binders occasionally exceed 0.7.

Real mode (--real / use_real=True): calls AF2-Multimer via Modal.
"""

import hashlib
import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Optional

TARGETS_PATH = Path(__file__).parent.parent / "targets" / "targets.json"
PDB_CACHE = Path(__file__).parent / "pdb_cache"
PDB_CACHE.mkdir(parents=True, exist_ok=True)

VALID_AAS = set("ACDEFGHIKLMNPQRSTVWY")
MIN_LEN = 50
MAX_LEN = 200
SUCCESS_THRESHOLD = 0.7

# ---------------------------------------------------------------------------
# Target loading
# ---------------------------------------------------------------------------

def load_targets() -> dict:
    with open(TARGETS_PATH) as f:
        targets = json.load(f)
    return {t["id"]: t for t in targets}


# ---------------------------------------------------------------------------
# Sequence validation
# ---------------------------------------------------------------------------

def validate_sequence(seq: str, target_id: str) -> Optional[str]:
    """Return an error string, or None if valid."""
    seq = seq.upper().strip()
    bad = set(seq) - VALID_AAS
    if bad:
        return f"{target_id}: invalid amino acid characters: {sorted(bad)}"
    if len(seq) < MIN_LEN:
        return f"{target_id}: sequence too short ({len(seq)} < {MIN_LEN})"
    if len(seq) > MAX_LEN:
        return f"{target_id}: sequence too long ({len(seq)} > {MAX_LEN})"
    return None


# ---------------------------------------------------------------------------
# PDB utilities
# ---------------------------------------------------------------------------

def fetch_pdb(pdb_id: str) -> Path:
    pdb_id = pdb_id.upper()
    cache_path = PDB_CACHE / f"{pdb_id}.pdb"
    if cache_path.exists():
        return cache_path
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    print(f"Downloading {url}...", file=sys.stderr)
    urllib.request.urlretrieve(url, cache_path)
    return cache_path


def extract_chain_sequence(pdb_path: Path, chain: str) -> str:
    """Extract one-letter amino acid sequence for a chain from a PDB file."""
    aa3to1 = {
        "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
        "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
        "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
        "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    }
    seen = set()
    residues = []
    with open(pdb_path) as f:
        for line in f:
            if not line.startswith("ATOM"):
                continue
            ch = line[21]
            if ch != chain:
                continue
            res_name = line[17:20].strip()
            res_seq = line[22:26].strip()
            key = (ch, res_seq)
            if key in seen:
                continue
            seen.add(key)
            aa = aa3to1.get(res_name)
            if aa:
                residues.append(aa)
    return "".join(residues)


# ---------------------------------------------------------------------------
# Mock verifier
# ---------------------------------------------------------------------------

def _beta_sample(alpha: float, beta_param: float, seed_int: int) -> float:
    """
    Draw one sample from Beta(alpha, beta) using a seeded approach.
    Uses a simple approximation via the relationship between Beta and Gamma
    distributions implemented with the Marsaglia-Tsang method equivalent
    via Python's random module seeded deterministically.
    """
    import random
    rng = random.Random(seed_int)

    # Johnk's method for Beta(a, b)
    while True:
        u = rng.random() ** (1.0 / alpha)
        v = rng.random() ** (1.0 / beta_param)
        if u + v <= 1.0:
            return u / (u + v)


def mock_verify(binder_seq: str, target_id: str) -> dict:
    """
    Return a reproducible plausible score without any GPU.
    Seed is derived from (target_id, binder_seq) so same input gives same output.
    """
    combined = f"{target_id}:{binder_seq}"
    digest = hashlib.sha256(combined.encode()).hexdigest()
    seed_int = int(digest[:16], 16)

    iptm = _beta_sample(2.0, 5.0, seed_int)
    # pAE_interaction is negatively correlated with quality: lower = better
    pae = 30.0 * (1.0 - iptm) + _beta_sample(2.0, 2.0, seed_int ^ 0xDEAD) * 5.0

    return {
        "iptm": round(iptm, 4),
        "pae_interaction": round(pae, 2),
        "success": iptm >= SUCCESS_THRESHOLD,
        "mock": True,
    }


# ---------------------------------------------------------------------------
# Real verifier stub (AF2-Multimer via Modal)
# ---------------------------------------------------------------------------

def real_verify(binder_seq: str, target_id: str, target_seq: str) -> dict:
    """
    Run AF2-Multimer via Modal. Requires Modal to be installed and authenticated.
    """
    try:
        import modal  # noqa: F401
    except ImportError:
        raise RuntimeError("modal package not installed; run: pip install modal")

    # This would be implemented as a Modal stub calling ColabFold / AF2-Multimer.
    # Placeholder signature for the real implementation:
    raise NotImplementedError(
        "Real AF2-Multimer verification not yet implemented. "
        "Run without --real to use the mock verifier."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def verify_sequence(
    binder_seq: str,
    target_id: str,
    use_real: bool = False,
) -> dict:
    """
    Validate and score a binder sequence against a target.

    Returns dict with keys: iptm, pae_interaction, success, mock, error (if any).
    """
    binder_seq = binder_seq.upper().strip()
    err = validate_sequence(binder_seq, target_id)
    if err:
        return {"iptm": 0.0, "pae_interaction": 30.0, "success": False, "mock": not use_real, "error": err}

    if use_real:
        targets = load_targets()
        if target_id not in targets:
            return {"iptm": 0.0, "pae_interaction": 30.0, "success": False, "mock": False,
                    "error": f"Unknown target: {target_id}"}
        t = targets[target_id]
        pdb_path = fetch_pdb(t["pdb"])
        target_seq = extract_chain_sequence(pdb_path, t["chain"])
        return real_verify(binder_seq, target_id, target_seq)
    else:
        return mock_verify(binder_seq, target_id)


def verify_fasta(fasta_text: str, use_real: bool = False) -> dict:
    """
    Parse a multi-FASTA string and verify each sequence.

    Returns dict with overall score and per-target breakdown.
    """
    targets = load_targets()
    sequences = parse_fasta(fasta_text)

    results = []
    for target_id, target in targets.items():
        seq = sequences.get(target_id)
        if seq is None:
            results.append({
                "target_id": target_id,
                "iptm": 0.0,
                "pae_interaction": 30.0,
                "success": False,
                "mock": not use_real,
                "error": "missing sequence",
            })
        else:
            r = verify_sequence(seq, target_id, use_real=use_real)
            r["target_id"] = target_id
            results.append(r)

    iptm_values = [r["iptm"] for r in results]
    mean_iptm = sum(iptm_values) / len(iptm_values) if iptm_values else 0.0

    return {
        "score": round(mean_iptm, 4),
        "per_target": results,
    }


def parse_fasta(text: str) -> dict:
    """Parse FASTA text into {header: sequence} dict."""
    sequences = {}
    current_header = None
    current_seq_parts = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if current_header is not None:
                sequences[current_header] = "".join(current_seq_parts).upper()
            current_header = line[1:].split()[0]
            current_seq_parts = []
        else:
            current_seq_parts.append(line)

    if current_header is not None:
        sequences[current_header] = "".join(current_seq_parts).upper()

    return sequences


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="bind.fail verifier")
    parser.add_argument("fasta", help="FASTA file with binder sequences")
    parser.add_argument("--real", action="store_true", help="Use real AF2-Multimer (requires Modal)")
    args = parser.parse_args()

    with open(args.fasta) as f:
        fasta_text = f.read()

    result = verify_fasta(fasta_text, use_real=args.real)
    print(json.dumps(result, indent=2))
