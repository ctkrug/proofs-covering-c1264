#!/usr/bin/env python3
"""Exactly classify one C(11,5,3) link under the fixed-matching stabilizer.

This is deliberately a one-input orbit computation, not an enumeration of all
optimal links.  It supplies the exact group action and canonical key needed by
a later checkpointed SAT orbit enumerator.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import time
from pathlib import Path


PAIRS = ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_link(path: Path) -> tuple[tuple[int, ...], ...]:
    blocks = tuple(sorted(tuple(sorted(map(int, line.split()))) for line in path.read_text().splitlines() if line.strip()))
    if len(blocks) != 20 or len(set(blocks)) != 20:
        raise ValueError("link must have exactly 20 distinct blocks")
    if any(len(block) != 5 or block[0] < 1 or block[-1] > 11 or len(set(block)) != 5 for block in blocks):
        raise ValueError("link blocks must be 5-subsets of 1..11")
    covered = {triple for block in blocks for triple in itertools.combinations(block, 3)}
    if len(covered) != 165:
        raise ValueError("link does not cover every triple")
    degrees = tuple(sum(point in block for block in blocks) for point in range(1, 12))
    if degrees != (10, *([9] * 10)):
        raise ValueError("link degrees must be 10 at point 1 and 9 elsewhere")
    return blocks


def group_maps():
    """Yield all 2^5 * 5! maps fixing 1 and preserving the five pairs."""
    for target_order in itertools.permutations(range(5)):
        for flip_mask in range(1 << 5):
            mapping = {1: 1}
            for source_index, target_index in enumerate(target_order):
                source = PAIRS[source_index]
                target = PAIRS[target_index]
                flip = (flip_mask >> source_index) & 1
                mapping[source[0]] = target[flip]
                mapping[source[1]] = target[1 - flip]
            yield mapping


def image(blocks: tuple[tuple[int, ...], ...], mapping: dict[int, int]) -> tuple[tuple[int, ...], ...]:
    return tuple(sorted(tuple(sorted(mapping[point] for point in block)) for block in blocks))


def block_clause(image_blocks: tuple[tuple[int, ...], ...]) -> tuple[int, ...]:
    universe = list(itertools.combinations(range(1, 12), 5))
    positions = {block: index for index, block in enumerate(universe, 1)}
    return tuple(-positions[block] for block in image_blocks)


def write_blocking_cnf(path: Path, images: set[tuple[tuple[int, ...], ...]]) -> dict[str, object]:
    clauses = sorted(block_clause(candidate) for candidate in images)
    text = f"p cnf 462 {len(clauses)}\n" + "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "variables": 462,
        "clauses": len(clauses),
        "literals_per_clause": 20,
        "soundness_basis": (
            "Each clause negates the 20 selected blocks of one orbit image. Exact degree constraints "
            "force every feasible link to contain exactly 20 blocks, so the clause excludes exactly "
            "that image within the intended link formulation."
        ),
    }


def analyze(path: Path, blocking_cnf: Path | None = None) -> dict[str, object]:
    started = time.monotonic()
    blocks = load_link(path)
    images: set[tuple[tuple[int, ...], ...]] = set()
    stabilizer_order = 0
    transformations_checked = 0
    for mapping in group_maps():
        transformed = image(blocks, mapping)
        transformations_checked += 1
        images.add(transformed)
        if transformed == blocks:
            stabilizer_order += 1
    group_order = 3840
    if transformations_checked != group_order:
        raise AssertionError("group generator did not emit 3,840 maps")
    if len(images) * stabilizer_order != group_order:
        raise AssertionError("orbit-stabilizer check failed")
    canonical = min(images)
    canonical_text = "".join(" ".join(map(str, block)) + "\n" for block in canonical)
    result: dict[str, object] = {
        "schema_version": 1,
        "status": "exact-single-link-orbit",
        "source": {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)},
        "action": {
            "fixed_point": 1,
            "preserved_pairs": [list(pair) for pair in PAIRS],
            "group": "C2 wr S5",
            "group_order": group_order,
        },
        "transformations_checked": transformations_checked,
        "orbit_size": len(images),
        "stabilizer_order": stabilizer_order,
        "canonical_blocks": [list(block) for block in canonical],
        "canonical_sha256": hashlib.sha256(canonical_text.encode()).hexdigest(),
        "elapsed_seconds": time.monotonic() - started,
        "claim_limit": (
            "Exactly classifies only the supplied link under the stated 3,840-element group. "
            "It does not count or exhaust all C(11,5,3) links and does not settle C(12,6,4)."
        ),
    }
    if blocking_cnf is not None:
        result["orbit_blocking_cnf"] = write_blocking_cnf(blocking_cnf, images)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("link", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocking-cnf", type=Path)
    args = parser.parse_args()
    result = analyze(args.link, args.blocking_cnf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
