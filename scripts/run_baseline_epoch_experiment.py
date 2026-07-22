#!/usr/bin/env python3
"""Run the baseline producer and independent checker as separate processes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv: list[str]) -> dict[str, object]:
    completed = subprocess.run(argv, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError({"argv": argv, "returncode": completed.returncode, "stderr": completed.stderr})
    return {"argv": argv, "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--producer", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--check", type=Path, required=True)
    args = parser.parse_args()
    producer = run([
        sys.executable,
        str(args.producer),
        "--witness", str(args.witness),
        "--output", str(args.result),
    ])
    checker = run([
        sys.executable,
        str(args.checker),
        "--result", str(args.result),
        "--witness", str(args.witness),
        "--output", str(args.check),
    ])
    print(json.dumps({
        "schema_version": 1,
        "status": "valid-baseline-experiment",
        "producer": producer,
        "checker": checker,
        "result": {"path": str(args.result), "sha256": digest(args.result)},
        "check": {"path": str(args.check), "sha256": digest(args.check)},
        "inputs": {
            "producer": {"path": str(args.producer), "sha256": digest(args.producer)},
            "checker": {"path": str(args.checker), "sha256": digest(args.checker)},
            "witness": {"path": str(args.witness), "sha256": digest(args.witness)},
        },
        "claim_limit": "No frontier search was run and no exact-value claim is supported.",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
