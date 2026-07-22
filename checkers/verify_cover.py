#!/usr/bin/env python3
"""Independent direct checker for a C(v,k,t) covering witness."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


def load_blocks(path: Path, *, v: int, k: int) -> list[tuple[int, ...]]:
    blocks: list[tuple[int, ...]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            block = tuple(int(value) - 1 for value in raw.split())
        except ValueError as exc:
            raise ValueError(f"line {line_number}: non-integer entry") from exc
        if len(block) != k or tuple(sorted(block)) != block or len(set(block)) != k:
            raise ValueError(f"line {line_number}: expected {k} strictly increasing points")
        if block[0] < 0 or block[-1] >= v:
            raise ValueError(f"line {line_number}: point outside 1..{v}")
        blocks.append(block)
    if len(set(blocks)) != len(blocks):
        raise ValueError("duplicate block")
    return blocks


def verify(path: Path, *, v: int, k: int, t: int, expected_blocks: int | None) -> dict[str, object]:
    if not 0 < t <= k <= v:
        raise ValueError("require 0 < t <= k <= v")
    blocks = load_blocks(path, v=v, k=k)
    if expected_blocks is not None and len(blocks) != expected_blocks:
        raise ValueError(f"expected {expected_blocks} blocks, found {len(blocks)}")
    covered: set[tuple[int, ...]] = set()
    for block in blocks:
        covered.update(itertools.combinations(block, t))
    universe = set(itertools.combinations(range(v), t))
    missing = sorted(universe - covered)
    if missing:
        sample = [[point + 1 for point in item] for item in missing[:10]]
        raise ValueError(f"not a cover: {len(missing)} uncovered t-sets; first={sample}")
    point_degrees = [sum(point in block for block in blocks) for point in range(v)]
    pair_multiplicities = [
        sum(a in block and b in block for block in blocks)
        for a, b in itertools.combinations(range(v), 2)
    ]
    return {
        "schema_version": 1,
        "status": "valid",
        "parameters": {"v": v, "k": k, "t": t},
        "blocks": len(blocks),
        "covered_t_sets": len(covered),
        "point_degree_range": [min(point_degrees), max(point_degrees)],
        "pair_multiplicity_range": [min(pair_multiplicities), max(pair_multiplicities)],
        "input": str(path),
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("witness", type=Path)
    parser.add_argument("--v", type=int, default=12)
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--t", type=int, default=4)
    parser.add_argument("--expected-blocks", type=int)
    args = parser.parse_args()
    print(json.dumps(verify(
        args.witness, v=args.v, k=args.k, t=args.t, expected_blocks=args.expected_blocks,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
