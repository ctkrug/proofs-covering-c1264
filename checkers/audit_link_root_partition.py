#!/usr/bin/env python3
"""Audit the six fixed-matching link roots using block-type invariants."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


PAIRS = ({2, 3}, {4, 5}, {6, 7}, {8, 9}, {10, 11})
TYPE_ORDER = ((1, 0, 4), (1, 1, 2), (1, 2, 0), (0, 0, 5), (0, 1, 3), (0, 2, 1))


def block_type(block: tuple[int, ...]) -> tuple[int, int, int]:
    chosen = set(block)
    complete = sum(pair <= chosen for pair in PAIRS)
    singles = sum(len(pair & chosen) == 1 for pair in PAIRS)
    return (int(1 in chosen), complete, singles)


def audit(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    blocks = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(blocks, 1)}
    expected = [
        {positions[block] for block in blocks if block_type(block) == kind}
        for kind in TYPE_ORDER
    ]
    if [len(orbit) for orbit in expected] != [80, 120, 10, 32, 160, 60]:
        raise AssertionError("independent block-type counts changed")
    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != 6:
        raise ValueError("root count mismatch")
    prior: set[int] = set()
    for index, (row, orbit) in enumerate(zip(roots, expected)):
        canonical = tuple(int(point) for point in row["canonical_block"])
        if row["root_index"] != index or block_type(canonical) != TYPE_ORDER[index]:
            raise ValueError("canonical root type mismatch")
        if row["canonical_variable"] != positions[canonical]:
            raise ValueError("canonical root variable mismatch")
        if set(row["orbit_variables"]) != orbit or row["orbit_size"] != len(orbit):
            raise ValueError("root orbit membership mismatch")
        if set(row["earlier_orbit_variables_forced_false"]) != prior:
            raise ValueError("earlier-orbit exclusion mismatch")
        prior.update(orbit)
    if prior != set(range(1, 463)):
        raise ValueError("root partition is not exhaustive")
    return {
        "schema_version": 1,
        "status": "valid",
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "root_count": 6,
        "orbit_sizes": [len(orbit) for orbit in expected],
        "covered_primary_variables": len(prior),
        "independence_basis": "Reconstructed from the six (contains distinguished point, complete pairs, single pairs) block types without enumerating group maps.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = audit(args.manifest)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(args.output)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
