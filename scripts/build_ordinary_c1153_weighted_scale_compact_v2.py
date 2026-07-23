#!/usr/bin/env python3
"""Build a pointer-only compact-v2 package over immutable scale segment 000."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPACT = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1/multi-deficit-propagation-gate-v1/weighted-generalization-gate-v1/compact-package-v1"
SCALE_MANIFEST = COMPACT / "scale-manifest.json"
SEGMENT = COMPACT / "scale-segments/weighted-scale-000"
V1_PROTOCOL = SEGMENT / "protocol.json"
V1_INDEX = SEGMENT / "index.json.gz"
V1_REVIEW = SEGMENT / "review-gate.json"
TARGET = SEGMENT / "compact-v2"
PROTOCOL = TARGET / "protocol.json"
ASSIGNMENT = TARGET / "assignment.json"
RECEIPTS = TARGET / "receipts"
INDEX = TARGET / "index.json.gz"
SUMMARY = TARGET / "summary.json"
EXPECTED_PROJECTION = 12_102_474


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def compact_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def gzip_bytes(raw: bytes) -> bytes:
    return gzip.compress(raw, compresslevel=9, mtime=0)


def write_immutable(path: Path, raw: bytes) -> None:
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing to replace incompatible immutable artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def build() -> dict[str, object]:
    scale = json.loads(SCALE_MANIFEST.read_text())
    review = json.loads(V1_REVIEW.read_text())
    segment = next(row for row in scale["segments"] if row["segment_id"] == "weighted-scale-000")
    if segment["case_count"] != 256 or review["status"] != "AUDITED_SEGMENT_COMPLETE_CONTINUATION_HELD":
        raise ValueError("segment 000 is not at the audited storage review gate")
    if review["gate"]["segment_001_authorized"]:
        raise ValueError("segment 001 unexpectedly authorized")
    protocol = {
        "schema_version": 2,
        "status": "STORAGE_ONLY_REPACK_NOT_A_MATHEMATICAL_RESULT",
        "segment_id": "weighted-scale-000",
        "case_count": 256,
        "case_ids_sha256": segment["case_ids_sha256"],
        "bindings": {
            "scale_manifest_sha256": sha(SCALE_MANIFEST),
            "v1_protocol_sha256": sha(V1_PROTOCOL),
            "v1_index_sha256": sha(V1_INDEX),
            "v1_review_sha256": sha(V1_REVIEW),
        },
        "row_rule": "Row index is the zero-based position in frozen weighted-scale-000 cases; case metadata is never duplicated.",
        "certificate_rule": "Reuse the immutable v1 gzip certificate by content hash; do not duplicate certificate bytes.",
        "success_gate": {
            "exact_membership": 256,
            "required_binding_and_check_fraction": 1.0,
            "maximum_projected_complete_bytes_with_10pct_safety": EXPECTED_PROJECTION,
        },
        "claim_limit": "Representation only; all mathematical status remains bound to the independently checked v1 certificates.",
    }
    assignment = {
        "schema_version": 2,
        "segment_id": "weighted-scale-000",
        "case_ids_sha256": segment["case_ids_sha256"],
        "cloud_role": "COMPACT_V2_ARTIFACT_OWNER",
        "local_role": "INDEPENDENT_CHECK_AND_PUBLICATION_ONLY",
        "mathematical_compute_authorized": False,
    }
    write_immutable(PROTOCOL, compact_json(protocol))
    write_immutable(ASSIGNMENT, compact_json(assignment))
    with gzip.open(V1_INDEX, "rb") as stream:
        v1_index = json.loads(stream.read())
    v1_rows = {row["case_id"]: row for row in v1_index["rows"]}
    compact_rows = []
    for index, job in enumerate(segment["cases"]):
        case_id = job["case_id"]
        v1_row = v1_rows[case_id]
        v1_receipt_path = ROOT / v1_row["receipt_path"]
        v1_receipt = json.loads(v1_receipt_path.read_text())
        if v1_receipt["status"] != "WEIGHTED_OBSTRUCTION_PENDING_AUDIT":
            raise ValueError(f"{case_id}: v1 receipt is not a weighted obstruction")
        certificate = v1_receipt["certificate"]
        receipt = {
            "v": 2,
            "i": index,
            "id": case_id,
            "src": sha(v1_receipt_path),
            "cert": certificate["sha256"],
            "cert_raw": certificate["uncompressed_sha256"],
            "domain": object_sha(v1_receipt["domain"]),
            "runtime": v1_receipt["continuous_lp"]["elapsed_seconds"],
            "lower": v1_receipt["normalized_lower_bound"],
            "margin": v1_receipt["margin_over_remaining_slots"],
            "status": "WEIGHTED_OBSTRUCTION_PENDING_V2_AUDIT",
        }
        receipt_path = RECEIPTS / f"{index:03d}.json"
        write_immutable(receipt_path, compact_json(receipt))
        compact_rows.append([index, sha(receipt_path), certificate["sha256"]])
    write_immutable(INDEX, gzip_bytes(compact_json({
        "v": 2,
        "segment": "weighted-scale-000",
        "rows": compact_rows,
    })))
    certificate_bytes = sum(
        (ROOT / json.loads((ROOT / row["receipt_path"]).read_text())["certificate"]["path"]).stat().st_size
        for row in v1_index["rows"]
    )
    receipt_bytes = sum(path.stat().st_size for path in RECEIPTS.glob("*.json"))
    metadata_bytes = PROTOCOL.stat().st_size + ASSIGNMENT.stat().st_size + INDEX.stat().st_size
    measured = certificate_bytes + receipt_bytes + metadata_bytes
    projected = math.ceil(measured * 4402 / 256 * 1.1)
    summary = {
        "schema_version": 2,
        "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "case_count": 256,
        "certificate_bytes_reused_once": certificate_bytes,
        "compact_v2_receipt_bytes": receipt_bytes,
        "protocol_assignment_index_bytes": metadata_bytes,
        "measured_package_bytes": measured,
        "projected_complete_4402_bytes_with_10pct_safety": projected,
        "predeclared_projection_bytes_with_10pct_safety": EXPECTED_PROJECTION,
        "storage_gate_passed_provisionally": projected <= EXPECTED_PROJECTION,
        "protocol_sha256": sha(PROTOCOL),
        "index_sha256": sha(INDEX),
        "claim_limit": "No continuation decision until the independent compact-v2 audit passes.",
    }
    write_immutable(SUMMARY, compact_json(summary))
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
