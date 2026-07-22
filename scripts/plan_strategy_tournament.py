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
FAMILY_CHAMPIONS = {
    "sat_cardinality": "sat_cardinality-02",
    "sat_cubing": "sat_cubing-02",
    "sat_search": "sat_search-07",
    "pseudo_boolean": "pseudo_boolean-01",
    "cp_sat": "cp_sat-10",
    "integer_programming": "integer_programming-02",
    "constructive_local_search": "constructive_local_search-04",
    "constructive_metaheuristic": "constructive_metaheuristic-09",
    "symmetry_representation": "symmetry_representation-01",
    "structural_reduction": "structural_reduction-02",
}


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

    # Successive halving: validate one champion per family first. Variants in a
    # family remain parked until its champion earns a reason to expand.
    validation_queue = [
        method_id for family, method_id in sorted(FAMILY_CHAMPIONS.items())
        if methods[method_id]["validation_status"] != "passed"
    ]
    champion_ids = set(FAMILY_CHAMPIONS.values())
    expansion_queue = [
        row["method_id"] for row in registry["candidates"]
        if row["validation_status"] != "passed" and row["method_id"] not in champion_ids
    ]

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
        "stage": "finish_frozen_predecessor_then_rebuild_for_expanded_link_catalog",
        "candidate_registry_sha256": registry["registry_payload_sha256"],
        "screening_manifest_sha256": screening["screening_payload_sha256"],
        "coverage_matrix_sha256": matrix["matrix_payload_sha256"],
        "maximum_parallel_searches": screening["maximum_parallel_searches"],
        "separate_local_workstation_constructive_searches": 2,
        "active_searches": [{
            "run_id": "cardinality-encoding-20-leaf-20260722",
            "instruction": "continue unchanged on the live host; do not launch other live-host tournament screens concurrently"
        }],
        "post_predecessor_sequential_sweep": {
            "run_id": "sequential-open-frontier-44-20260722",
            "status": "superseded_before_launch",
            "method": "sequential",
            "target_count": 44,
            "seconds_per_target": 60,
            "excluded_preserved_certificates": ["s-r0-6", "s-r1-5", "s-r1-8"],
            "instruction": "do not launch: s-r1-3 exposed a fifth link orbit; rebuild and audit the catalogue, blocker, frontier bindings, and replacement sweep first"
        },
        "expanded_catalog_gate": {
            "validated_orbit_count": 5,
            "new_orbit_canonical_sha256": "b470049c5444b5f9bdd253d6e096e42e52e42c3512e545b43a4ad8f9346bb49c",
            "new_orbit_residual_status": "UNSAT_REPLAY_VERIFIED",
            "required_before_scale": "ingest all benchmark discoveries, independently audit a versioned expanded blocker, recompute frontier bindings, and build a replacement sweep manifest"
        },
        "hard_tail_policy": {
            "profile": "derive structural classes only for nodes still open after the short-cap sweep",
            "allocation": "assign alternative encodings, cubing, PB/CP-SAT, ILP, or longer method-specific budgets by survivor class",
            "prohibition": "do not apply a uniform timeout increase to every survivor"
        },
        "next_semantic_validation_queue": validation_queue,
        "parked_family_variant_expansion_queue": expansion_queue,
        "family_champions": FAMILY_CHAMPIONS,
        "admitted_screen_methods": sorted(
            method_id for method_id in champion_ids if methods[method_id]["validation_status"] == "passed"
        ),
        "method_scores": scores,
        "open_leaf_assignments": assignments,
        "global_constructive_assignment": {
            "status": "active_measured_route",
            "initial_signal": "one-block repair improved to six uncovered quadruples with exact point degrees; four degree-preserving two-block tranches found no improvement, including two barrier-crossing runs with 35,000 accepted trades; exact-repair follow-up produced only UNKNOWN results, while earlier local CORE_UNSAT statuses remain unreplayed allocation signals",
            "next_gate": "demote exact-degree two-block repair for this basin; validate a larger neighborhood that temporarily permits degree slack or repairs at least three blocks before spending a longer tranche"
        },
        "recompute_when": "frozen predecessor completes, the expanded catalogue/frontier is independently audited, survivor classes change, a semantic gate changes, or a new independently validated matrix cell is recorded"
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
