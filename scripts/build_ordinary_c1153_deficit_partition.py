#!/usr/bin/env python3
"""Build a coverage-deficit partition for every final fifth-level timeout.

For each five-block prefix, choose an uncovered triple whose eligible covering
blocks have the fewest orbits under the prefix stabilizer that also fixes the
triple setwise.  Every completion must select a covering block, so branching
on the first occupied covering-block orbit is exhaustive and disjoint.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
TRIPLES = tuple(itertools.combinations(POINTS, 3))
SOURCE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-sixth-discriminator-final/manifest.json"
TARGET = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-deficit-partition"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe_sha(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + "\n").encode()).hexdigest()


def prefix_actions(fixed: tuple[tuple[int, ...], ...]) -> list[dict[int, int]]:
    cells = []
    for point in POINTS:
        signature = tuple(point in block for block in fixed)
        if not any(signature == row[0] for row in cells):
            cells.append((signature, tuple(q for q in POINTS if tuple(q in block for block in fixed) == signature)))
    groups = [row[1] for row in cells]
    actions = []
    for choices in itertools.product(*(itertools.permutations(group) for group in groups)):
        action = {}
        for source, image in zip(groups, choices):
            action.update(zip(source, image))
        actions.append(action)
    if len(actions) != math.prod(math.factorial(len(group)) for group in groups):
        raise AssertionError("prefix stabilizer size mismatch")
    return actions


def orbits(values: set[tuple[int, ...]], actions: list[dict[int, int]]) -> list[list[tuple[int, ...]]]:
    unseen = set(values)
    rows = []
    while unseen:
        seed = min(unseen)
        orbit = {tuple(sorted(action[p] for p in seed)) for action in actions}
        if not orbit <= unseen:
            raise ValueError("orbit escaped eligible covering-block domain")
        row = sorted(orbit)
        rows.append(row)
        unseen -= orbit
    return rows


def build() -> dict[str, object]:
    source = json.loads(SOURCE.read_text())
    if source["case_count"] != 82:
        raise ValueError("expected the frozen all-82 timeout manifest")
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    cases = []
    generic_total = 0
    deficit_total = 0
    for case in source["cases"]:
        fixed = tuple(tuple(block) for block in case["fixed_blocks"])
        inherited = list(case["inherited_units"])
        absent = {-value for value in inherited if value < 0}
        available = set(BLOCKS) - {BLOCKS[value - 1] for value in absent} - set(fixed)
        actions = prefix_actions(fixed)
        candidates = []
        for triple in TRIPLES:
            if any(set(triple) <= set(block) for block in fixed):
                continue
            covering = {block for block in available if set(triple) <= set(block)}
            if not covering:
                raise ValueError(f"{case['id']}: uncovered triple has no available coverer")
            triple_set = set(triple)
            subgroup = [action for action in actions if {action[p] for p in triple} == triple_set]
            rows = orbits(covering, subgroup)
            candidates.append((len(rows), len(covering), triple, subgroup, rows))
        branch_count, eligible_count, triple, subgroup, rows = min(candidates, key=lambda row: row[:3])
        orbit_rows = []
        for index, row in enumerate(rows):
            member_variables = [positions[block] for block in row]
            orbit_rows.append({
                "index": index,
                "canonical_block": list(row[0]),
                "canonical_variable": member_variables[0],
                "member_variables": member_variables,
                "size": len(row),
            })
        cases.append({
            "id": case["id"],
            "top_parent": case["top_parent"],
            "fifth_position": case["fifth_position"],
            "fixed_blocks": case["fixed_blocks"],
            "third_level_parent_cnf": case["third_level_parent_cnf"],
            "inherited_units": inherited,
            "inherited_unit_sha256": recipe_sha(inherited),
            "prefix_stabilizer_order": len(actions),
            "chosen_uncovered_triple": list(triple),
            "triple_stabilizer_order": len(subgroup),
            "eligible_covering_blocks": eligible_count,
            "generic_sixth_branch_count": case["branch_count"],
            "branch_count": branch_count,
            "covering_block_orbits": orbit_rows,
        })
        generic_total += case["branch_count"]
        deficit_total += branch_count
    manifest = {
        "schema_version": 1,
        "status": "BUILT_NOT_SOLVED",
        "source": {"path": str(SOURCE.relative_to(ROOT)), "sha256": sha(SOURCE), "case_count": 82},
        "hypothesis": "Early-prefix hardness is caused by broad arbitrary-next-block choice. Branching on a currently uncovered triple should collapse the search because every completion must select one of at most 28 blocks covering that deficit.",
        "invariant": "For the chosen triple T, no fixed block covers T. Every C(11,5,3) completion covers T, hence contains an available block covering T.",
        "partition_rule": "Restrict the five-block prefix stabilizer to permutations fixing T setwise; partition available T-covering blocks into its orbits; select the least occupied orbit, force earlier covering orbits absent, and map one selected block to the orbit representative.",
        "exhaustiveness_reason": "Every completion occupies at least one T-covering orbit. The least occupied orbit is unique, and the T stabilizer maps a selected member to the recorded canonical block without changing the prefix or T.",
        "representation": "Append inherited units to the bound third-level CNF, then append negative units for all members of earlier covering-block orbits and the selected orbit's canonical positive unit.",
        "case_count": len(cases),
        "generic_sixth_children": generic_total,
        "deficit_children": deficit_total,
        "reduction_fraction": 1 - deficit_total / generic_total,
        "cases": cases,
        "claim_limit": "This is a structural completeness partition, not a solver result. No parent closes until every child has a replay-certified terminal result.",
    }
    TARGET.mkdir(parents=True, exist_ok=False)
    path = TARGET / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: manifest[key] for key in ("case_count", "generic_sixth_children", "deficit_children", "reduction_fraction")}, sort_keys=True))
    return manifest


if __name__ == "__main__":
    build()
