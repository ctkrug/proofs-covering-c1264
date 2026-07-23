#!/usr/bin/env python3
"""Test exact weighted obstructions on unresolved shallow second-live formulas."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
SOURCE_AUDIT = BASE / "independent-audit.json"
SAMPLE = BASE / "discriminator-5s/protocol.json"
SAMPLE_AUDIT = BASE / "discriminator-5s/independent-audit.json"
STRUCTURAL = BASE / "multi-deficit-propagation-gate-v1/manifest.json"
AGGREGATION_AUDIT = BASE / "multi-deficit-propagation-gate-v1/weighted-complete-aggregation-v1/independent-audit.json"
TARGET = BASE / "shallow-weighted-gate-v1"
PROTOCOL = TARGET / "protocol.json"
ASSIGNMENT = TARGET / "hybrid-assignment.json"
RESULTS = TARGET / "results"
SUMMARY = TARGET / "summary.json"
LP_SECONDS = 1

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from run_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402
from run_ordinary_c1153_weighted_generalization_gate import weighted_certificate  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def write_immutable(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text() != raw:
            raise ValueError(f"refusing to replace incompatible artifact: {path}")
        return
    path.write_text(raw)


def expected_cases() -> list[dict[str, object]]:
    sample = json.loads(SAMPLE.read_text())
    structural = json.loads(STRUCTURAL.read_text())
    closed = {row["leaf_id"] for row in structural["formulas"]}
    cases = []
    for source in sorted(sample["sample"], key=lambda row: row["leaf_id"]):
        if source["leaf_id"] in closed:
            continue
        cases.append({
            **source,
            "case_id": source["leaf_id"],
            "cube_path": [],
            "formula_id": source["leaf_id"],
        })
    if len(cases) != 36 or len({row["case_id"] for row in cases}) != 36:
        raise ValueError("shallow gate must contain exactly the 36 unresolved sampled formulas")
    return cases


def freeze() -> dict[str, object]:
    source_audit = json.loads(SOURCE_AUDIT.read_text())
    sample_audit = json.loads(SAMPLE_AUDIT.read_text())
    aggregation_audit = json.loads(AGGREGATION_AUDIT.read_text())
    if source_audit["status"] != "VALID" or source_audit["manifest_sha256"] != sha(SOURCE):
        raise ValueError("second-live structural audit binding failed")
    if sample_audit["status"] != "VALID" or sample_audit["protocol_sha256"] != sha(SAMPLE):
        raise ValueError("48-case sample audit binding failed")
    if sample_audit["counts"] != {"FIXED_CAP_TIMEOUT": 48}:
        raise ValueError("source sample is not exactly 48 audited timeouts")
    if aggregation_audit["status"] != "VALID" or aggregation_audit["formulas_independently_aggregated_closed"] != 12:
        raise ValueError("12-formula aggregation audit is not complete")
    cases = expected_cases()
    protocol = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "bindings": {
            "second_live_manifest": {"path": str(SOURCE.relative_to(ROOT)), "sha256": sha(SOURCE)},
            "second_live_audit": {"path": str(SOURCE_AUDIT.relative_to(ROOT)), "sha256": sha(SOURCE_AUDIT)},
            "timeout_sample": {"path": str(SAMPLE.relative_to(ROOT)), "sha256": sha(SAMPLE)},
            "timeout_sample_audit": {"path": str(SAMPLE_AUDIT.relative_to(ROOT)), "sha256": sha(SAMPLE_AUDIT)},
            "closed_formula_manifest": {"path": str(STRUCTURAL.relative_to(ROOT)), "sha256": sha(STRUCTURAL)},
            "closed_formula_audit": {"path": str(AGGREGATION_AUDIT.relative_to(ROOT)), "sha256": sha(AGGREGATION_AUDIT)},
        },
        "case_count": len(cases),
        "case_ids_sha256": object_sha([row["case_id"] for row in cases]),
        "cases": cases,
        "selection_rule": "Take the exact frozen 48-case second-live timeout sample and exclude precisely the 12 formulas already closed by complete weighted child aggregation.",
        "hypothesis": "The set-cover LP already exceeds the residual exact-cardinality budget at the shallow second-live formula, so deeper multi-deficit branching is unnecessary for a useful fraction of formulas.",
        "success_certificate": "Exact nonnegative integer weights on uncovered triples: every eligible block has normalized load at most one and total weight exceeds the remaining block budget.",
        "fixed_budget": {
            "continuous_lp_seconds_per_case": LP_SECONDS,
            "parallelism": 1,
            "sat_solver_calls": 0,
            "binary_probes": 0,
        },
        "success_gate": {
            "minimum_exact_certificates": 24,
            "required_checker_fraction": 1.0,
            "maximum_median_runtime_seconds": 0.5,
        },
        "stop_rule": "Stop after exactly 36 cases or immediately on hash, reconstruction, checker, or resource failure.",
        "claim_limit": "Only exact sampled second-live formulas with independently checked certificates close.",
    }
    assignment = {
        "schema_version": 1,
        "protocol_object_sha256": object_sha(protocol),
        "cloud": {"role": "EXCLUSIVE_LP_AND_RECEIPT_OWNER", "case_ids": [row["case_id"] for row in cases]},
        "local": {"role": "INDEPENDENT_CHECK_AND_PUBLICATION_ONLY", "case_ids": []},
        "exclusivity": "Each formula is assigned once; no closed formula is reintroduced.",
    }
    write_immutable(PROTOCOL, protocol)
    write_immutable(ASSIGNMENT, assignment)
    return protocol


def run() -> dict[str, object]:
    protocol = freeze()
    source = json.loads(SOURCE.read_text())
    target_cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    outcomes = []
    for job in protocol["cases"]:
        result_path = RESULTS / job["case_id"] / "result.json"
        if result_path.exists():
            outcomes.append(json.loads(result_path.read_text()))
            continue
        case = target_cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
        domain = residual_domain(job, case, parent_raw)
        folder = result_path.parent
        folder.mkdir(parents=True, exist_ok=False)
        report, certificate = weighted_certificate(
            [tuple(row) for row in domain["uncovered"]],
            domain["available"],
            domain["remaining_slots"],
            folder,
        )
        result = {
            "schema_version": 1,
            **job,
            "protocol_sha256": sha(PROTOCOL),
            "parent_cnf_sha256": sha_bytes(parent_raw),
            "domain": {
                "fixed_sha256": object_sha(domain["fixed"]),
                "forbidden_sha256": object_sha(domain["forbidden"]),
                "available_sha256": object_sha(domain["available"]),
                "uncovered_sha256": object_sha(domain["uncovered"]),
                "unit_recipe_sha256": object_sha(domain["units"]),
                "remaining_slots": domain["remaining_slots"],
            },
            "continuous_lp": report,
            "weighted_certificate": certificate,
            "status": "WEIGHTED_OBSTRUCTION_PENDING_AUDIT" if certificate else "OPEN_NO_CERTIFICATE",
        }
        write_immutable(result_path, result)
        outcomes.append(result)
    certified = [row for row in outcomes if row["weighted_certificate"] is not None]
    runtimes = sorted(row["continuous_lp"]["elapsed_seconds"] for row in outcomes)
    margins = sorted(row["weighted_certificate"]["margin_over_remaining_slots"] for row in certified)
    by_stratum = Counter(
        f"{row['root_class']}|{row['sample_category']}|{'CERT' if row['weighted_certificate'] else 'OPEN'}"
        for row in outcomes
    )
    summary = {
        "schema_version": 1,
        "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "protocol": {"path": str(PROTOCOL.relative_to(ROOT)), "sha256": sha(PROTOCOL)},
        "completed": len(outcomes),
        "weighted_certificate_count": len(certified),
        "open_no_certificate_count": len(outcomes) - len(certified),
        "sat_count": 0,
        "median_runtime_seconds": statistics.median(runtimes),
        "minimum_margin": min(margins) if margins else None,
        "maximum_margin": max(margins) if margins else None,
        "counts_by_stratum": dict(sorted(by_stratum.items())),
        "outcomes": outcomes,
        "claim_limit": "No shallow formula closes until the independent domain and arithmetic checker passes.",
    }
    write_immutable(SUMMARY, summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run()
    print(json.dumps({key: report[key] for key in report if key in (
        "status", "case_count", "completed", "weighted_certificate_count",
        "open_no_certificate_count", "median_runtime_seconds",
        "minimum_margin", "maximum_margin", "counts_by_stratum",
    )}, indent=2, sort_keys=True))
