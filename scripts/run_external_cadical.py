#!/usr/bin/env python3
"""Run a bounded external CaDiCaL process and preserve a hash-bound receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
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
    parser.add_argument("solver", type=Path)
    parser.add_argument("proof", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    if args.seconds < 1 or args.proof.exists() or args.receipt.exists():
        raise ValueError("invalid cap or pre-existing immutable output")
    command = [str(args.solver), "-t", str(args.seconds), "--no-binary", str(args.cnf), str(args.proof)]
    started = time.monotonic()
    result = subprocess.run(command, text=True, capture_output=True, timeout=args.seconds + 30)
    elapsed = time.monotonic() - started
    combined = result.stdout + result.stderr
    status = "UNSAT_PROVISIONAL" if result.returncode == 20 and "s UNSATISFIABLE" in combined else (
        "SAT" if result.returncode == 10 and "s SATISFIABLE" in combined else "UNKNOWN_OR_ERROR"
    )
    if status != "UNSAT_PROVISIONAL" and args.proof.exists():
        raise RuntimeError("unexpected solver outcome produced a proof artifact")
    log = args.receipt.with_suffix(args.receipt.suffix + ".log")
    atomic(log, combined)
    payload = {
        "schema_version": 1,
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "exit_code": result.returncode,
        "seconds_cap": args.seconds,
        "elapsed_seconds": elapsed,
        "cnf": {"path": str(args.cnf), "bytes": args.cnf.stat().st_size, "sha256": sha(args.cnf)},
        "solver": {"path": str(args.solver), "sha256": sha(args.solver)},
        "proof": None if not args.proof.exists() else {
            "path": str(args.proof), "bytes": args.proof.stat().st_size, "sha256": sha(args.proof),
        },
        "log": {"path": str(log), "bytes": log.stat().st_size, "sha256": sha(log)},
        "claim_limit": "UNSAT is provisional until the exact proof is independently replayed; SAT requires a direct witness check.",
    }
    atomic(args.receipt, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))
    if status == "UNKNOWN_OR_ERROR":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
