#!/usr/bin/env python3
"""Independent audit of shallow second-live weighted certificates."""

from __future__ import annotations

import hashlib
import itertools
import json
import statistics
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
SAMPLE = BASE / "discriminator-5s/protocol.json"
STRUCTURAL = BASE / "multi-deficit-propagation-gate-v1/manifest.json"
TARGET = BASE / "shallow-weighted-gate-v1"
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
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def expected_cases() -> list[dict[str, object]]:
    sample = json.loads(SAMPLE.read_text())
    closed = {row["leaf_id"] for row in json.loads(STRUCTURAL.read_text())["formulas"]}
    return [{
        **row,
        "case_id": row["leaf_id"],
        "cube_path": [],
        "formula_id": row["leaf_id"],
    } for row in sorted(sample["sample"], key=lambda item: item["leaf_id"]) if row["leaf_id"] not in closed]


def check_certificate(reference: dict[str, object], domain: dict[str, object]) -> float:
    path = ROOT / reference["path"]
    if sha(path) != reference["sha256"]:
        raise ValueError("certificate hash mismatch")
    cert = json.loads(path.read_text())
    denominator = cert["denominator"]
    slots = domain["remaining_slots"]
    if denominator <= 0 or cert["remaining_slots"] != slots:
        raise ValueError("certificate budget mismatch")
    uncovered = set(domain["uncovered"])
    weights: dict[tuple[int, ...], int] = {}
    for row in cert["weighted_triples"]:
        triple = tuple(row["triple"])
        numerator = row["numerator"]
        if triple not in uncovered or triple in weights or not isinstance(numerator, int) or numerator <= 0:
            raise ValueError("invalid weighted triple")
        weights[triple] = numerator
    total = sum(weights.values())
    if total != cert["total_numerator"] or total <= slots * denominator:
        raise ValueError("weighted lower bound does not exceed residual budget")
    loads = [
        sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
        for value in domain["available"]
    ]
    maximum = max(loads, default=0)
    if maximum != cert["maximum_eligible_block_load"] or maximum > denominator:
        raise ValueError("eligible block exceeds normalized unit load")
    return total / denominator - slots


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    summary = json.loads(SUMMARY.read_text())
    expected = expected_cases()
    if len(expected) != 36 or protocol["cases"] != expected:
        raise ValueError("36-case exact selection mismatch")
    if protocol["case_ids_sha256"] != object_sha([row["case_id"] for row in expected]):
        raise ValueError("case identity hash mismatch")
    for binding in protocol["bindings"].values():
        path = ROOT / binding["path"]
        if sha(path) != binding["sha256"]:
            raise ValueError(f"binding mismatch: {path}")
    if summary["protocol"]["sha256"] != sha(PROTOCOL) or summary["completed"] != 36:
        raise ValueError("summary binding/completion mismatch")
    outcomes = {row["case_id"]: row for row in summary["outcomes"]}
    jobs = {row["case_id"]: row for row in expected}
    if set(outcomes) != set(jobs):
        raise ValueError("outcome membership mismatch")
    target_cases = {row["id"]: row for row in json.loads(SOURCE.read_text())["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    certified = 0
    margins = []
    counts = Counter()
    for cid in sorted(jobs):
        job, result = jobs[cid], outcomes[cid]
        if any(result[key] != value for key, value in job.items()):
            raise ValueError(f"{cid}: immutable case field mismatch")
        case = target_cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != result["parent_cnf_sha256"]:
            raise ValueError(f"{cid}: parent reconstruction mismatch")
        domain = residual_domain(job, case, parent_raw)
        recorded = result["domain"]
        checks = {
            "fixed_sha256": object_sha(domain["fixed"]),
            "forbidden_sha256": object_sha(domain["forbidden"]),
            "available_sha256": object_sha(domain["available"]),
            "uncovered_sha256": object_sha([list(row) for row in domain["uncovered"]]),
            "unit_recipe_sha256": object_sha(domain["units"]),
            "remaining_slots": domain["remaining_slots"],
        }
        if any(recorded[key] != value for key, value in checks.items()):
            raise ValueError(f"{cid}: residual-domain mismatch")
        cert = result["weighted_certificate"]
        label = "OPEN"
        if cert is not None:
            margins.append(check_certificate(cert, domain))
            certified += 1
            label = "CERT"
        elif result["status"] != "OPEN_NO_CERTIFICATE":
            raise ValueError(f"{cid}: missing-certificate status mismatch")
        counts[f"{job['root_class']}|{job['sample_category']}|{label}"] += 1
    runtime = statistics.median(row["continuous_lp"]["elapsed_seconds"] for row in outcomes.values())
    gate = protocol["success_gate"]
    passed = certified >= gate["minimum_exact_certificates"] and runtime < gate["maximum_median_runtime_seconds"]
    report = {
        "schema_version": 1,
        "status": "VALID",
        "protocol_sha256": sha(PROTOCOL),
        "summary_sha256": sha(SUMMARY),
        "case_count": 36,
        "independently_checked_weighted_formulas": certified,
        "open_no_certificate_count": 36 - certified,
        "median_runtime_seconds": runtime,
        "minimum_margin": min(margins) if margins else None,
        "maximum_margin": max(margins) if margins else None,
        "counts_by_stratum": dict(sorted(counts.items())),
        "success_gate_passed": passed,
        "claim_limit": "Only the exact certified shallow formulas close; no target child or higher ancestor closes from this sample.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
