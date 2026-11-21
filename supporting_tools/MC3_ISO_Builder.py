#!/usr/bin/env python3
"""Unified Retail/VIP ISO builder entry point.

The profile-specific verified builders remain separate engines for now.
This dispatcher deliberately does not alter their preflight or write behavior.
"""
import argparse
from pathlib import Path
import subprocess
import sys

ENGINES = {
    "retail": "MC3_ISO_Builder_Retail.py",
    "vip": "MC3_ISO_Builder_VIP.py",
    "vip-v11a": "MC3_ISO_Builder_V11A.py",
}

def main():
    parser = argparse.ArgumentParser(description="MC3 Retail/VIP ISO builder dispatcher", add_help=False)
    parser.add_argument("--profile", choices=tuple(ENGINES), required=True)
    args, remaining = parser.parse_known_args()
    engine = Path(__file__).resolve().parent / ENGINES[args.profile]
    if not engine.is_file():
        print(f"[ERROR] Required {args.profile} builder not found: {engine}", file=sys.stderr)
        return 2
    command = [sys.executable, str(engine), "--profile", args.profile, *remaining]
    return subprocess.call(command)

if __name__ == "__main__":
    sys.exit(main())
