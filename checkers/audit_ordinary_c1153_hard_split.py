#!/usr/bin/env python3
"""Independent exact audit of the 42-child ordinary-link hard split."""

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


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_stabilizer(second: tuple[int, ...]) -> list[dict[int, int]]:
    cells: dict[tuple[bool, bool], tuple[int, ...]] = {}
    for key in itertools.product((False, True), repeat=2):
        cells[key] = tuple(p for p in POINTS if (p in ROOT_BLOCK, p in second) == key)
    actions = []
    permutations = [tuple(itertools.permutations(cell)) for cell in cells.values()]
    for choices in itertools.product(*permutations):
        mapping = {}
        for source, target in zip(cells.values(), choices):
            mapping.update(zip(source, target))
        actions.append(mapping)
    return actions


def audit() -> dict[str, object]:
    split_path = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-split/manifest.json"
    split = json.loads(split_path.read_text())
    top_path = ROOT / split["top_manifest"]["path"]
    if sha(top_path) != split["top_manifest"]["sha256"]:
        raise ValueError("top manifest hash mismatch")
    top = json.loads(top_path.read_text())
    top_by_id = {leaf["id"]: leaf for leaf in top["leaves"]}
    positions = {block: i for i, block in enumerate(BLOCKS, 1)}
    audited = []
    for parent in split["parents"]:
        top_parent = top_by_id[parent["id"]]
        parent_path = ROOT / top_parent["cnf"]["path"]
        if sha(parent_path) != parent["parent_cnf"]["sha256"]:
            raise ValueError("parent binding mismatch")
        parent_cnf = CNF(from_file=str(parent_path))
        second = tuple(parent["fixed_second_block"])
        actions = cell_stabilizer(second)
        if len(actions) != parent["stabilizer_order"]:
            raise ValueError("stabilizer order mismatch")
        overlap = len(set(second) & set(ROOT_BLOCK))
        earlier_overlaps = (4, 3, 2, 1, 0)[:(4, 3, 2, 1, 0).index(overlap)]
        earlier_second = {b for b in BLOCKS if b != ROOT_BLOCK and len(set(b) & set(ROOT_BLOCK)) in earlier_overlaps}
        unseen = set(BLOCKS) - earlier_second - {ROOT_BLOCK, second}
        orbits = []
        while unseen:
            seed = min(unseen)
            orbit = {tuple(sorted(action[p] for p in seed)) for action in actions}
            if not orbit <= unseen:
                raise ValueError("orbit partition overlap")
            orbits.append(orbit)
            unseen -= orbit
        if len(orbits) != parent["child_count"] or sum(map(len, orbits)) != parent["eligible_third_blocks"]:
            raise ValueError("child partition count mismatch")
        earlier: set[tuple[int, ...]] = set()
        for child, orbit in zip(parent["children"], orbits):
            canonical = min(orbit)
            if list(canonical) != child["canonical_third_block"]:
                raise ValueError("canonical third block mismatch")
            expected = parent_cnf.clauses + [[-positions[b]] for b in sorted(earlier)] + [[positions[canonical]]]
            cnf_path = ROOT / child["cnf"]["path"]
            actual = CNF(from_file=str(cnf_path))
            if sha(cnf_path) != child["cnf"]["sha256"] or actual.clauses != expected:
                raise ValueError("child exact reconstruction failed")
            earlier.update(orbit)
        audited.append({"id": parent["id"], "children": len(orbits), "stabilizer_order": len(actions), "eligible_third_blocks": len(set().union(*orbits))})
    return {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": sha(split_path),
        "parents": audited,
        "total_children": sum(row["children"] for row in audited),
        "coverage": "Every selected model in each parent has an additional block in exactly one first-present third-block orbit; cell-stabilizer transitivity maps that block to the frozen representative.",
        "claim_limit": "Exact partition/CNF audit only; no parent closes until all child certificates replay.",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
