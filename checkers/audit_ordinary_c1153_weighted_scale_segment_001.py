#!/usr/bin/env python3
"""Independent exact-domain and arithmetic audit of weighted segment 001."""

from __future__ import annotations

import gzip
import importlib.util
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/run_ordinary_c1153_weighted_scale_segment_001.py"
spec = importlib.util.spec_from_file_location("weighted_scale_001", RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(runner)
base = runner.base
checker_spec = importlib.util.spec_from_file_location(
    "weighted_audit_base",
    ROOT / "checkers/audit_ordinary_c1153_weighted_scale_segment.py",
)
checker = importlib.util.module_from_spec(checker_spec)
assert checker_spec.loader
checker_spec.loader.exec_module(checker)
TARGET = runner.TARGET
OUTPUT = TARGET / "independent-audit.json"


def audit() -> dict:
    selected = runner.selected_segment()
    jobs = selected["cases"]
    protocol = json.loads(runner.PROTOCOL.read_text())
    assignment = json.loads(runner.ASSIGNMENT.read_text())
    summary = json.loads(runner.SUMMARY.read_text())
    with gzip.open(runner.INDEX, "rb") as stream:
        index = json.loads(stream.read())
    if protocol["case_ids_sha256"] != selected["case_ids_sha256"] or protocol["case_count"] != 256:
        raise ValueError("protocol membership mismatch")
    if assignment["cloud"]["case_ids_sha256"] != selected["case_ids_sha256"] or assignment["local"]["case_count"] != 0:
        raise ValueError("host assignment mismatch")
    if summary["completed"] != 256 or summary["index_sha256"] != base.sha(runner.INDEX):
        raise ValueError("summary completion binding mismatch")
    if len(index["rows"]) != 256 or [row["case_id"] for row in index["rows"]] != [row["case_id"] for row in jobs]:
        raise ValueError("index membership/order mismatch")
    source = json.loads(base.SOURCE.read_text())
    cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = base.reconstruct_hierarchy()
    certified, margins, runtimes = 0, [], []
    for row_index, (index_row, job) in enumerate(zip(index["rows"], jobs)):
        receipt_path = runner.RECEIPTS / f"{row_index:03d}.json"
        if index_row["row"] != row_index or index_row["receipt_sha256"] != base.sha(receipt_path):
            raise ValueError(f"{job['case_id']}: receipt index binding mismatch")
        receipt = json.loads(receipt_path.read_text())
        if receipt["case_id"] != job["case_id"] or receipt["case_object_sha256"] != base.object_sha(job):
            raise ValueError(f"{job['case_id']}: case binding mismatch")
        if receipt["protocol_sha256"] != base.sha(runner.PROTOCOL):
            raise ValueError(f"{job['case_id']}: protocol binding mismatch")
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if receipt["parent_cnf_sha256"] != base.sha_bytes(parent_raw):
            raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
        domain = base.residual_domain(job, case, parent_raw)
        domain_sha = base.object_sha({
            "fixed": domain["fixed"], "forbidden": domain["forbidden"],
            "available": domain["available"], "uncovered": domain["uncovered"],
            "remaining_slots": domain["remaining_slots"], "units": domain["units"],
        })
        if receipt["domain_sha256"] != domain_sha:
            raise ValueError(f"{job['case_id']}: exact residual-domain mismatch")
        runtimes.append(receipt["continuous_lp"]["elapsed_seconds"])
        reference = receipt["certificate"]
        if reference is None:
            if receipt["status"] != "OPEN_NO_CERTIFICATE" or index_row["certificate_sha256"] is not None:
                raise ValueError(f"{job['case_id']}: open status mismatch")
            continue
        certificate_path = ROOT / reference["path"]
        compressed = certificate_path.read_bytes()
        if base.sha_bytes(compressed) != reference["sha256"] or index_row["certificate_sha256"] != reference["sha256"]:
            raise ValueError(f"{job['case_id']}: certificate binding mismatch")
        raw = gzip.decompress(compressed)
        if base.sha_bytes(raw) != reference["uncompressed_sha256"]:
            raise ValueError(f"{job['case_id']}: certificate content mismatch")
        margin = checker.check_certificate(
            raw,
            [tuple(triple) for triple in domain["uncovered"]],
            domain["available"],
            domain["remaining_slots"],
        )
        if abs(margin - receipt["margin_over_remaining_slots"]) > 1e-12:
            raise ValueError(f"{job['case_id']}: arithmetic margin mismatch")
        certified += 1
        margins.append(margin)
    median_runtime = statistics.median(runtimes)
    measured = sum(path.stat().st_size for path in [runner.PROTOCOL, runner.ASSIGNMENT, runner.INDEX, *runner.RECEIPTS.glob("*.json"), *runner.CERTIFICATES.glob("*.gz")])
    projection = __import__("math").ceil(measured * 4402 / 256 * 1.1)
    report = {
        "schema_version": 2, "status": "VALID", "segment_id": runner.SEGMENT_ID,
        "selected": 256, "completed": 256, "independently_checked_weighted_obstructions": certified,
        "open_no_certificate_count": 256 - certified, "sat_count": 0,
        "minimum_arithmetic_margin": min(margins) if margins else None,
        "maximum_arithmetic_margin": max(margins) if margins else None,
        "median_runtime_seconds": median_runtime,
        "measured_compact_v2_bytes": measured,
        "projected_complete_4402_bytes_with_10pct_safety": projection,
        "continuation_gate_passed": certified >= 240 and median_runtime < 0.5 and projection <= 12_102_474,
        "protocol_sha256": base.sha(runner.PROTOCOL), "summary_sha256": base.sha(runner.SUMMARY), "index_sha256": base.sha(runner.INDEX),
        "claim_limit": "Only these exact cubes close. No ancestor or campaign ledger changes without complete independent aggregation.",
    }
    base.write_immutable(OUTPUT, base.compact_json(report))
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
