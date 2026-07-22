#!/usr/bin/env python3
"""Independent cell-count audit of the complete fifth-block partition."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
TARGET = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split/manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def audit() -> dict[str, object]:
    manifest = json.loads(TARGET.read_text())
    open_path = ROOT / manifest["open_fourth_manifest"]["path"]
    if sha(open_path) != manifest["open_fourth_manifest"]["sha256"]:
        raise ValueError("open fourth manifest hash mismatch")
    opened = json.loads(open_path.read_text())
    open_by_id = {row["id"]: row for row in opened["open_cases"]}
    if len(open_by_id) != 384 or len(manifest["parents"]) != 384:
        raise ValueError("fifth parent set is not exactly the audited open set")
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    seen_parents = set()
    summaries = []
    total = 0
    for parent in manifest["parents"]:
        parent_id = parent["id"]
        if parent_id in seen_parents or parent_id not in open_by_id:
            raise ValueError(f"duplicate or foreign parent {parent_id}")
        seen_parents.add(parent_id)
        source = open_by_id[parent_id]
        cnf_path = ROOT / parent["third_level_parent_cnf"]["path"]
        if sha(cnf_path) != parent["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{parent_id}: parent CNF hash mismatch")
        cnf = CNF(from_file=str(cnf_path))
        fixed = tuple(tuple(block) for block in parent["fixed_blocks"])
        if fixed != tuple(tuple(block) for block in source["fixed_blocks"]):
            raise ValueError(f"{parent_id}: fixed-block binding mismatch")
        fourth = source["fourth_branch"]
        inherited_units = [-value for value in fourth["earlier_fourth_variables_forced_false"]] + [fourth["canonical_fourth_block_variable"]]
        if inherited_units != parent["inherited_fourth_units"] or unit_sha(inherited_units) != parent["inherited_fourth_unit_sha256"]:
            raise ValueError(f"{parent_id}: inherited unit recipe mismatch")
        absent = {-clause[0] for clause in cnf.clauses if len(clause) == 1 and -462 <= clause[0] < 0}
        absent.update(fourth["earlier_fourth_variables_forced_false"])
        available = set(BLOCKS) - {BLOCKS[value - 1] for value in absent} - set(fixed)

        cells: dict[tuple[bool, ...], tuple[int, ...]] = {}
        for signature in itertools.product((False, True), repeat=4):
            cell = tuple(point for point in POINTS if tuple(point in block for block in fixed) == signature)
            if cell:
                cells[signature] = cell
        stabilizer_order = math.prod(math.factorial(len(cell)) for cell in cells.values())
        if stabilizer_order != parent["stabilizer_order"]:
            raise ValueError(f"{parent_id}: stabilizer order mismatch")
        groups: dict[tuple[int, ...], set[tuple[int, ...]]] = defaultdict(set)
        for block in available:
            key = tuple(len(set(block) & set(cell)) for _, cell in sorted(cells.items()))
            groups[key].add(block)
        expected_orbits = sorted(groups.values(), key=min)
        if len(expected_orbits) != parent["branch_count"] or sum(map(len, expected_orbits)) != parent["eligible_fifth_blocks"]:
            raise ValueError(f"{parent_id}: orbit count/coverage mismatch")
        for recorded, orbit in zip(parent["fifth_orbits"], expected_orbits):
            variables = [positions[block] for block in sorted(orbit)]
            if recorded["canonical_block"] != list(min(orbit)) or recorded["member_variables"] != variables or recorded["size"] != len(orbit):
                raise ValueError(f"{parent_id}: recorded fifth orbit mismatch")
        total += len(expected_orbits)
        summaries.append({"id": parent_id, "branches": len(expected_orbits), "eligible_blocks": len(available), "stabilizer_order": stabilizer_order})
    if seen_parents != set(open_by_id) or total != manifest["total_branches"]:
        raise ValueError("parent or global branch coverage mismatch")
    return {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": sha(TARGET),
        "parent_count": len(summaries),
        "total_branches": total,
        "parents": summaries,
        "coverage": "For each open fourth case, every additional selected block has one membership-count vector across the four-block cells. Those vectors are exactly the stabilizer orbits; the first-present rule is exhaustive and orbit-level disjoint.",
        "completion_standard": "This certifies the partition only. A fourth parent closes only after all its fifth children replay UNSAT or a directly validated new ordinary class appears.",
    }


if __name__ == "__main__":
    report = audit()
    output = TARGET.parent / "independent-partition-audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "manifest_sha256", "parent_count", "total_branches", "coverage")}, indent=2, sort_keys=True))
