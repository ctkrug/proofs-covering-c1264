#!/usr/bin/env python3
"""Build a compact, complete fourth-block split for the 13 hard timeouts.

The manifest stores parent-CNF bindings and unit-clause recipes.  Exact child
CNFs are reconstructed on demand, avoiding roughly a gigabyte of duplicated
base clauses while retaining byte-level reproducibility.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
ROOT_BLOCK = (1, 2, 3, 4, 5)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stabilizer(fixed: tuple[tuple[int, ...], ...]) -> list[dict[int, int]]:
    cells = {}
    for signature in itertools.product((False, True), repeat=len(fixed)):
        cell = tuple(point for point in POINTS if tuple(point in block for block in fixed) == signature)
        if cell:
            cells[signature] = cell
    actions = []
    permutations = [tuple(itertools.permutations(cell)) for cell in cells.values()]
    for choices in itertools.product(*permutations):
        action = {}
        for source, target in zip(cells.values(), choices):
            action.update(zip(source, target))
        actions.append(action)
    expected = math.prod(math.factorial(len(cell)) for cell in cells.values())
    if len(actions) != expected:
        raise AssertionError("cell stabilizer order mismatch")
    return actions


def build() -> dict[str, object]:
    source_path = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-split/manifest.json"
    source = json.loads(source_path.read_text())
    output = source_path.parent.parent / "hard-tail-fourth-split"
    output.mkdir(exist_ok=False)
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    parents = []
    total = 0
    for top_parent in source["parents"]:
        second = tuple(top_parent["fixed_second_block"])
        for child in top_parent["children"]:
            result_path = ROOT / child["result"]["path"]
            if json.loads(result_path.read_text())["status"] != "FIXED_CAP_TIMEOUT":
                continue
            cnf_path = ROOT / child["cnf"]["path"]
            if sha(cnf_path) != child["cnf"]["sha256"]:
                raise ValueError(f"{child['id']}: parent CNF hash mismatch")
            parent_cnf = CNF(from_file=str(cnf_path))
            absent = {-clause[0] for clause in parent_cnf.clauses if len(clause) == 1 and -462 <= clause[0] < 0}
            third = tuple(child["canonical_third_block"])
            fixed = (ROOT_BLOCK, second, third)
            actions = stabilizer(fixed)
            unseen = set(BLOCKS) - {BLOCKS[var - 1] for var in absent} - set(fixed)
            orbits = []
            while unseen:
                seed = min(unseen)
                orbit = {tuple(sorted(action[point] for point in seed)) for action in actions}
                if not orbit <= unseen:
                    raise AssertionError(f"{child['id']}: fourth-block orbit overlap")
                orbits.append(orbit)
                unseen -= orbit
            branches = []
            earlier: set[tuple[int, ...]] = set()
            for index, orbit in enumerate(orbits):
                canonical = min(orbit)
                false_vars = [positions[block] for block in sorted(earlier)]
                assumptions = [-var for var in false_vars] + [positions[canonical]]
                recipe_bytes = (" ".join(map(str, assumptions)) + "\n").encode()
                branch_id = f"{child['id']}-fourth-{index:03d}"
                branches.append({
                    "id": branch_id,
                    "index": index,
                    "canonical_fourth_block": list(canonical),
                    "canonical_fourth_block_variable": positions[canonical],
                    "fourth_block_orbit_size": len(orbit),
                    "earlier_fourth_variables_forced_false": false_vars,
                    "unit_recipe_sha256": hashlib.sha256(recipe_bytes).hexdigest(),
                    "added_clause_count": len(assumptions),
                })
                earlier.update(orbit)
            parents.append({
                "id": child["id"],
                "top_parent": top_parent["id"],
                "fixed_blocks": [list(block) for block in fixed],
                "parent_cnf": child["cnf"],
                "stabilizer_order": len(actions),
                "eligible_fourth_blocks": sum(len(orbit) for orbit in orbits),
                "branch_count": len(branches),
                "branches": branches,
            })
            total += len(branches)
    manifest = {
        "schema_version": 1,
        "status": "BUILT_NOT_SOLVED",
        "source_manifest": {"path": str(source_path.relative_to(ROOT)), "sha256": sha(source_path)},
        "representation": "Each exact child CNF is the bound parent CNF followed by the listed negative unit clauses, then the canonical positive unit clause. It is reconstructed on demand.",
        "partition_rule": "Choose the first present fourth-block orbit under the setwise stabilizer of the three fixed blocks; force all earlier fourth-block orbits absent and one canonical representative present.",
        "parents": parents,
        "parent_count": len(parents),
        "total_branches": total,
        "completion_standard": "A timeout parent closes only after every branch has an independently replayed UNSAT proof, unless a directly validated nonisomorphic ordinary cover is found.",
        "claim_limit": "Partition recipe only; no solver result is implied.",
    }
    target = output / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(target), "parents": len(parents), "branches": total}, sort_keys=True))
    return manifest


if __name__ == "__main__":
    build()
