#!/usr/bin/env python3
"""Build a deterministic complete shallow cube frontier for a C(12,6,4) root."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path


MATCHING = ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11))


def block_r(block: tuple[int, ...]) -> int:
    return sum(set(pair).issubset(block) for pair in MATCHING)


def select_variables(root_case: str, depth: int) -> tuple[list[int], list[list[int]]]:
    blocks = list(itertools.combinations(range(12), 6))
    index = {block: position + 1 for position, block in enumerate(blocks)}
    if root_case == "r0-present":
        fixed = (0, 2, 4, 6, 8, 10)
        forbidden: set[int] = set()
    elif root_case == "no-r0-r1-present":
        fixed = (0, 1, 2, 4, 6, 8)
        forbidden = {
            position + 1 for position, block in enumerate(blocks) if block_r(block) == 0
        }
    else:
        raise ValueError("unknown root case")
    fixed_variable = index[fixed]
    candidates: list[tuple[tuple[int, int], int]] = []
    for position, block in enumerate(blocks, 1):
        if position == fixed_variable or position in forbidden:
            continue
        signature = (block_r(block), len(set(block).intersection(fixed)))
        candidates.append((signature, position))
    selected: list[int] = []
    seen: set[tuple[int, int]] = set()
    for signature, position in candidates:
        if signature not in seen:
            seen.add(signature)
            selected.append(position)
            if len(selected) == depth:
                break
    if len(selected) < depth:
        selected.extend(position for _signature, position in candidates if position not in selected)
        selected = selected[:depth]
    return selected, [list(blocks[position - 1]) for position in selected]


def build(root_case: str, depth: int, cnf: Path) -> dict[str, object]:
    if depth < 1 or depth > 16:
        raise ValueError("depth must be 1..16")
    variables, blocks = select_variables(root_case, depth)
    cubes = []
    for cube_id, bits in enumerate(itertools.product((0, 1), repeat=depth)):
        literals = [variable if bit else -variable for variable, bit in zip(variables, bits)]
        cubes.append({"cube_id": cube_id, "bits": "".join(map(str, bits)), "literals": literals})
    return {
        "schema_version": 1,
        "problem_id": "covering-c1264",
        "root_case": root_case,
        "depth": depth,
        "variables": variables,
        "blocks_zero_based": blocks,
        "cube_count": len(cubes),
        "cnf_path": str(cnf),
        "cnf_sha256": hashlib.sha256(cnf.read_bytes()).hexdigest(),
        "coverage_basis": "all 2^depth Boolean assignments to distinct unfixed primary variables",
        "cubes": cubes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-case", choices=("r0-present", "no-r0-r1-present"), required=True)
    parser.add_argument("--depth", type=int, default=7)
    parser.add_argument("--cnf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.root_case, args.depth, args.cnf)
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({key: payload[key] for key in ("root_case", "depth", "cube_count", "cnf_sha256")}, sort_keys=True))


if __name__ == "__main__":
    main()
