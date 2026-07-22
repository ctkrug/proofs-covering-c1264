#!/usr/bin/env python3
"""Produce the next hardware-safe tournament validation, screening, and leaf-assignment plan."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOURNAMENT = ROOT / "artifacts/tournament"
PORTFOLIO = ROOT / "artifacts/portfolio/frontier-manifest-v1.json"


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def build_plan() -> dict:
    registry = json.loads((TOURNAMENT / "candidate-registry.json").read_text())
    screening = json.loads((TOURNAMENT / "screening-manifest.json").read_text())
    matrix = json.loads((TOURNAMENT / "coverage-matrix.json").read_text())
    portfolio = json.loads(PORTFOLIO.read_text())
    methods = {row["method_id"]: row for row in registry["candidates"]}
    observations = defaultdict(list)
    for cell in matrix["cells"]:
        observations[cell["method_id"]].append(cell)

    scores = []
    for method_id, method in methods.items():
        cells = observations[method_id]
        certified = {row["target_id"] for row in cells if row["status"] in {"unsat_certified", "sat_validated"}}
        cpu = sum(float(row.get("cpu_seconds") or 0) for row in cells)
        retained = any(row["method_id"] == method_id for row in matrix["retained_methods"])
        protected = any(row["method_id"] == method_id for row in matrix["protected_incomplete_methods"])
        scores.append({
            "method_id": method_id,
            "family": method["family"],
            "validated_targets": sorted(certified),
            "validated_target_count": len(certified),
            "observed_cpu_seconds": round(cpu, 6),
            "closures_per_cpu_hour": round(len(certified) / (cpu / 3600), 6) if cpu and certified else 0.0,
            "decision": "retain" if retained else "finish_frozen_protocol" if protected else
                "semantic_gate" if method["validation_status"] != "passed" else "screen"
        })

    # Round-robin families prevents one easy-to-implement family from monopolizing validation.
    pending_by_family = defaultdict(list)
    for row in registry["candidates"]:
        if row["validation_status"] != "passed":
            pending_by_family[row["family"]].append(row["method_id"])
    validation_queue = []
    for index in range(max(map(len, pending_by_family.values()), default=0)):
        for family in sorted(pending_by_family):
            if index < len(pending_by_family[family]):
                validation_queue.append(pending_by_family[family][index])

    open_nodes = [row for row in portfolio["nodes"] if row["final_coverage_status"] == "open"]
    retained_ids = [row["method_id"] for row in matrix["retained_methods"]]
    protected_ids = [row["method_id"] for row in matrix["protected_incomplete_methods"]]
    eligible_now = retained_ids + [item for item in protected_ids if item not in retained_ids]
    assignments = []
    for node in open_nodes:
        assignments.append({
            "target_id": node["id"],
            "structural_class": f"{node['kind']}:root-{node['root_index']}",
            "shortlist": eligible_now[:3],
            "basis": "finish frozen predecessor and retain inherited net-new winner; recompute after its complete 20-leaf evidence"
        })
    plan = {
        "schema_version": 1,
        "stage": "finish_frozen_predecessor",
        "candidate_registry_sha256": registry["registry_payload_sha256"],
        "screening_manifest_sha256": screening["screening_payload_sha256"],
        "coverage_matrix_sha256": matrix["matrix_payload_sha256"],
        "maximum_parallel_searches": screening["maximum_parallel_searches"],
        "active_searches": [{
            "run_id": "cardinality-encoding-20-leaf-20260722",
            "instruction": "continue unchanged from checkpoint; do not launch tournament screens concurrently"
        }],
        "next_semantic_validation_queue": validation_queue,
        "admitted_screen_methods": [],
        "method_scores": scores,
        "open_leaf_assignments": assignments,
        "global_constructive_assignment": {
            "status": "active_design_route",
            "next_gate": "validate the first forced-matching exact-degree constructive implementation before its eight fixed-seed screen"
        },
        "recompute_when": "frozen predecessor completes, a semantic gate changes, or a new independently validated matrix cell is recorded"
    }
    plan["plan_payload_sha256"] = canonical_hash(plan)
    return plan


def main() -> None:
    plan = build_plan()
    path = TOURNAMENT / "assignment-plan.json"
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(f"planned {len(plan['open_leaf_assignments'])} open leaves; validation queue={len(plan['next_semantic_validation_queue'])}; parallel={plan['maximum_parallel_searches']}")


if __name__ == "__main__":
    main()
