#!/usr/bin/env python3
"""Run only frozen weighted arithmetic scale segment 001 in compact-v2 form."""

from __future__ import annotations

import gzip
import importlib.util
import json
import math
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "scripts/run_ordinary_c1153_weighted_scale_segment.py"
spec = importlib.util.spec_from_file_location("weighted_scale_base", BASE_SCRIPT)
base = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(base)

SEGMENT_NUMBER = int(os.environ.get("WEIGHTED_SCALE_SEGMENT", "1"))
SEGMENT_ID = f"weighted-scale-{SEGMENT_NUMBER:03d}"
COMPACT = base.COMPACT
MANIFEST = base.SCALE_MANIFEST
AUDIT = base.SCALE_AUDIT
REVIEW = (
    COMPACT / "scale-segments/weighted-scale-000/compact-v2/review-gate.json"
    if SEGMENT_NUMBER == 1
    else COMPACT / f"scale-segments/weighted-scale-{SEGMENT_NUMBER - 1:03d}/review-gate.json"
)
TARGET = COMPACT / f"scale-segments/{SEGMENT_ID}"
PROTOCOL = TARGET / "protocol.json"
ASSIGNMENT = TARGET / "assignment.json"
CERTIFICATES = TARGET / "certificates"
RECEIPTS = TARGET / "receipts"
INDEX = TARGET / "index.json.gz"
SUMMARY = TARGET / "summary.json"


def selected_segment() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    audit = json.loads(AUDIT.read_text())
    review = json.loads(REVIEW.read_text())
    if audit["status"] != "VALID" or not audit["membership_exhaustive"] or not audit["segments_pairwise_disjoint"]:
        raise ValueError("scale audit is not valid")
    authorized_names = {SEGMENT_ID, f"weighted-scale-segment-{SEGMENT_NUMBER:03d}"}
    if review["single_next_action"]["name"] not in authorized_names:
        raise ValueError(f"previous review did not authorize {SEGMENT_ID}")
    audit_path = REVIEW.parent / "independent-audit.json"
    if base.sha(audit_path) != review["bindings"]["independent_audit_sha256"]:
        raise ValueError("previous review audit binding mismatch")
    rows = [row for row in manifest["segments"] if row["segment_id"] == SEGMENT_ID]
    if len(rows) != 1 or rows[0]["case_count"] <= 0:
        raise ValueError(f"frozen {SEGMENT_ID} membership mismatch")
    if rows[0]["case_ids_sha256"] != base.object_sha([row["case_id"] for row in rows[0]["cases"]]):
        raise ValueError("segment 001 case binding mismatch")
    return rows[0]


def freeze() -> dict:
    selected = selected_segment()
    protocol = {
        "schema_version": 2,
        "status": "AUTHORIZED_NOT_RUN",
        "segment_id": SEGMENT_ID,
        "case_count": selected["case_count"],
        "segment_row_index": SEGMENT_NUMBER,
        "case_ids_sha256": selected["case_ids_sha256"],
        "bindings": {
            "scale_manifest_sha256": base.sha(MANIFEST),
            "scale_audit_sha256": base.sha(AUDIT),
            "previous_review_sha256": base.sha(REVIEW),
        },
        "fixed_route": {
            "continuous_lp_seconds_per_case": 1,
            "parallelism": 1,
            "dual_denominator": base.DUAL_DENOMINATOR,
            "artifact_format": "compact-v2 pointer receipts and one deterministic gzip exact certificate per certified case",
            "sat_pb_solver_calls": 0,
        },
        "stop_rule": f"Stop after exactly {selected['case_count']} results or any audit/resource failure. No later segment is authorized by this protocol.",
    }
    assignment = {
        "schema_version": 2,
        "segment_id": SEGMENT_ID,
        "protocol_object_sha256": base.object_sha(protocol),
        "cloud": {"role": "EXCLUSIVE_CONTINUOUS_LP_AND_RECEIPT_OWNER", "segment_row_index": SEGMENT_NUMBER, "case_ids_sha256": selected["case_ids_sha256"]},
        "local": {"role": "INDEPENDENT_CHECK_AND_PUBLICATION_ONLY", "case_count": 0},
    }
    base.write_immutable(PROTOCOL, base.compact_json(protocol))
    base.write_immutable(ASSIGNMENT, base.compact_json(assignment))
    return protocol


