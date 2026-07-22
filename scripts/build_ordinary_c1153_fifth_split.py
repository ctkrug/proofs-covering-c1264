#!/usr/bin/env python3
"""Build a compact canonical fifth-block partition of every open fourth case."""

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
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1"
OPEN_PATH = BASE / "hard-tail-fourth-split/open-fourth-level-manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def stabilizer(fixed: tuple[tuple[int, ...], ...]) -> list[dict[int, int]]:
    cells = []
    for signature in itertools.product((False, True), repeat=len(fixed)):
        cell = tuple(point for point in POINTS if tuple(point in block for block in fixed) == signature)
        if cell:
            cells.append(cell)
    actions = []
    for choices in itertools.product(*(tuple(itertools.permutations(cell)) for cell in cells)):
        action = {}
        for source, target in zip(cells, choices):
            action.update(zip(source, target))
        actions.append(action)
    if len(actions) != math.prod(math.factorial(len(cell)) for cell in cells):
        raise AssertionError("stabilizer enumeration mismatch")
    return actions


def build() -> dict[str, object]:
    opened = json.loads(OPEN_PATH.read_text())
    if opened["counts"]["open"] != 384:
        raise ValueError("open-set ledger changed")
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    parents = []
    total = 0
    for row in opened["open_cases"]:
        parent_path = ROOT / row["parent_cnf"]["path"]
        if sha(parent_path) != row["parent_cnf"]["sha256"]:
            raise ValueError(f"{row['id']}: third-level parent CNF hash mismatch")
        parent_cnf = CNF(from_file=str(parent_path))
        inherited_absent = {-clause[0] for clause in parent_cnf.clauses if len(clause) == 1 and -462 <= clause[0] < 0}
        fourth = row["fourth_branch"]
        fourth_units = [-value for value in fourth["earlier_fourth_variables_forced_false"]] + [fourth["canonical_fourth_block_variable"]]
        inherited_absent.update(fourth["earlier_fourth_variables_forced_false"])
        fixed = tuple(tuple(block) for block in row["fixed_blocks"])
        if len(fixed) != 4:
            raise ValueError(f"{row['id']}: expected four fixed blocks")
        actions = stabilizer(fixed)
        unseen = set(BLOCKS) - {BLOCKS[value - 1] for value in inherited_absent} - set(fixed)
        orbit_rows = []
        while unseen:
            seed = min(unseen)
            orbit = {tuple(sorted(action[point] for point in seed)) for action in actions}
            if not orbit <= unseen:
                raise ValueError(f"{row['id']}: fifth orbit overlap")
            member_variables = [positions[block] for block in sorted(orbit)]
            orbit_rows.append({
                "index": len(orbit_rows),
                "canonical_block": list(min(orbit)),
                "canonical_variable": positions[min(orbit)],
                "member_variables": member_variables,
                "size": len(orbit),
            })
            unseen -= orbit
        parents.append({
            "id": row["id"],
            "prior_status": row["status"],
            "top_parent": row["top_parent"],
            "fixed_blocks": [list(block) for block in fixed],
            "third_level_parent_cnf": row["parent_cnf"],
            "inherited_fourth_units": fourth_units,
            "inherited_fourth_unit_sha256": unit_sha(fourth_units),
            "stabilizer_order": len(actions),
            "eligible_fifth_blocks": sum(orbit["size"] for orbit in orbit_rows),
            "branch_count": len(orbit_rows),
            "fifth_orbits": orbit_rows,
        })
        total += len(orbit_rows)
    manifest = {
        "schema_version": 1,
        "status": "BUILT_NOT_SOLVED",
        "open_fourth_manifest": {"path": str(OPEN_PATH.relative_to(ROOT)), "sha256": sha(OPEN_PATH)},
        "parent_count": len(parents),
        "total_branches": total,
        "representation": "An exact fifth child is reconstructed from the bound third-level CNF, inherited fourth-level unit recipe, negative units for every member of earlier fifth orbits, and the current orbit's canonical positive unit.",
        "partition_rule": "Under the setwise stabilizer of all four fixed blocks, select the first present fifth-block orbit, force every earlier orbit absent, and map the selected block to the orbit's canonical representative.",
        "parents": parents,
        "completion_standard": "An open fourth parent closes only if every fifth child has an independently replayed UNSAT proof, unless a directly validated nonisomorphic ordinary cover is found.",
        "claim_limit": "Partition recipes only; no solver outcome or classification completeness is implied.",
    }
    target_dir = BASE / "hard-tail-fifth-split"
    target_dir.mkdir(exist_ok=False)
    target = target_dir / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(target), "parents": len(parents), "branches": total, "bytes": target.stat().st_size}, sort_keys=True))
    return manifest


if __name__ == "__main__":
    build()
