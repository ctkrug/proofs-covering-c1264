#!/usr/bin/env python3
"""Independent audit of the 96-cube weighted-cover generalization gate."""

from __future__ import annotations

import hashlib
import itertools
import json
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
GATE = BASE / "multi-deficit-propagation-gate-v1"
STRUCTURAL = GATE / "manifest.json"
PRIOR_PROTOCOL = GATE / "discriminator-5s/protocol.json"
ILP_PROTOCOL = GATE / "ilp-forced-gate-v1/protocol.json"
TARGET = GATE / "weighted-generalization-gate-v1"
PROTOCOL = TARGET / "protocol.json"
SUMMARY = TARGET / "summary.json"
OUTPUT = TARGET / "independent-audit.json"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from audit_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def make_id(formula_id: str, path: list[int]) -> str:
    return f"{formula_id}-cube-{path[0]:03d}-{path[1]:03d}"


def expected_cases() -> list[dict[str, object]]:
    structural = json.loads(STRUCTURAL.read_text())
    prior = json.loads(PRIOR_PROTOCOL.read_text())
    ilp = json.loads(ILP_PROTOCOL.read_text())
    excluded = {row["case_id"] for row in prior["sample"]} | {row["case_id"] for row in ilp["cases"]}
    expected = []
    for formula in sorted(structural["formulas"], key=lambda row: row["leaf_id"]):
        paths = sorted(
            row["path"] for row in formula["terminal_partition"]
            if row["kind"] == "frontier" and make_id(formula["leaf_id"], row["path"]) not in excluded
        )
        if len(paths) < 8:
            raise ValueError("formula has fewer than eight unmeasured paths")
        indices = [round(index * (len(paths) - 1) / 7) for index in range(8)]
        if len(set(indices)) != 8:
            raise ValueError("independent quantile indices collide")
        for quantile, index in enumerate(indices):
            path = paths[index]
            expected.append({
                "branch_count_quantile": formula["branch_count_quantile"],
                "case_id": make_id(formula["leaf_id"], path),
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
    return expected


def check_certificate(
    reference: dict[str, object],
    uncovered: list[tuple[int, ...]],
    available: list[int],
    slots: int,
) -> float:
    path = ROOT / reference["path"]
    if sha(path) != reference["sha256"]:
        raise ValueError("certificate file hash mismatch")
    certificate = json.loads(path.read_text())
    denominator = certificate["denominator"]
    if denominator <= 0 or certificate["remaining_slots"] != slots:
        raise ValueError("certificate budget mismatch")
    uncovered_set = set(uncovered)
    weights: dict[tuple[int, ...], int] = {}
    for row in certificate["weighted_triples"]:
        triple = tuple(row["triple"])
        numerator = row["numerator"]
        if triple not in uncovered_set or triple in weights or not isinstance(numerator, int) or numerator <= 0:
            raise ValueError("invalid weighted triple")
        weights[triple] = numerator
    total = sum(weights.values())
    if total != certificate["total_numerator"] or total <= slots * denominator:
        raise ValueError("weighted total does not exceed residual block budget")
    loads = [
        sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
        for value in available
    ]
    maximum = max(loads, default=0)
    if maximum != certificate["maximum_eligible_block_load"] or maximum > denominator:
        raise ValueError("eligible block exceeds certified unit weight")
    lower = total / denominator
    if abs(lower - certificate["normalized_lower_bound"]) > 1e-12:
        raise ValueError("normalized lower bound mismatch")
    if abs((lower - slots) - certificate["margin_over_remaining_slots"]) > 1e-12:
        raise ValueError("arithmetic margin mismatch")
    return lower - slots


def audit() -> dict[str, object]:
    protocol = json.loads(PROTOCOL.read_text())
    summary = json.loads(SUMMARY.read_text())
    expected = expected_cases()
    if protocol["cases"] != expected or len(expected) != 96:
        raise ValueError("96-case selection mismatch")
    if protocol["case_ids_sha256"] != object_sha([row["case_id"] for row in expected]):
        raise ValueError("case ID binding mismatch")
    for name, binding in protocol["bindings"].items():
        path = ROOT / binding["path"]
        if sha(path) != binding["sha256"]:
            raise ValueError(f"binding mismatch: {name}")
    if summary["protocol"]["sha256"] != sha(PROTOCOL) or summary["completed"] != 96:
        raise ValueError("summary protocol/completion mismatch")
    jobs = {row["case_id"]: row for row in expected}
    outcomes = {row["case_id"]: row for row in summary["outcomes"]}
    if len(outcomes) != 96 or set(outcomes) != set(jobs):
        raise ValueError("outcome membership mismatch")
    source = json.loads(SOURCE.read_text())
    target_cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    certified = 0
    margins = []
    by_stratum: dict[str, dict[str, int]] = {}
    for case_id in sorted(jobs):
        job, result = jobs[case_id], outcomes[case_id]
        if any(result[key] != value for key, value in job.items()):
            raise ValueError(f"{case_id}: immutable case fields changed")
        case = target_cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != result["parent_cnf_sha256"]:
            raise ValueError(f"{case_id}: parent hash mismatch")
        domain = residual_domain(job, case, parent_raw)
        recorded = result["domain"]
        checks = {
            "fixed_sha256": object_sha(domain["fixed"]),
            "forbidden_sha256": object_sha(domain["forbidden"]),
            "available_sha256": object_sha(domain["available"]),
            "uncovered_sha256": object_sha([list(value) for value in domain["uncovered"]]),
            "unit_recipe_sha256": object_sha(domain["units"]),
            "terminal_state_sha256": domain["state_sha"],
        }
        if any(recorded[key] != value for key, value in checks.items()):
            raise ValueError(f"{case_id}: independently reconstructed domain mismatch")
        key = f"{job['root_class']}|{job['sample_category']}|{job['second_index']}"
        stratum = by_stratum.setdefault(key, {"selected": 0, "certified": 0, "open": 0})
        stratum["selected"] += 1
        certificate = result["weighted_certificate"]
        if certificate is None:
            stratum["open"] += 1
            if result["status"] != "OPEN_NO_CERTIFICATE":
                raise ValueError(f"{case_id}: missing-certificate status mismatch")
            continue
        margins.append(check_certificate(
            certificate,
            domain["uncovered"],
            domain["available"],
            domain["remaining_slots"],
        ))
        certified += 1
        stratum["certified"] += 1
    if summary["weighted_certificate_count"] != certified:
        raise ValueError("summary certificate count mismatch")
    runtime_p50 = statistics.median(
        row["continuous_lp"]["elapsed_seconds"] for row in outcomes.values()
    )
    gate = protocol["success_gate"]
    gate_passed = (
        certified >= gate["minimum_certified"]
        and runtime_p50 < gate["maximum_median_runtime_seconds"]
        and summary["projected_full_4402_bytes"] < gate["maximum_projected_full_partition_bytes"]
    )
    report = {
        "schema_version": 1,
        "status": "VALID",
        "protocol_sha256": sha(PROTOCOL),
        "summary_sha256": sha(SUMMARY),
        "case_count": 96,
        "independently_checked_weighted_obstructions": certified,
        "open_no_certificate_count": 96 - certified,
        "sat_count": 0,
        "minimum_arithmetic_margin": min(margins) if margins else None,
        "maximum_arithmetic_margin": max(margins) if margins else None,
        "median_runtime_seconds": runtime_p50,
        "projected_full_4402_bytes": summary["projected_full_4402_bytes"],
        "by_formula_stratum": dict(sorted(by_stratum.items())),
        "success_gate_passed": gate_passed,
        "claim_limit": "Only the independently checked sampled cubes are semantic arithmetic closures. No ancestor or campaign ledger changes.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
