"""
Thin entrypoint shim — the real CLI lives in bindfail/cli.py.
This file exists for direct execution: python cli/bindfail.py
"""
import sys
import os

# Add project root to path so `bindfail` package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bindfail.cli import cli

if __name__ == "__main__":
    cli()
