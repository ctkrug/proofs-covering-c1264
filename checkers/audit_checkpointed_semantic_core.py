#!/usr/bin/env python3
"""Audit the replayed 88-group fifth-orbit obstruction and its pair skeleton."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = Path("artifacts/discoveries/link-orbit-s-r1-3/residual-extension")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit() -> dict[str, object]:
    core_path = ROOT / BASE / "semantic-core-checkpointed.json"
    solver_path = ROOT / BASE / "semantic-core-checkpointed-solver.json"
    validation_path = ROOT / BASE / "semantic-core-checkpointed-validation.json"
    core = json.loads(core_path.read_text())
    solver = json.loads(solver_path.read_text())
    validation = json.loads(validation_path.read_text())
    groups = core["semantic_groups"]
    pairs = [row for row in groups if row["kind"] == "pair_equality"]
    assert core["seed_core"]["groups"] == 161
    assert core["core_groups"] == len(groups) == 88
    assert core["coverage_groups"] == 82 and core["pair_equality_groups"] == len(pairs) == 6
    assert solver["status"] == "UNSAT_PROVISIONAL" and solver["exit_code"] == 20
    assert validation["status"] == "verified" and validation["verdict"] == "s VERIFIED"
    assert core["core_cnf"]["sha256"] == solver["cnf"]["sha256"] == validation["cnf"]["sha256"]
    assert solver["proof"]["sha256"] == validation["proof"]["sha256"]
    graph: dict[int, set[int]] = defaultdict(set)
    edges = []
    for row in pairs:
        a, b = row["pair"]
        graph[a].add(b); graph[b].add(a); edges.append([a, b])
        assert row["link_multiplicity"] == 4 and row["residual_bound"] == 5
    vertices = set(graph)
    seen = set()
    stack = [next(iter(vertices))]
    while stack:
        v = stack.pop()
        if v in seen:
            continue
        seen.add(v); stack.extend(graph[v] - seen)
    degrees = sorted((len(graph[v]) for v in vertices), reverse=True)
    assert len(vertices) == 7 and len(edges) == 6 and seen == vertices
    assert degrees == [3, 2, 2, 2, 1, 1, 1]
    statuses = Counter(row["status"] for row in core["attempts"])
    return {
        "schema_version": 1,
        "status": "verified_unsat_obstruction",
        "seed_groups": 161,
        "certified_core_groups": 88,
        "coverage_groups": 82,
        "pair_equality_groups": 6,
        "minimization_attempts": core["attempted_groups"],
        "deletion_statuses": dict(sorted(statuses.items())),
        "pair_skeleton": {
            "kind": "tree",
            "vertices": sorted(vertices),
            "edges": sorted(edges),
            "degree_sequence": degrees,
        },
        "cnf": core["core_cnf"],
        "proof": solver["proof"],
        "sources": {
            "core": {"path": str(BASE / core_path.name), "sha256": sha(core_path)},
            "solver": {"path": str(BASE / solver_path.name), "sha256": sha(solver_path)},
            "replay": {"path": str(BASE / validation_path.name), "sha256": sha(validation_path)},
        },
        "claim_limit": "The 88 groups are a certified sufficient UNSAT obstruction, not a globally minimal MUS; four attempted deletions timed out and 66 groups were not attempted within the bounded pass.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=BASE / "semantic-core-checkpointed-audit.json")
    args = parser.parse_args()
    result = audit()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
