#!/usr/bin/env python3
"""Aggregate independent audits for the exact point-link classification domain."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checkers"))
from audit_link_orbit import all_actions  # noqa: E402
from audit_link_root_partition import audit as audit_roots  # noqa: E402
from audit_secondary_root_partition import audit as audit_secondary  # noqa: E402
from audit_tertiary_root_partition import audit as audit_tertiary  # noqa: E402
from audit_link_orbit_frontier import audit as audit_frontier  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(relative: str) -> dict[str, object]:
    path = ROOT / relative
    return {"path": relative, "sha256": sha(path), "bytes": path.stat().st_size}


def audit(manifest_relative: str) -> dict[str, object]:
    # A link at point 0 consists of the twenty 5-subsets obtained by deleting 0
    # from its incident 6-blocks.  Covering every {0}+triple gives all 165 triples.
    link_blocks = tuple(itertools.combinations(range(1, 12), 5))
    triples = tuple(itertools.combinations(range(1, 12), 3))
    if len(link_blocks) != 462 or len(triples) != 165:
        raise AssertionError("link universe counts changed")
    degree_vector = (10, *([9] * 10))
    if sum(degree_vector) != 5 * 20:
        raise AssertionError("link degree incidence identity failed")

    actions = all_actions()
    if len(actions) != 3840 or len(set(actions)) != 3840:
        raise AssertionError("C2 wr S5 action is incomplete")
    pairs = {frozenset(pair) for pair in ((2, 3), (4, 5), (6, 7), (8, 9), (10, 11))}
    for action in actions:
        if action[1] != 1:
            raise ValueError("action moves the distinguished degree-10 point")
        image = {frozenset((action[a], action[b])) for a, b in pairs}
        if image != pairs:
            raise ValueError("action does not preserve the five matched pairs")

    root_path = ROOT / "artifacts/pilot/link-root-partition.json"
    r0_path = ROOT / "artifacts/pilot/link-root-0-secondary-partition.json"
    r1_path = ROOT / "artifacts/pilot/link-root-1-secondary-partition.json"
    tertiary_path = ROOT / "artifacts/pilot/link-root0-secondary0-tertiary-partition.json"
    root = audit_roots(root_path)
    secondary0 = audit_secondary(r0_path)
    secondary1 = audit_secondary(r1_path)
    tertiary = audit_tertiary(tertiary_path)
    frontier_path = ROOT / manifest_relative
    frontier = audit_frontier(frontier_path)
    if root["covered_primary_variables"] != 462:
        raise ValueError("primary partition is incomplete")
    if secondary0["secondary_root_count"] != 39 or secondary1["secondary_root_count"] != 68:
        raise ValueError("secondary partition counts changed")
    if tertiary["tertiary_root_count"] != 122:
        raise ValueError("tertiary partition count changed")

    return {
        "schema_version": 1,
        "status": "valid",
        "classification_domain": {
            "objects": "20 distinct 5-subsets of {1,...,11} covering all 165 triples",
            "forced_degree_vector": [10, *([9] * 10)],
            "degree_10_point": 1,
            "matched_pairs_preserved": [[2, 3], [4, 5], [6, 7], [8, 9], [10, 11]],
            "candidate_primary_variables": 462,
            "naive_subsets": "choose(462,20) approximately 5.315e34",
            "derivation": "A hypothetical 40-cover has point degree 20 and pair multiplicities 10 on one perfect matching and 9 elsewhere; the link at a fixed point inherits these exact constraints.",
        },
        "symmetry": {
            "group": "C2 wr S5",
            "order": 3840,
            "actions_independently_enumerated": len(actions),
            "canonicalization_scope": "fix degree-10 point 1 and preserve the five matched pairs",
        },
        "partition_coverage": {
            "primary_roots": root["root_count"],
            "primary_variables_covered": root["covered_primary_variables"],
            "root_0_secondary_cases": secondary0["secondary_root_count"],
            "root_1_secondary_cases": secondary1["secondary_root_count"],
            "root_0_secondary_0_tertiary_cases": tertiary["tertiary_root_count"],
            "active_frontier_nodes": frontier["frontier_nodes"],
            "active_closed": frontier["closed"],
            "active_open": frontier["open"],
            "disjointness_and_prefix_coverage": "verified by independent orbit reconstruction",
        },
        "catalogue": {
            "canonical_orbits_found": frontier["catalog_orbits"],
            "blocked_images": frontier["blocked_link_images"],
            "exhaustive": False,
        },
        "inputs": [
            record("docs/BASELINE.md"),
            record("artifacts/baseline/link.opb"),
            record("artifacts/pilot/link-root-partition.json"),
            record("artifacts/pilot/link-root-0-secondary-partition.json"),
            record("artifacts/pilot/link-root-1-secondary-partition.json"),
            record("artifacts/pilot/link-root0-secondary0-tertiary-partition.json"),
            record(manifest_relative),
        ],
        "theorem_chain_status": "domain and partition reduction audited; exhaustive orbit classification remains open until all 47 canonical frontier nodes close or a new orbit is found",
        "claim_limit": "This certifies the exact classification domain and its disjoint canonical partition, not exhaustion of that partition.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="artifacts/portfolio/frontier-manifest-26of47-seven-orbit-snapshot.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = audit(args.manifest)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
