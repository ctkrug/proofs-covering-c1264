#!/usr/bin/env python3
"""Emit deterministic OPB skeletons for the two C(12,6,4) pilot formulations."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


POINTS = tuple(range(12))
MATCHING = ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11))


def term(indices: list[int]) -> str:
    return " ".join(f"+1 x{index + 1}" for index in indices)


def block_variables() -> tuple[list[tuple[int, ...]], dict[tuple[int, ...], int]]:
    blocks = list(itertools.combinations(POINTS, 6))
    return blocks, {block: index for index, block in enumerate(blocks)}


def direct_constraints(root_case: str) -> tuple[list[tuple[int, ...]], list[str], dict[str, object]]:
    blocks, index = block_variables()
    constraints: list[str] = []
    for target in itertools.combinations(POINTS, 4):
        variables = [i for i, block in enumerate(blocks) if set(target) <= set(block)]
        constraints.append(f"{term(variables)} >= 1 ;")
    matching = {tuple(pair) for pair in MATCHING}
    for pair in itertools.combinations(POINTS, 2):
        variables = [i for i, block in enumerate(blocks) if set(pair) <= set(block)]
        constraints.append(f"{term(variables)} = {10 if pair in matching else 9} ;")
    r0 = [i for i, block in enumerate(blocks) if all(not set(pair) <= set(block) for pair in MATCHING)]
    canonical_r0 = (0, 2, 4, 6, 8, 10)
    canonical_r1 = (0, 1, 2, 4, 6, 8)
    if root_case == "r0-present":
        constraints.append(f"+1 x{index[canonical_r0] + 1} = 1 ;")
    elif root_case == "no-r0-r1-present":
        constraints.extend(f"+1 x{i + 1} = 0 ;" for i in r0)
        constraints.append(f"+1 x{index[canonical_r1] + 1} = 1 ;")
    else:
        raise ValueError("unknown root case")
    metadata = {
        "formulation": "direct-perfect-matching",
        "root_case": root_case,
        "variables": len(blocks),
        "coverage_constraints": 495,
        "pair_constraints": 66,
        "r0_variables": len(r0),
        "matching": [list(pair) for pair in MATCHING],
    }
    return blocks, constraints, metadata


def link_constraints() -> tuple[list[tuple[int, ...]], list[str], dict[str, object]]:
    # A block through point 0 is represented by its remaining five points.
    links = list(itertools.combinations(range(1, 12), 5))
    constraints: list[str] = []
    for triple in itertools.combinations(range(1, 12), 3):
        variables = [i for i, link in enumerate(links) if set(triple) <= set(link)]
        constraints.append(f"{term(variables)} >= 1 ;")
    for point in range(1, 12):
        variables = [i for i, link in enumerate(links) if point in link]
        constraints.append(f"{term(variables)} = {10 if point == 1 else 9} ;")
    return links, constraints, {
        "formulation": "point-link",
        "fixed_point": 0,
        "matched_partner": 1,
        "variables": len(links),
        "triple_coverage_constraints": 165,
        "degree_constraints": 11,
    }


def write_instance(kind: str, root_case: str, output: Path, manifest: Path) -> None:
    if kind == "direct":
        objects, constraints, metadata = direct_constraints(root_case)
    else:
        objects, constraints, metadata = link_constraints()
    header = f"* #variable= {len(objects)} #constraint= {len(constraints)}\n"
    payload = header + "\n".join(constraints) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="ascii")
    metadata.update({
        "schema_version": 1,
        "object_order": [list(item) for item in objects],
        "opb_path": str(output),
        "opb_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "constraints": len(constraints),
    })
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("direct", "link"), required=True)
    parser.add_argument("--root-case", choices=("r0-present", "no-r0-r1-present"), default="r0-present")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    write_instance(args.kind, args.root_case, args.output, args.manifest)


if __name__ == "__main__":
    main()
