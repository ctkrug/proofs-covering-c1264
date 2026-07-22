#!/usr/bin/env python3
"""Build the deterministic 100-candidate C(12,6,4) strategy tournament."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("docs/STRATEGY-TOURNAMENT-POLICY.json")
PORTFOLIO = Path("artifacts/portfolio/frontier-manifest-v1.json")
OUT = ROOT / "artifacts/tournament"


FAMILIES = {
    "sat_cardinality": {
        "route_kind": "negative",
        "variants": [
            "pairwise", "sequential-counter", "sorting-network", "cardinality-network", "bitwise",
            "ladder", "totalizer", "modulo-totalizer", "kmtotalizer", "native-cardinality"
        ],
        "gate": "truth-table boundary checks plus exact reconstruction of the non-cardinality CNF core"
    },
    "sat_cubing": {
        "route_kind": "negative",
        "variants": [
            "first-unassigned", "minimum-orbit", "maximum-occurrence", "balanced-polarity", "lookahead-propagation",
            "degree-deficit", "uncovered-quadruple", "proof-core-guided", "secondary-prefix", "tertiary-prefix"
        ],
        "gate": "independent proof that generated cubes are disjoint and exhaust the parent leaf"
    },
    "sat_search": {
        "route_kind": "negative_or_constructive",
        "variants": [
            "cadical-default", "stable-only", "focused-only", "phase-false", "phase-true",
            "random-phase", "near-cover-core-repair", "restart-aggressive", "restart-conservative", "proof-core-variable-order"
        ],
        "gate": "independent CNF reconstruction; direct validation of every witness; proof replay for any promoted UNSAT result"
    },
    "pseudo_boolean": {
        "route_kind": "negative",
        "variants": [
            "bdd", "sequential-weight-counter", "sorting-network", "binary-adder", "binary-merge",
            "generalized-totalizer", "modulo-totalizer", "global-polynomial-watchdog", "mixed-radix", "cutting-planes"
        ],
        "gate": "exhaustive small-instance equivalence plus reconstruction of every coverage and degree inequality"
    },
    "cp_sat": {
        "route_kind": "negative_or_constructive",
        "variants": [
            "fixed-block-order", "minimum-domain", "maximum-domain", "degree-first", "coverage-first",
            "conflict-first", "pseudo-cost", "deterministic-portfolio", "block-neighborhood-lns", "uncovered-quadruple-lns"
        ],
        "gate": "direct witness validation for feasible output and matched small-instance infeasibility cross-check"
    },
    "integer_programming": {
        "route_kind": "negative_or_constructive",
        "variants": [
            "plain-set-cover", "exact-degree-equalities", "orbit-representatives", "lex-symmetry-breaking", "row-generation",
            "cover-cut-separation", "clique-cuts", "degree-deficit-branching", "block-pair-branching", "proof-producing-cut-log"
        ],
        "gate": "coefficient-by-coefficient model audit and direct validation of every integer witness or checkable cut log"
    },
    "constructive_local_search": {
        "route_kind": "constructive",
        "variants": [
            "one-block-replacement", "two-block-swap", "three-block-ejection-chain", "uncovered-quadruple-repair", "degree-balanced-swap",
            "matching-preserving-swap", "pair-frequency-repair", "triple-frequency-repair", "tabu-block-replacement", "min-conflicts-block-replacement"
        ],
        "gate": "every candidate state has 40 distinct blocks, preserves declared forced constraints, and is checked directly for all 495 quadruples"
    },
    "constructive_metaheuristic": {
        "route_kind": "constructive",
        "variants": [
            "simulated-annealing", "parallel-tempering", "late-acceptance", "iterated-local-search", "variable-neighborhood-search",
            "genetic-block-set", "cross-entropy", "estimation-of-distribution", "large-neighborhood-repair", "beam-search-deficit"
        ],
        "gate": "deterministic seeded control plus independent direct validation of any 40-block output"
    },
    "symmetry_representation": {
        "route_kind": "reduction",
        "variants": [
            "fixed-perfect-matching", "point-link-orbits", "block-stabilizer-orbits", "incidence-graph-canonical", "lex-leader-blocks",
            "orderly-generation", "canonical-augmentation", "orbitopal-fixing", "double-lex-incidence", "nauty-canonical-cubes"
        ],
        "gate": "independent orbit/canonicalization implementation and exhaustive coverage check on a bounded parent"
    },
    "structural_reduction": {
        "route_kind": "reduction",
        "variants": [
            "point-degree-profile", "pair-frequency-profile", "triple-frequency-profile", "intersection-distribution", "matching-incidence-profile",
            "LP-dual-bound", "covering-density-bound", "dominance-elimination", "proof-core-signature", "meet-in-the-middle-half-cover"
        ],
        "gate": "independent derivation or exhaustive bounded counterexample search for the proposed reduction"
    }
}

IMPLEMENTED = {
    ("sat_cardinality", "sequential-counter"): "frozen_predecessor_in_progress",
    ("sat_cardinality", "kmtotalizer"): "frozen_predecessor_in_progress",
    ("sat_search", "cadical-default"): "prior_direct_pilot_unknown",
    ("sat_search", "near-cover-core-repair"): "initial_constructive_discriminator_complete",
    ("constructive_local_search", "uncovered-quadruple-repair"): "initial_constructive_discriminator_complete",
    ("symmetry_representation", "fixed-perfect-matching"): "validated_reduction_available",
    ("structural_reduction", "point-degree-profile"): "validated_reduction_available",
    ("structural_reduction", "pair-frequency-profile"): "validated_reduction_available",
}


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def file_binding(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}


def candidates() -> list[dict]:
    rows = []
    for family, definition in FAMILIES.items():
        for index, variant in enumerate(definition["variants"], 1):
            signature = {
                "family": family,
                "variant": variant,
                "route_kind": definition["route_kind"],
                "semantic_gate": definition["gate"]
            }
            method_id = f"{family}-{index:02d}"
            implemented = (family, variant) in IMPLEMENTED
            rows.append({
                "method_id": method_id,
                "family": family,
                "variant": variant,
                "route_kind": definition["route_kind"],
                "mechanism_fingerprint": canonical_hash(signature),
                "material_signature": signature,
                "success_certificate": (
                    "independently validated 40-block cover" if definition["route_kind"] == "constructive"
                    else "net-new reconstructed and replayed UNSAT leaf, or directly validated 40-block cover"
                ),
                "semantic_gate": definition["gate"],
                "implementation_status": "available" if implemented else "design_candidate",
                "validation_status": "passed" if implemented else "pending",
                "screen_status": IMPLEMENTED[(family, variant)] if implemented else "blocked_pending_semantic_gate",
                "screen_budget": {"units": 8, "search_seconds_per_unit": 5, "maximum_search_cpu_seconds": 40},
                "applicable_targets": "eight frozen leaves" if definition["route_kind"] == "negative" else
                    "eight fixed seeds plus any returned global witness" if definition["route_kind"] == "constructive" else
                    "bounded parent plus downstream leaves after coverage validation"
            })
    rows.sort(key=lambda row: row["method_id"])
    return rows


def stratified_sample(open_nodes: list[dict]) -> list[str]:
    secondary = [row for row in open_nodes if row["kind"] == "secondary"]
    tertiary = sorted((row for row in open_nodes if row["kind"] == "tertiary"), key=lambda row: row["tertiary_index"])
    chosen = []
    for root in (0, 1):
        group = sorted((row for row in secondary if row["root_index"] == root), key=lambda row: row["inherited_result_sha256"])
        chosen.extend(row["id"] for row in group[:2])
    for position in (0, len(tertiary) // 3, 2 * len(tertiary) // 3, len(tertiary) - 1):
        chosen.append(tertiary[position]["id"])
    if len(chosen) != 8 or len(set(chosen)) != 8:
        raise ValueError("failed to construct eight distinct stratified open leaves")
    return chosen


def build() -> tuple[dict, dict, dict]:
    portfolio = json.loads((ROOT / PORTFOLIO).read_text())
    methods = candidates()
    if len(methods) != 100 or len({row["mechanism_fingerprint"] for row in methods}) != 100:
        raise ValueError("candidate registry must contain 100 materially distinct signatures")
    open_nodes = [row for row in portfolio["nodes"] if row["final_coverage_status"] == "open"]
    sample = stratified_sample(open_nodes)
    registry = {
        "schema_version": 1,
        "problem_id": "covering-c1264",
        "policy": file_binding(POLICY),
        "portfolio_manifest": file_binding(PORTFOLIO),
        "candidate_count": 100,
        "family_count": len(FAMILIES),
        "candidates": methods
    }
    registry["registry_payload_sha256"] = canonical_hash(registry)

    screening = {
        "schema_version": 1,
        "stage": "semantic_gate_then_cheap_screen",
        "candidate_registry_sha256": registry["registry_payload_sha256"],
        "frozen_stratified_leaf_sample": sample,
        "constructive_seed_ids": [f"seed-{index:02d}" for index in range(8)],
        "search_seconds_per_unit": 5,
        "maximum_units_per_candidate": 8,
        "maximum_search_cpu_seconds_per_candidate": 40,
        "maximum_parallel_searches": 1,
        "admission_rule": "validation_status must be passed before any screen unit runs",
        "retention_rule": "retain unique validated coverage; zero coverage demotes only for the matched tested class unless the family-level gate supports broader elimination",
        "selection_rule": "successive halving: validate and screen one champion per family before expanding variants in a winning family",
        "frozen_predecessor_exception": "sequential-counter and kmtotalizer finish cardinality-encoding-20-leaf-20260722 unchanged"
    }
    screening["screening_payload_sha256"] = canonical_hash(screening)

    method_by_variant = {(row["family"], row["variant"]): row["method_id"] for row in methods}
    matrix_rows = []
    for node in portfolio["nodes"]:
        for outcome in node["outcomes"]:
            key = ("sat_cardinality", "sequential-counter" if outcome["method"] == "sequential" else outcome["method"])
            if key not in method_by_variant:
                continue
            matrix_rows.append({
                "target_id": node["id"], "method_id": method_by_variant[key],
                "status": outcome["status"], "cpu_seconds": outcome["cpu_seconds"],
                "proof_sha256": outcome.get("proof_sha256"), "source_run_id": outcome.get("run_id")
            })
    matrix = {
        "schema_version": 1,
        "problem_id": "covering-c1264",
        "candidate_registry_sha256": registry["registry_payload_sha256"],
        "frontier_definition_sha256": portfolio["frontier_definition_sha256"],
        "targets": ["global-40-block-witness"] + [row["id"] for row in portfolio["nodes"]],
        "cells": sorted(matrix_rows, key=lambda row: (row["target_id"], row["method_id"])),
        "covered_frontier_targets": sorted(row["id"] for row in portfolio["nodes"] if row["final_coverage_status"] != "open"),
        "global_witness_status": "open",
        "retained_methods": [{
            "method_id": method_by_variant[("sat_cardinality", "sequential-counter")],
            "basis": "three net-new independently replayed closures in inherited tranche"
        }],
        "protected_incomplete_methods": [{
            "method_id": method_by_variant[("sat_cardinality", "kmtotalizer")],
            "basis": "must finish frozen predecessor protocol before stop/retain decision"
        }],
        "constructive_measurements": [
            {
                "method_id": method_by_variant[("constructive_local_search", "uncovered-quadruple-repair")],
                "result": file_binding(Path("artifacts/constructive/repair-seed126440-10s/result.json")),
                "outcome": "no witness; best candidate has seven uncovered quadruples"
            },
            {
                "method_id": method_by_variant[("sat_search", "near-cover-core-repair")],
                "result": file_binding(Path("artifacts/constructive/sat-repair-seed126441-4x10s/result.json")),
                "outcome": "no witness; cores 32, 28, and 24 were solver-reported UNSAT without replayed proofs; core 20 timed out; allocation signal only"
            },
            {
                "method_id": method_by_variant[("constructive_local_search", "uncovered-quadruple-repair")],
                "result": file_binding(Path("artifacts/constructive/repair-seed126442-30s/result.json")),
                "outcome": "no witness; improved to six uncovered quadruples with exact point degrees"
            },
            {
                "method_id": method_by_variant[("constructive_local_search", "uncovered-quadruple-repair")],
                "result": file_binding(Path("artifacts/constructive/repair-seed126443-30s/result.json")),
                "outcome": "no witness; best remained seven uncovered quadruples"
            },
            {
                "method_id": method_by_variant[("sat_search", "near-cover-core-repair")],
                "result": file_binding(Path("artifacts/constructive/sat-repair-seed126444-4x15s/result.json")),
                "outcome": "no witness; all four cores timed out; allocation signal only"
            }
        ]
    }
    matrix["matrix_payload_sha256"] = canonical_hash(matrix)
    return registry, screening, matrix


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    registry, screening, matrix = build()
    for name, value in (("candidate-registry.json", registry), ("screening-manifest.json", screening),
                        ("coverage-matrix.json", matrix)):
        (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"built {len(registry['candidates'])} candidates; sample={screening['frozen_stratified_leaf_sample']}")


if __name__ == "__main__":
    main()
