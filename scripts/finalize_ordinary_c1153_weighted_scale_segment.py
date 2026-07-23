#!/usr/bin/env python3
"""Emit the immutable review gate for one independently audited weighted segment."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/run_ordinary_c1153_weighted_scale_segment_001.py"
spec = importlib.util.spec_from_file_location("weighted_scale_current", RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(runner)
base = runner.base
AUDIT = runner.TARGET / "independent-audit.json"
REVIEW = runner.TARGET / "review-gate.json"


def finalize() -> dict:
    selected = runner.selected_segment()
    audit = json.loads(AUDIT.read_text())
    if audit["status"] != "VALID" or audit["completed"] != selected["case_count"]:
        raise ValueError("segment is not completely and independently audited")
    if audit["protocol_sha256"] != base.sha(runner.PROTOCOL):
        raise ValueError("audit protocol binding mismatch")
    next_number = runner.SEGMENT_NUMBER + 1
    manifest = json.loads(runner.MANIFEST.read_text())
    remaining = [row for row in manifest["segments"] if row["segment_id"] == f"weighted-scale-{next_number:03d}"]
    if audit["continuation_gate_passed"] and remaining:
        next_action = {
            "name": remaining[0]["segment_id"],
            "case_count": remaining[0]["case_count"],
            "fixed_lp_cap_seconds": 1,
            "parallelism": 1,
            "scope": f"Run only frozen segment {next_number:03d}, independently audit every certificate, and do not run a later segment in that tranche.",
        }
        status = f"AUDITED_SEGMENT_COMPLETE_SEGMENT_{next_number:03d}_AUTHORIZED"
    elif audit["continuation_gate_passed"]:
        next_action = {
            "name": "weighted-scale-complete-aggregation",
            "scope": "Independently aggregate the full 4,402-cube paired partition from exact child receipts; do not infer ancestor closure from summary counts.",
        }
        status = "AUDITED_WEIGHTED_SCALE_COMPLETE_AGGREGATION_AUTHORIZED"
    else:
        next_action = {
            "name": "weighted-scale-failure-stratum-review",
            "scope": "Diagnose the exact failed continuation predicate and build one sound discriminator; do not raise the LP cap or run another segment.",
        }
        status = "AUDITED_SEGMENT_COMPLETE_CONTINUATION_HELD"
    review = {
        "schema_version": 2,
        "status": status,
        "bindings": {
            "protocol_sha256": base.sha(runner.PROTOCOL),
            "assignment_sha256": base.sha(runner.ASSIGNMENT),
            "index_sha256": base.sha(runner.INDEX),
            "summary_sha256": base.sha(runner.SUMMARY),
            "independent_audit_sha256": base.sha(AUDIT),
        },
        "observed": {
            "completed": audit["completed"],
            "independently_checked_weighted_obstructions": audit["independently_checked_weighted_obstructions"],
            "open_no_certificate": audit["open_no_certificate_count"],
            "sat": audit["sat_count"],
            "median_lp_runtime_seconds": audit["median_runtime_seconds"],
            "minimum_arithmetic_margin": audit["minimum_arithmetic_margin"],
            "maximum_arithmetic_margin": audit["maximum_arithmetic_margin"],
            "projected_complete_bytes_with_10pct_safety": audit["projected_complete_4402_bytes_with_10pct_safety"],
        },
        "single_next_action": next_action,
        "claim_limit": "Only exact audited cubes close. Aggregate ancestors exclusively from complete child-by-child receipts.",
    }
    base.write_immutable(REVIEW, base.compact_json(review))
    return review


if __name__ == "__main__":
    print(json.dumps(finalize(), indent=2, sort_keys=True))
