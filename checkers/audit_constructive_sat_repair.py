#!/usr/bin/env python3
"""Audit hashes, cores, and any witness from a constructive SAT-repair run."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLOCKS = list(itertools.combinations(range(12), 6))
BLOCK_INDEX = {block: index + 1 for index, block in enumerate(BLOCKS)}


def load(path: Path) -> list[tuple[int, ...]]:
    rows = [
        tuple(int(value) - 1 for value in raw.split())
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    ]
    if len(rows) != len(set(rows)) or any(row not in BLOCK_INDEX for row in rows):
        raise ValueError("invalid or duplicate block")
    return rows


def audit(result_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    near_path = Path(result["near_cover"]["path"])
    if not near_path.is_absolute():
        near_path = ROOT / near_path
    if hashlib.sha256(near_path.read_bytes()).hexdigest() != result["near_cover"]["sha256"]:
        raise ValueError("near-cover hash mismatch")
    near = load(near_path)
    if len(near) != 40:
        raise ValueError("near-cover does not have 40 blocks")
    near_variables = {BLOCK_INDEX[row] for row in near}
    for attempt in result["attempts"]:
        core = attempt["core_block_variables"]
        if len(core) != attempt["core_size"] or len(set(core)) != len(core):
            raise ValueError("core size or uniqueness mismatch")
        if not set(core) <= near_variables:
            raise ValueError("repair core is not a subset of the bound near-cover")
        if attempt["status"] not in {"CORE_UNSAT", "UNKNOWN", "SAT", "ERROR"}:
            raise ValueError("unknown attempt status")
    witness = result["witness"]
    covered = False
    if witness is not None:
        witness_path = Path(witness["path"])
        if not witness_path.is_absolute():
            witness_path = ROOT / witness_path
        if hashlib.sha256(witness_path.read_bytes()).hexdigest() != witness["sha256"]:
            raise ValueError("witness hash mismatch")
        rows = load(witness_path)
        covered = len(rows) == 40 and all(
            any(set(quad).issubset(block) for block in rows)
            for quad in itertools.combinations(range(12), 4)
        )
        if not covered or result["status"] != "WITNESS_CANDIDATE":
            raise ValueError("witness/status disagreement")
    elif result["status"] != "NO_WITNESS":
        raise ValueError("missing witness/status disagreement")
    return {
        "schema_version": 1,
        "status": "valid",
        "attempts": len(result["attempts"]),
        "direct_witness_valid": covered,
        "claim_limit": "CORE_UNSAT without a replayed proof is provisional and excludes no global case.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.result), sort_keys=True))


if __name__ == "__main__":
    main()
