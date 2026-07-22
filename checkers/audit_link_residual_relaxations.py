#!/usr/bin/env python3
"""Independently recompute every saved relaxation candidate's cover defects."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from profile_link_residual_relaxations import candidate_metrics  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(result_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    checked = []
    for row in result["results"]:
        if row["status"] != "SAT":
            continue
        path = Path(row["candidate"]["path"])
        if not path.is_absolute():
            path = ROOT / path
        assert sha(path) == row["candidate"]["sha256"]
        blocks = [tuple(map(int, line.split())) for line in path.read_text().splitlines() if line.strip()]
        metrics = candidate_metrics(blocks)
        assert metrics == row["metrics"]
        checked.append({"test_index": row["test_index"], "candidate_sha256": sha(path),
                        "uncovered_count": metrics["uncovered_count"],
                        "block_count": metrics["block_count"],
                        "pair_deviation_count": metrics["pair_deviation_count"],
                        "is_valid_40_cover": metrics["is_valid_40_cover"]})
    return {
        "schema_version": 1,
        "status": "valid",
        "result_sha256": sha(result_path),
        "sat_candidates_checked": len(checked),
        "valid_40_covers": sum(row["is_valid_40_cover"] for row in checked),
        "candidates": checked,
        "claim_limit": "Recomputes candidate hashes and complete cover-defect metrics; it does not certify provisional UNSAT relaxation results.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result_path = args.result if args.result.is_absolute() else ROOT / args.result
    value = audit(result_path)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
