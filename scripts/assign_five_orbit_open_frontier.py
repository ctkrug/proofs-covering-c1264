#!/usr/bin/env python3
"""Assign the audited five-orbit open frontier without rerunning settled work."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from build_certificate_portfolio import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("artifacts/portfolio/frontier-manifest-v1.json")
CHECKPOINT = Path("artifacts/cardinality-encoding-benchmark/cardinality-encoding-20-leaf-20260722/checkpoint.json")
OUTPUT = Path("artifacts/portfolio/five-orbit-dynamic-assignment.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def assign() -> tuple[dict, dict]:
    manifest = json.loads((ROOT / MANIFEST).read_text())
    checkpoint = json.loads((ROOT / CHECKPOINT).read_text())
    sequential = {row["leaf_id"]: row for row in checkpoint["results"] if row["encoding"] == "sequential"}
    assignments = []
    for node in manifest["nodes"]:
        if node["final_coverage_status"] != "open":
            continue
        methods = node["assigned_methods"]
        measured = sequential.get(node["id"])
        if measured is None:
            append_once(methods, "sequential")
            hard_class = "unmeasured_five_orbit_frontier"
            rationale = "default cheap harvester at the frozen short cap"
        elif measured["status"] == "SAT_NEW_ORBIT":
            append_once(methods, "alternative_cubing")
            append_once(methods, "forced_matching_exact_degree_40_block_witness")
            hard_class = "fifth_orbit_structural_constructive"
            rationale = "new link orbit and replayed residual obstruction merit structural branching and direct witness work"
        else:
            append_once(methods, "alternative_cubing")
            append_once(methods, "pb_cp_sat")
            hard_class = "sequential_short_cap_survivor"
            rationale = "do not repeat the same short sequential run; diversify formulation and branching"
        assignments.append({
            "node_id": node["id"],
            "structural_class": hard_class,
            "next_methods": methods[2:] if node["id"] in sequential else methods,
            "rationale": rationale,
        })
    assert len(assignments) == manifest["counts"]["open"]
    plan = {
        "schema_version": 1,
        "status": "assigned",
        "active_blocker_sha256": manifest["active_link_blocker"]["sha256"],
        "open_nodes": len(assignments),
        "class_counts": {
            name: sum(row["structural_class"] == name for row in assignments)
            for name in sorted({row["structural_class"] for row in assignments})
        },
        "assignments": sorted(assignments, key=lambda row: row["node_id"]),
        "policy": {
            "kmtotalizer": "contained; zero unique closure in the completed frozen benchmark",
            "sequential": "default only for nodes not yet measured by sequential",
            "hard_tail": "diversify after a short-cap survivor; no symmetry reruns",
            "constructive": "s-r1-3 remains a first-class direct-witness and structural target",
        },
    }
    output = ROOT / OUTPUT
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    manifest["dynamic_assignment"] = {"path": str(OUTPUT), "sha256": sha(output)}
    manifest.pop("manifest_payload_sha256", None)
    manifest["manifest_payload_sha256"] = canonical_hash(manifest)
    return manifest, plan


def main() -> None:
    manifest, plan = assign()
    (ROOT / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"open_nodes": plan["open_nodes"], "class_counts": plan["class_counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
