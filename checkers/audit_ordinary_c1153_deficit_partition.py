#!/usr/bin/env python3
"""Independent exact audit of the all-timeout uncovered-triple partition."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path


POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def independent_actions(fixed: tuple[frozenset[int], ...], triple: frozenset[int]) -> list[tuple[int, ...]]:
    buckets: dict[tuple[bool, ...], list[int]] = {}
    for point in POINTS:
        buckets.setdefault(tuple(point in block for block in fixed), []).append(point)
    groups = list(buckets.values())
    expected = math.prod(math.factorial(len(group)) for group in groups)
    actions = []
    for images in itertools.product(*(itertools.permutations(group) for group in groups)):
        mapping = dict(zip(POINTS, POINTS))
        for group, image in zip(groups, images):
            mapping.update(zip(group, image))
        if frozenset(mapping[p] for p in triple) == triple:
            actions.append(tuple(mapping[p] for p in POINTS))
    if expected < len(actions) or not actions:
        raise AssertionError("invalid independently reconstructed action group")
    return actions


def audit(root: Path, manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text())
    source_path = root / manifest["source"]["path"]
    if digest(source_path) != manifest["source"]["sha256"]:
        raise ValueError("source hash mismatch")
    source = json.loads(source_path.read_text())
    source_by_id = {case["id"]: case for case in source["cases"]}
    if len(source_by_id) != 82 or {case["id"] for case in manifest["cases"]} != set(source_by_id):
        raise ValueError("all-82 membership mismatch")
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    total = 0
    generic = 0
    for row in manifest["cases"]:
        source_row = source_by_id[row["id"]]
        if row["fixed_blocks"] != source_row["fixed_blocks"] or row["inherited_units"] != source_row["inherited_units"]:
            raise ValueError(f"{row['id']}: source recipe changed")
        fixed = tuple(frozenset(block) for block in row["fixed_blocks"])
        triple = frozenset(row["chosen_uncovered_triple"])
        if len(triple) != 3 or any(triple <= block for block in fixed):
            raise ValueError(f"{row['id']}: triple is not a live coverage deficit")
        absent = {-value for value in row["inherited_units"] if value < 0}
        available = {block for block in BLOCKS if positions[block] not in absent and frozenset(block) not in fixed}
        coverers = {block for block in available if triple <= frozenset(block)}
        actions = independent_actions(fixed, triple)
        remaining = set(coverers)
        expected_orbits = []
        while remaining:
            seed = min(remaining)
            orbit = {
                tuple(sorted(action[p - 1] for p in seed))
                for action in actions
            }
            if not orbit <= remaining:
                raise ValueError(f"{row['id']}: independently reconstructed orbit escaped")
            expected_orbits.append(sorted(positions[block] for block in orbit))
            remaining -= orbit
        recorded = [orbit["member_variables"] for orbit in row["covering_block_orbits"]]
        if recorded != expected_orbits:
            raise ValueError(f"{row['id']}: orbit partition mismatch")
        if row["eligible_covering_blocks"] != len(coverers) or row["branch_count"] != len(recorded):
            raise ValueError(f"{row['id']}: count mismatch")
        if any(orbit["canonical_variable"] != orbit["member_variables"][0] for orbit in row["covering_block_orbits"]):
            raise ValueError(f"{row['id']}: noncanonical representative")
        total += len(recorded)
        generic += source_row["branch_count"]
    if total != manifest["deficit_children"] or generic != manifest["generic_sixth_children"]:
        raise ValueError("aggregate mismatch")
    return {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": digest(manifest_path),
        "source_sha256": digest(source_path),
        "case_count": 82,
        "generic_sixth_children": generic,
        "deficit_children": total,
        "reduction_fraction": 1 - total / generic,
        "checked_properties": [
            "exact all-82 membership and unchanged inherited recipes",
            "chosen triple uncovered by every fixed block",
            "eligible covering-block domain reconstructed independently",
            "triple-stabilizer orbits exhaustive and pairwise disjoint",
            "first-occupied-orbit recipes exhaustive and disjoint",
        ],
        "claim_limit": "VALID certifies the partition only; it is not a solver closure.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = audit(root, args.manifest)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
