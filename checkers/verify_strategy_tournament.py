#!/usr/bin/env python3
"""Independent structural and hash audit for the strategy tournament."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOURNAMENT = ROOT / "artifacts/tournament"


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def verify() -> None:
    registry = json.loads((TOURNAMENT / "candidate-registry.json").read_text())
    screening = json.loads((TOURNAMENT / "screening-manifest.json").read_text())
    matrix = json.loads((TOURNAMENT / "coverage-matrix.json").read_text())
    plan = json.loads((TOURNAMENT / "assignment-plan.json").read_text())
    portfolio = json.loads((ROOT / registry["portfolio_manifest"]["path"]).read_text())
    policy_path = ROOT / registry["policy"]["path"]
    assert hashlib.sha256(policy_path.read_bytes()).hexdigest() == registry["policy"]["sha256"]
    assert hashlib.sha256((ROOT / registry["portfolio_manifest"]["path"]).read_bytes()).hexdigest() == registry["portfolio_manifest"]["sha256"]
    methods = registry["candidates"]
    assert len(methods) == registry["candidate_count"] == 100
    assert len({row["method_id"] for row in methods}) == 100
    assert len({row["mechanism_fingerprint"] for row in methods}) == 100
    family_counts = Counter(row["family"] for row in methods)
    assert len(family_counts) == 10 and set(family_counts.values()) == {10}
    for row in methods:
        assert row["variant"] and row["semantic_gate"] and row["success_certificate"]
        assert row["mechanism_fingerprint"] == canonical_hash(row["material_signature"])
        if row["validation_status"] != "passed":
            assert row["screen_status"] == "blocked_pending_semantic_gate"
    payload = dict(registry); recorded = payload.pop("registry_payload_sha256")
    assert canonical_hash(payload) == recorded
    assert screening["candidate_registry_sha256"] == recorded
    assert screening["maximum_parallel_searches"] == 1
    sample = screening["frozen_stratified_leaf_sample"]
    assert 6 <= len(sample) <= 12 and len(sample) == len(set(sample))
    open_ids = {row["id"] for row in portfolio["nodes"] if row["final_coverage_status"] == "open"}
    assert set(sample) <= open_ids
    kinds = {row["id"]: row["kind"] for row in portfolio["nodes"]}
    assert Counter(kinds[item] for item in sample) == {"secondary": 4, "tertiary": 4}
    screen_payload = dict(screening); screen_hash = screen_payload.pop("screening_payload_sha256")
    assert canonical_hash(screen_payload) == screen_hash
    assert matrix["candidate_registry_sha256"] == recorded
    assert matrix["frontier_definition_sha256"] == portfolio["frontier_definition_sha256"]
    assert len(matrix["targets"]) == 48 and matrix["targets"][0] == "global-40-block-witness"
    method_ids = {row["method_id"] for row in methods}
    target_ids = set(matrix["targets"])
    assert all(row["method_id"] in method_ids and row["target_id"] in target_ids for row in matrix["cells"])
    assert matrix["covered_frontier_targets"] == sorted(row["id"] for row in portfolio["nodes"] if row["final_coverage_status"] != "open")
    matrix_payload = dict(matrix); matrix_hash = matrix_payload.pop("matrix_payload_sha256")
    assert canonical_hash(matrix_payload) == matrix_hash
    assert plan["candidate_registry_sha256"] == recorded
    assert plan["screening_manifest_sha256"] == screen_hash
    assert plan["coverage_matrix_sha256"] == matrix_hash
    assert plan["maximum_parallel_searches"] == 1 and len(plan["active_searches"]) <= 1
    assert plan["separate_local_workstation_constructive_searches"] == 2
    assert len(plan["family_champions"]) == 10 and len(set(plan["family_champions"].values())) == 10
    assert 1 <= len(plan["next_semantic_validation_queue"]) < 10
    assert len(plan["next_semantic_validation_queue"]) + len(plan["parked_family_variant_expansion_queue"]) == sum(
        row["validation_status"] != "passed" for row in methods
    )
    assert "constructive_local_search-04" in plan["admitted_screen_methods"]
    assert len(plan["open_leaf_assignments"]) == portfolio["counts"]["open"]
    assert all(1 <= len(row["shortlist"]) <= 3 for row in plan["open_leaf_assignments"])
    plan_payload = dict(plan); plan_hash = plan_payload.pop("plan_payload_sha256")
    assert canonical_hash(plan_payload) == plan_hash
    assert len(matrix["constructive_measurements"]) == 9
    for measurement in matrix["constructive_measurements"]:
        bound = ROOT / measurement["result"]["path"]
        assert hashlib.sha256(bound.read_bytes()).hexdigest() == measurement["result"]["sha256"]
    print(f"PASS: 100 distinct candidates; 10 family champions; {len(sample)}-leaf screen; {len(matrix['covered_frontier_targets'])}/47 certified coverage; split-host plan")


if __name__ == "__main__":
    verify()
