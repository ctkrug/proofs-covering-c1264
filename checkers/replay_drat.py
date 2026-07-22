#!/usr/bin/env python3
"""Replay a DRAT proof and write a hash-bound validation receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cnf", type=Path)
    parser.add_argument("proof", type=Path)
    parser.add_argument("drat_trim", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--seconds", type=int, default=300)
    args = parser.parse_args()
    command = [str(args.drat_trim), str(args.cnf), str(args.proof)]
    result = subprocess.run(command, text=True, capture_output=True, timeout=args.seconds)
    combined = result.stdout + result.stderr
    if result.returncode != 0 or "s VERIFIED" not in combined:
        raise RuntimeError(f"DRAT replay failed: {combined[-2000:]}")
    log = args.receipt.with_suffix(args.receipt.suffix + ".log")
    atomic(log, combined)
    receipt = {
        "schema_version": 1,
        "status": "verified",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "exit_code": result.returncode,
        "seconds_cap": args.seconds,
        "cnf": {"path": str(args.cnf), "sha256": sha(args.cnf)},
        "proof": {"path": str(args.proof), "sha256": sha(args.proof)},
        "checker": {"path": str(args.drat_trim), "sha256": sha(args.drat_trim)},
        "log": {"path": str(log), "sha256": sha(log)},
        "verdict": "s VERIFIED",
    }
    atomic(args.receipt, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
