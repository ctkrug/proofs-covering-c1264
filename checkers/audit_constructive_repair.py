#!/usr/bin/env python3
"""Independently recompute a constructive repair run's candidate metrics."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def audit(result_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    candidate = Path(result["candidate"]["path"])
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    blocks: list[tuple[int, ...]] = []
    for line_number, raw in enumerate(candidate.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        block = tuple(int(value) - 1 for value in raw.split())
        if len(block) != 6 or tuple(sorted(block)) != block or len(set(block)) != 6:
            raise ValueError(f"line {line_number}: malformed block")
        if block[0] < 0 or block[-1] >= 12:
            raise ValueError(f"line {line_number}: point outside 1..12")
        blocks.append(block)
    if len(set(blocks)) != len(blocks):
        raise ValueError("duplicate candidate block")
    if len(blocks) != 40:
        raise ValueError("candidate does not contain exactly 40 blocks")
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if digest != result["candidate"]["sha256"]:
        raise ValueError("candidate hash mismatch")
    quad_counts = [sum(set(quad).issubset(block) for block in blocks) for quad in itertools.combinations(range(12), 4)]
    point_counts = [sum(point in block for block in blocks) for point in range(12)]
    pair_counts = [sum(set(pair).issubset(block) for block in blocks) for pair in itertools.combinations(range(12), 2)]
    measured = {
        "uncovered_quadruples": sum(value == 0 for value in quad_counts),
        "point_degree_deviation": sum(abs(value - 20) for value in point_counts),
        "pair_deficit_below_9": sum(max(0, 9 - value) for value in pair_counts),
        "pair_excess_above_10": sum(max(0, value - 10) for value in pair_counts),
    }
    if measured != result["best_metrics"]:
        raise ValueError(f"metric disagreement: {measured} != {result['best_metrics']}")
    expected_status = "WITNESS_CANDIDATE" if measured["uncovered_quadruples"] == 0 else "NO_WITNESS"
    if result["status"] != expected_status:
        raise ValueError("status disagrees with direct coverage count")
    return {"schema_version": 1, "status": "valid", "candidate_sha256": digest, "metrics": measured}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.result), sort_keys=True))


if __name__ == "__main__":
    main()
