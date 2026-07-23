#!/usr/bin/env python3
"""Freeze and run the 96-cube weighted-cover generalization gate."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
GATE = BASE / "multi-deficit-propagation-gate-v1"
STRUCTURAL = GATE / "manifest.json"
STRUCTURAL_AUDIT = GATE / "independent-audit.json"
PRIOR_PROTOCOL = GATE / "discriminator-5s/protocol.json"
PRIOR_AUDIT = GATE / "discriminator-5s/independent-audit.json"
ILP_GATE = GATE / "ilp-forced-gate-v1"
ILP_PROTOCOL = ILP_GATE / "protocol.json"
ILP_AUDIT = ILP_GATE / "independent-audit.json"
ILP_REVIEW = ILP_GATE / "review-gate.json"
TARGET = GATE / "weighted-generalization-gate-v1"
PROTOCOL = TARGET / "protocol.json"
ASSIGNMENT = TARGET / "hybrid-assignment.json"
RESULTS = TARGET / "results"
SUMMARY = TARGET / "summary.json"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
LP_SECONDS = 1
SAMPLES_PER_FORMULA = 8
DUAL_DENOMINATOR = 1_000_000
sys.path.insert(0, str(ROOT / "scripts"))
from run_ordinary_c1153_ilp_forced_gate import residual_domain, solve_cover  # noqa: E402
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def case_id(formula_id: str, path: list[int]) -> str:
    return f"{formula_id}-cube-{path[0]:03d}-{path[1]:03d}"


def quantile_indices(size: int, count: int) -> list[int]:
    if size < count:
        raise ValueError("not enough unmeasured cubes for quantile sample")
    indices = [round(index * (size - 1) / (count - 1)) for index in range(count)]
    if len(set(indices)) != count:
        raise ValueError("quantile selection is not unique")
    return indices


def select_cases(
    structural: dict[str, object],
    prior: dict[str, object],
    ilp: dict[str, object],
) -> list[dict[str, object]]:
    excluded_prior = {row["case_id"] for row in prior["sample"]}
    excluded_ilp = {row["case_id"] for row in ilp["cases"]}
    if not excluded_ilp <= excluded_prior:
        raise ValueError("six-case gate is not a subset of the prior frozen sample")
    excluded = excluded_prior | excluded_ilp
    selected = []
    for formula in sorted(structural["formulas"], key=lambda row: row["leaf_id"]):
        paths = sorted(
            row["path"] for row in formula["terminal_partition"]
            if row["kind"] == "frontier"
            and case_id(formula["leaf_id"], row["path"]) not in excluded
        )
        indices = quantile_indices(len(paths), SAMPLES_PER_FORMULA)
        for quantile, index in enumerate(indices):
            path = paths[index]
            selected.append({
                "branch_count_quantile": formula["branch_count_quantile"],
                "case_id": case_id(formula["leaf_id"], path),
                "cube_path": path,
                "formula_frontier_count": formula["frontier_count"],
                "formula_id": formula["leaf_id"],
                "quantile_index": quantile,
                "quantile_source_index": index,
                "quantile_source_size": len(paths),
                "rank_band": formula["rank_band"],
                "root_class": formula["root_class"],
                "sample_category": formula["sample_category"],
                "second_index": formula["second_index"],
                "stabilizer_tier": formula["stabilizer_tier"],
                "target_child_id": formula["target_child_id"],
            })
    if len(selected) != 96 or len({row["case_id"] for row in selected}) != 96:
        raise ValueError("weighted gate must contain exactly 96 unique cubes")
    if {row["case_id"] for row in selected} & excluded:
        raise ValueError("weighted gate reintroduces a prior measured cube")
    return selected


def freeze() -> dict[str, object]:
    structural = json.loads(STRUCTURAL.read_text())
    structural_audit = json.loads(STRUCTURAL_AUDIT.read_text())
    prior = json.loads(PRIOR_PROTOCOL.read_text())
    prior_audit = json.loads(PRIOR_AUDIT.read_text())
    ilp = json.loads(ILP_PROTOCOL.read_text())
    ilp_audit = json.loads(ILP_AUDIT.read_text())
    ilp_review = json.loads(ILP_REVIEW.read_text())
    if structural_audit["status"] != "VALID" or structural_audit["manifest_sha256"] != sha(STRUCTURAL):
        raise ValueError("structural manifest audit binding failed")
    if prior_audit["status"] != "VALID" or prior_audit["protocol_sha256"] != sha(PRIOR_PROTOCOL):
        raise ValueError("prior discriminator audit binding failed")
    if ilp_audit["status"] != "VALID" or ilp_audit["protocol_sha256"] != sha(ILP_PROTOCOL):
        raise ValueError("six-case arithmetic audit binding failed")
    if ilp_review["status"] != "AUDITED_GATE_COMPLETE":
        raise ValueError("six-case review gate is incomplete")
    cases = select_cases(structural, prior, ilp)
    protocol = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "bindings": {
            "structural_manifest": {"path": str(STRUCTURAL.relative_to(ROOT)), "sha256": sha(STRUCTURAL)},
            "structural_audit": {"path": str(STRUCTURAL_AUDIT.relative_to(ROOT)), "sha256": sha(STRUCTURAL_AUDIT)},
            "prior_protocol": {"path": str(PRIOR_PROTOCOL.relative_to(ROOT)), "sha256": sha(PRIOR_PROTOCOL)},
            "prior_audit": {"path": str(PRIOR_AUDIT.relative_to(ROOT)), "sha256": sha(PRIOR_AUDIT)},
            "ilp_protocol": {"path": str(ILP_PROTOCOL.relative_to(ROOT)), "sha256": sha(ILP_PROTOCOL)},
            "ilp_audit": {"path": str(ILP_AUDIT.relative_to(ROOT)), "sha256": sha(ILP_AUDIT)},
            "ilp_review": {"path": str(ILP_REVIEW.relative_to(ROOT)), "sha256": sha(ILP_REVIEW)},
        },
        "case_count": 96,
        "case_ids_sha256": object_sha([row["case_id"] for row in cases]),
        "cases": cases,
        "selection_rule": "For each of the 12 audited formulas, remove every cube in the prior 24-case sample (including the six later arithmetic closures), sort the remaining frontier paths lexicographically, and select rounded indices q*(n-1)/7 for q=0..7.",
        "fixed_budget": {
            "continuous_lp_seconds_per_case": LP_SECONDS,
            "parallelism": 1,
            "dual_denominator": DUAL_DENOMINATOR,
            "binary_probes": 0,
            "sat_solver_calls": 0,
        },
        "certificate_rule": "Round a nonnegative continuous set-cover dual downward to exact integer triple weights. Every eligible block must have weight at most the denominator, while total weight must exceed remaining_slots times the denominator.",
        "success_gate": {
            "minimum_certified": 90,
            "required_audit_fraction": 1.0,
            "maximum_median_runtime_seconds": 0.5,
            "maximum_projected_full_partition_bytes": 50_000_000,
        },
        "stop_rule": "Stop after exactly 96 cases or immediately on hash/reconstruction/checker/resource failure. Failed certificate attempts remain open; do not substitute a solver or raise caps.",
        "claim_limit": "Only independently checked exact sampled cubes close. No ancestor closes without a separate complete aggregation audit.",
    }
    assignment = {
        "schema_version": 1,
        "protocol_object_sha256": object_sha(protocol),
        "cloud": {"role": "EXCLUSIVE_CONTINUOUS_LP_AND_RECEIPT_OWNER", "case_ids": [row["case_id"] for row in cases]},
        "local": {"role": "FREEZE_CHECK_AND_PUBLICATION_ONLY", "case_ids": []},
        "exclusivity": "Every sampled cube is assigned exactly once to cloud; local may not run the LP tranche.",
    }
    TARGET.mkdir(parents=True, exist_ok=True)
    for path, payload in ((PROTOCOL, protocol), (ASSIGNMENT, assignment)):
        raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if path.exists() and path.read_text() != raw:
            raise ValueError(f"refusing to replace incompatible immutable {path}")
        path.write_text(raw)
    return protocol


def weighted_certificate(
    uncovered: list[tuple[int, ...]],
    available: list[int],
    slots: int,
    folder: Path,
) -> tuple[dict[str, object], dict[str, object] | None]:
    log = folder / "continuous-lp.log"
    report = solve_cover(uncovered, available, LP_SECONDS, log, continuous=True)
    if report["status"] != "Optimal" or not report["duals"]:
        return report, None
    positive = [(tuple(row["triple"]), max(0.0, row["value"])) for row in report["duals"]]
    max_float_load = max(
        (sum(weight for triple, weight in positive if triple in BLOCK_TRIPLES[value - 1]) for value in available),
        default=0.0,
    )
    scale = max(1.0, max_float_load)
    weights = {
        triple: math.floor((weight / scale) * DUAL_DENOMINATOR)
        for triple, weight in positive
        if weight > 0
    }
    weights = {triple: weight for triple, weight in weights.items() if weight > 0}
    total = sum(weights.values())
    loads = [
        sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
        for value in available
    ]
    maximum = max(loads, default=0)
    if total <= slots * DUAL_DENOMINATOR or maximum > DUAL_DENOMINATOR:
        return report, None
    certificate = {
        "schema_version": 1,
        "denominator": DUAL_DENOMINATOR,
        "remaining_slots": slots,
        "weighted_triples": [
            {"triple": list(triple), "numerator": numerator}
            for triple, numerator in sorted(weights.items())
        ],
        "total_numerator": total,
        "maximum_eligible_block_load": maximum,
        "eligible_block_count": len(available),
        "normalized_lower_bound": total / DUAL_DENOMINATOR,
        "margin_over_remaining_slots": (total / DUAL_DENOMINATOR) - slots,
        "interpretation": "Each eligible residual block has normalized weight at most one, but the weighted uncovered triples require more blocks than the remaining exact-cardinality budget.",
    }
    path = folder / "weighted-certificate.json"
    path.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n")
    return report, {"path": str(path.relative_to(ROOT)), "sha256": sha(path), **certificate}


def run_case(job: dict[str, object], case: dict[str, object], parent_raw: bytes) -> dict[str, object]:
    folder = RESULTS / job["case_id"]
    result_path = folder / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    folder.mkdir(parents=True, exist_ok=False)
    domain = residual_domain(job, case, parent_raw)
    uncovered = [tuple(triple) for triple in domain["uncovered"]]
    report, certificate = weighted_certificate(
        uncovered, domain["available"], domain["remaining_slots"], folder
    )
    result = {
        "schema_version": 1,
        **job,
        "protocol_sha256": sha(PROTOCOL),
        "parent_cnf_sha256": sha_bytes(parent_raw),
        "domain": {
            "fixed_count": len(domain["fixed"]),
            "forbidden_count": len(domain["forbidden"]),
            "available_count": len(domain["available"]),
            "uncovered_triple_count": len(uncovered),
            "remaining_slots": domain["remaining_slots"],
            "fixed_sha256": object_sha(domain["fixed"]),
            "forbidden_sha256": object_sha(domain["forbidden"]),
            "available_sha256": object_sha(domain["available"]),
            "uncovered_sha256": object_sha(domain["uncovered"]),
            "unit_recipe_sha256": object_sha(domain["units"]),
            "terminal_state_sha256": domain["state"]["terminal_state_sha256"],
        },
        "continuous_lp": report,
        "weighted_certificate": certificate,
        "status": "WEIGHTED_OBSTRUCTION_PENDING_AUDIT" if certificate else "OPEN_NO_CERTIFICATE",
        "claim_limit": "The arithmetic obstruction is provisional until independently reconstructed and checked.",
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def distribution(values: list[float | int]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {}
    at = lambda q: ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p50": at(0.5),
        "p90": at(0.9),
        "max": ordered[-1],
        "total": sum(ordered),
    }


def run() -> dict[str, object]:
    protocol = freeze()
    source = json.loads(SOURCE.read_text())
    cases = {case["id"]: case for case in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    outcomes = []
    for job in protocol["cases"]:
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
        outcomes.append(run_case(job, case, parent_raw))
    certified = [row for row in outcomes if row["weighted_certificate"] is not None]
    artifact_bytes = sum(
        path.stat().st_size for path in TARGET.rglob("*") if path.is_file()
    )
    elapsed = [row["continuous_lp"]["elapsed_seconds"] for row in outcomes]
    margins = [row["weighted_certificate"]["margin_over_remaining_slots"] for row in certified]
    summary = {
        "schema_version": 1,
        "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "protocol": {"path": str(PROTOCOL.relative_to(ROOT)), "sha256": sha(PROTOCOL)},
        "completed": len(outcomes),
        "weighted_certificate_count": len(certified),
        "open_no_certificate_count": len(outcomes) - len(certified),
        "sat_count": 0,
        "runtime_seconds": distribution(elapsed),
        "arithmetic_margin": distribution(margins),
        "artifact_bytes_before_summary": artifact_bytes,
        "projected_full_4402_bytes": math.ceil(artifact_bytes * 4402 / len(outcomes)),
        "outcomes": outcomes,
        "claim_limit": "No sampled certificate counts until the independent gate audit passes.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run()
    print(json.dumps({
        key: report[key]
        for key in (
            "status", "case_count", "completed", "weighted_certificate_count",
            "open_no_certificate_count", "sat_count", "runtime_seconds",
            "arithmetic_margin", "projected_full_4402_bytes",
        )
        if key in report
    }, indent=2, sort_keys=True))