def run() -> dict:
    protocol = freeze()
    jobs = selected_segment()["cases"]
    source = json.loads(base.SOURCE.read_text())
    cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = base.reconstruct_hierarchy()
    rows, runtimes, margins = [], [], []
    for row_index, job in enumerate(jobs):
        receipt_path = RECEIPTS / f"{row_index:03d}.json"
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        domain = base.residual_domain(job, case, parent_raw)
        lp, certificate = base.exact_certificate(
            [tuple(triple) for triple in domain["uncovered"]],
            domain["available"],
            domain["remaining_slots"],
        )
        certificate_reference = None
        if certificate is not None:
            raw = base.compact_json(certificate)
            compressed = base.gzip_bytes(raw)
            certificate_path = CERTIFICATES / f"{row_index:03d}.json.gz"
            base.write_immutable(certificate_path, compressed)
            certificate_reference = {
                "path": str(certificate_path.relative_to(ROOT)),
                "sha256": base.sha_bytes(compressed),
                "uncompressed_sha256": base.sha_bytes(raw),
                "bytes": len(compressed),
            }
            margins.append(certificate["margin_over_remaining_slots"])
        receipt = {
            "schema_version": 2,
            "segment_id": SEGMENT_ID,
            "segment_row_index": SEGMENT_NUMBER,
            "case_row_index": row_index,
            "case_id": job["case_id"],
            "case_object_sha256": base.object_sha(job),
            "protocol_sha256": base.sha(PROTOCOL),
            "parent_cnf_sha256": base.sha_bytes(parent_raw),
            "domain_sha256": base.object_sha({
                "fixed": domain["fixed"], "forbidden": domain["forbidden"],
                "available": domain["available"], "uncovered": domain["uncovered"],
                "remaining_slots": domain["remaining_slots"], "units": domain["units"],
            }),
            "continuous_lp": lp,
            "certificate": certificate_reference,
            "status": "WEIGHTED_OBSTRUCTION_PENDING_AUDIT" if certificate else "OPEN_NO_CERTIFICATE",
            "normalized_lower_bound": None if certificate is None else certificate["normalized_lower_bound"],
            "margin_over_remaining_slots": None if certificate is None else certificate["margin_over_remaining_slots"],
        }
        base.write_immutable(receipt_path, base.compact_json(receipt))
        runtimes.append(lp["elapsed_seconds"])
        rows.append({
            "row": row_index, "case_id": job["case_id"], "status": receipt["status"],
            "receipt_sha256": base.sha(receipt_path),
            "certificate_sha256": None if certificate_reference is None else certificate_reference["sha256"],
        })
    base.write_immutable(INDEX, base.gzip_bytes(base.compact_json({"schema_version": 2, "segment_id": SEGMENT_ID, "rows": rows})))
    artifacts = [PROTOCOL, ASSIGNMENT, INDEX, *RECEIPTS.glob("*.json"), *CERTIFICATES.glob("*.gz")]
    measured = sum(path.stat().st_size for path in artifacts)
    summary = {
        "schema_version": 2, "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT", "segment_id": SEGMENT_ID,
        "protocol_sha256": base.sha(PROTOCOL), "index_sha256": base.sha(INDEX),
        "completed": len(rows), "weighted_certificate_count": len(margins),
        "open_no_certificate_count": len(rows) - len(margins), "sat_count": 0,
        "runtime_seconds": base.distribution(runtimes), "arithmetic_margin": base.distribution(margins),
        "compact_v2_bytes_before_summary": measured,
        "projected_complete_4402_bytes_with_10pct_safety": math.ceil(measured * 4402 / len(rows) * 1.1),
    }
    base.write_immutable(SUMMARY, base.compact_json(summary))
    return summary


if __name__ == "__main__":
    report = freeze() if len(sys.argv) > 1 and sys.argv[1] == "freeze" else run()
    print(json.dumps(report, indent=2, sort_keys=True))
