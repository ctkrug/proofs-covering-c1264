#!/usr/bin/env python3
"""Independent coverage and reconstruction audit of the compact fourth split."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
TARGET = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fourth-split/manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def independent_actions(fixed: tuple[tuple[int, ...], ...]) -> list[dict[int, int]]:
    groups: dict[tuple[int, ...], list[int]] = {}
    for point in POINTS:
        signature = tuple(index for index, block in enumerate(fixed) if point in block)
        groups.setdefault(signature, []).append(point)
    actions = []
    sources = [tuple(group) for _, group in sorted(groups.items())]
    for targets in itertools.product(*(tuple(itertools.permutations(group)) for group in sources)):
        action = {}
        for source, target in zip(sources, targets):
            action.update(zip(source, target))
        actions.append(action)
    return actions


def audit() -> dict[str, object]:
    manifest = json.loads(TARGET.read_text())
    source_path = ROOT / manifest["source_manifest"]["path"]
    if sha(source_path) != manifest["source_manifest"]["sha256"]:
        raise ValueError("source manifest hash mismatch")
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    rows = []
    for parent in manifest["parents"]:
        cnf_path = ROOT / parent["parent_cnf"]["path"]
        if sha(cnf_path) != parent["parent_cnf"]["sha256"]:
            raise ValueError(f"{parent['id']}: parent CNF hash mismatch")
        cnf = CNF(from_file=str(cnf_path))
        absent = {-clause[0] for clause in cnf.clauses if len(clause) == 1 and -462 <= clause[0] < 0}
        fixed = tuple(tuple(block) for block in parent["fixed_blocks"])
        actions = independent_actions(fixed)
        if len(actions) != parent["stabilizer_order"]:
            raise ValueError(f"{parent['id']}: stabilizer order mismatch")
        unseen = set(BLOCKS) - {BLOCKS[var - 1] for var in absent} - set(fixed)
        orbits = []
        while unseen:
            seed = min(unseen)
            orbit = {tuple(sorted(action[point] for point in seed)) for action in actions}
            if not orbit <= unseen:
                raise ValueError(f"{parent['id']}: orbit partition overlap")
            orbits.append(orbit)
            unseen -= orbit
        if len(orbits) != parent["branch_count"]:
            raise ValueError(f"{parent['id']}: branch count mismatch")
        earlier: set[tuple[int, ...]] = set()
        for branch, orbit in zip(parent["branches"], orbits):
            canonical = min(orbit)
            false_vars = [positions[block] for block in sorted(earlier)]
            assumptions = [-var for var in false_vars] + [positions[canonical]]
            recipe_sha = hashlib.sha256((" ".join(map(str, assumptions)) + "\n").encode()).hexdigest()
            if branch["canonical_fourth_block"] != list(canonical) or branch["earlier_fourth_variables_forced_false"] != false_vars or branch["unit_recipe_sha256"] != recipe_sha:
                raise ValueError(f"{branch['id']}: branch recipe mismatch")
            earlier.update(orbit)
        rows.append({"id": parent["id"], "branches": len(orbits), "eligible_blocks": sum(map(len, orbits)), "stabilizer_order": len(actions)})
    return {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": sha(TARGET),
        "parents": rows,
        "total_branches": sum(row["branches"] for row in rows),
        "coverage": "Every model in each timeout parent selects a fourth block in exactly one first-present stabilizer orbit; the stabilizer maps that selected block to the recorded representative.",
        "claim_limit": "Partition and recipe audit only; no branch is closed by this audit.",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
