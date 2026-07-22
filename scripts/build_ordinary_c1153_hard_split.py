#!/usr/bin/env python3
"""Split the two hard ordinary-link parents by a complete third-block orbit partition."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
ROOT_BLOCK = (1, 2, 3, 4, 5)
PARENTS = ("intersection-4", "intersection-3")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def root_stabilizer() -> list[dict[int, int]]:
    complement = tuple(p for p in POINTS if p not in set(ROOT_BLOCK))
    actions = []
    for inside in itertools.permutations(ROOT_BLOCK):
        left = dict(zip(ROOT_BLOCK, inside))
        for outside in itertools.permutations(complement):
            action = dict(left)
            action.update(zip(complement, outside))
            actions.append(action)
    if len(actions) != 86400:
        raise AssertionError("root stabilizer order changed")
    return actions


def partition(parent: dict[str, object], actions: list[dict[int, int]]) -> tuple[list[set[tuple[int, ...]]], int]:
    second = tuple(parent["canonical_second_block"])
    stabilizer = [a for a in actions if tuple(sorted(a[p] for p in second)) == second]
    earlier_count = int(parent["earlier_orbit_variables_forced_false"])
    overlap = int(parent["minimum_present_second_block_intersection"])
    order = (4, 3, 2, 1, 0)
    earlier_overlaps = order[:order.index(overlap)]
    earlier = {b for b in BLOCKS if b != ROOT_BLOCK and len(set(b) & set(ROOT_BLOCK)) in earlier_overlaps}
    if len(earlier) != earlier_count:
        raise AssertionError("parent earlier-orbit count mismatch")
    unseen = set(BLOCKS) - earlier - {ROOT_BLOCK, second}
    orbits = []
    while unseen:
        seed = min(unseen)
        orbit = {tuple(sorted(a[p] for p in seed)) for a in stabilizer}
        if not orbit <= unseen:
            raise AssertionError("third-block orbit overlap")
        orbits.append(orbit)
        unseen -= orbit
    return orbits, len(stabilizer)


def build() -> dict[str, object]:
    base = ROOT / "artifacts/classification/ordinary-c1153-v1"
    top_manifest_path = base / "manifest.json"
    top = json.loads(top_manifest_path.read_text())
    by_id = {leaf["id"]: leaf for leaf in top["leaves"]}
    output = base / "hard-split"
    output.mkdir(exist_ok=False)
    positions = {block: i for i, block in enumerate(BLOCKS, 1)}
    actions = root_stabilizer()
    parents = []
    total = 0
    for parent_id in PARENTS:
        parent = by_id[parent_id]
        parent_cnf_path = ROOT / parent["cnf"]["path"]
        if sha(parent_cnf_path) != parent["cnf"]["sha256"]:
            raise ValueError("parent CNF hash mismatch")
        parent_cnf = CNF(from_file=str(parent_cnf_path))
        orbits, stabilizer_order = partition(parent, actions)
        parent_folder = output / parent_id
        parent_folder.mkdir()
        children = []
        earlier: set[tuple[int, ...]] = set()
        for index, orbit in enumerate(orbits):
            canonical = min(orbit)
            tail = [[-positions[b]] for b in sorted(earlier)] + [[positions[canonical]]]
            cnf = CNF(from_clauses=parent_cnf.clauses + tail)
            child_id = f"{parent_id}-third-{index:02d}"
            folder = parent_folder / child_id
            folder.mkdir()
            cnf_path = folder / "instance.cnf"
            cnf.to_file(str(cnf_path))
            result_path = folder / "result.json"
            result_path.write_text(json.dumps({"schema_version": 1, "status": "NOT_RUN"}, indent=2) + "\n")
            children.append({
                "id": child_id,
                "index": index,
                "canonical_third_block": list(canonical),
                "canonical_third_block_variable": positions[canonical],
                "third_block_orbit_size": len(orbit),
                "earlier_third_variables_forced_false": len(earlier),
                "cnf": {"path": str(cnf_path.relative_to(ROOT)), "sha256": sha(cnf_path), "bytes": cnf_path.stat().st_size, "variables": cnf.nv, "clauses": len(cnf.clauses)},
                "result": {"path": str(result_path.relative_to(ROOT)), "sha256": sha(result_path)},
            })
            earlier.update(orbit)
        parents.append({
            "id": parent_id,
            "parent_cnf": parent["cnf"],
            "fixed_second_block": parent["canonical_second_block"],
            "stabilizer_order": stabilizer_order,
            "eligible_third_blocks": sum(len(orbit) for orbit in orbits),
            "child_count": len(children),
            "children": children,
        })
        total += len(children)
    manifest = {
        "schema_version": 1,
        "status": "BUILT_NOT_SOLVED",
        "top_manifest": {"path": str(top_manifest_path.relative_to(ROOT)), "sha256": sha(top_manifest_path)},
        "partition_rule": "For each hard parent, choose the first present third-block orbit under the stabilizer of the fixed root and second blocks; force earlier orbits absent and a canonical member present.",
        "parents": parents,
        "total_children": total,
        "expected_counts": {"intersection-4": 17, "intersection-3": 25},
        "completion_standard": "A parent closes only when every child is replay-verified UNSAT, unless a directly validated nonisomorphic SAT cover is found.",
        "claim_limit": "Built partition only; no child solver status is counted before independent CNF/coverage audit and certificate replay.",
    }
    path = output / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))
    return manifest


if __name__ == "__main__":
    build()
