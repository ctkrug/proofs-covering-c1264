#!/usr/bin/env python3
"""Independently bind and audit segment-000 compact-v2 storage artifacts."""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
COMPACT = BASE / "multi-deficit-propagation-gate-v1/weighted-generalization-gate-v1/compact-package-v1"
SCALE_MANIFEST = COMPACT / "scale-manifest.json"
SEGMENT = COMPACT / "scale-segments/weighted-scale-000"
V1_INDEX = SEGMENT / "index.json.gz"
V1_REVIEW = SEGMENT / "review-gate.json"
TARGET = SEGMENT / "compact-v2"
PROTOCOL = TARGET / "protocol.json"
ASSIGNMENT = TARGET / "assignment.json"
INDEX = TARGET / "index.json.gz"
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


def compact_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def write_immutable(path: Path, raw: bytes) -> None:
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing to replace incompatible immutable audit: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def check_certificate(
    raw: bytes,
    uncovered: list[tuple[int, ...]],
    available: list[int],
    slots: int,
) -> float:
    certificate = json.loads(raw)
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
        raise ValueError("weighted total does not exceed residual budget")
    maximum = max(
        (
            sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
            for value in available
        ),
        default=0,
    )
    if maximum != certificate["maximum_eligible_block_load"] or maximum > denominator:
        raise ValueError("eligible block exceeds certified unit weight")
    return total / denominator - slots


def audit() -> dict[str, object]:
    scale = json.loads(SCALE_MANIFEST.read_text())
    segment = next(row for row in scale["segments"] if row["segment_id"] == "weighted-scale-000")
    protocol = json.loads(PROTOCOL.read_text())
    assignment = json.loads(ASSIGNMENT.read_text())
    summary = json.loads(SUMMARY.read_text())
    review = json.loads(V1_REVIEW.read_text())
    if review["single_next_action"]["name"] != "weighted-scale-segment-000-compact-v2-audit":
        raise ValueError("compact-v2 was not the reviewed next action")
    if protocol["case_count"] != 256 or protocol["case_ids_sha256"] != segment["case_ids_sha256"]:
        raise ValueError("protocol membership binding mismatch")
    if assignment["case_ids_sha256"] != segment["case_ids_sha256"] or assignment["mathematical_compute_authorized"]:
        raise ValueError("assignment or compute authorization mismatch")
    with gzip.open(V1_INDEX, "rb") as stream:
        v1_index = json.loads(stream.read())
    v1_rows = {row["case_id"]: row for row in v1_index["rows"]}
    with gzip.open(INDEX, "rb") as stream:
        v2_index = json.loads(stream.read())
    if len(v2_index["rows"]) != 256 or [row[0] for row in v2_index["rows"]] != list(range(256)):
        raise ValueError("compact-v2 index membership mismatch")
    source = json.loads(SOURCE.read_text())
    target_cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    margins = []
    source_bound = certificate_bound = domains_checked = arithmetic_checked = 0
    for index, job in enumerate(segment["cases"]):
        case_id = job["case_id"]
        v2_receipt_path = TARGET / f"receipts/{index:03d}.json"
        v2_receipt = json.loads(v2_receipt_path.read_text())
        index_row = v2_index["rows"][index]
        if (
            v2_receipt["i"] != index
            or v2_receipt["id"] != case_id
            or index_row[1] != sha(v2_receipt_path)
        ):
            raise ValueError(f"{case_id}: compact-v2 row binding mismatch")
        v1_row = v1_rows[case_id]
        v1_receipt_path = ROOT / v1_row["receipt_path"]
        v1_receipt = json.loads(v1_receipt_path.read_text())
        if v2_receipt["src"] != sha(v1_receipt_path):
            raise ValueError(f"{case_id}: source receipt hash mismatch")
        source_bound += 1
        certificate_path = ROOT / v1_receipt["certificate"]["path"]
        compressed = certificate_path.read_bytes()
        if (
            v2_receipt["cert"] != sha_bytes(compressed)
            or index_row[2] != v2_receipt["cert"]
            or v2_receipt["cert_raw"] != v1_receipt["certificate"]["uncompressed_sha256"]
        ):
            raise ValueError(f"{case_id}: certificate binding mismatch")
        raw = gzip.decompress(compressed)
        if sha_bytes(raw) != v2_receipt["cert_raw"]:
            raise ValueError(f"{case_id}: certificate content hash mismatch")
        certificate_bound += 1
        case = target_cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        domain = residual_domain(job, case, parent_raw)
        checks = {
            "fixed_count": len(domain["fixed"]),
            "forbidden_count": len(domain["forbidden"]),
            "available_count": len(domain["available"]),
            "uncovered_triple_count": len(domain["uncovered"]),
            "remaining_slots": domain["remaining_slots"],
            "fixed_sha256": object_sha(domain["fixed"]),
            "forbidden_sha256": object_sha(domain["forbidden"]),
            "available_sha256": object_sha(domain["available"]),
            "uncovered_sha256": object_sha([list(value) for value in domain["uncovered"]]),
            "unit_recipe_sha256": object_sha(domain["units"]),
            "terminal_state_sha256": domain["state_sha"],
        }
        if checks != v1_receipt["domain"] or v2_receipt["domain"] != object_sha(v1_receipt["domain"]):
            raise ValueError(f"{case_id}: independently reconstructed domain mismatch")
        domains_checked += 1
        margin = check_certificate(
            raw,
            domain["uncovered"],
            domain["available"],
            domain["remaining_slots"],
        )
        if (
            abs(margin - v2_receipt["margin"]) > 1e-12
            or v2_receipt["runtime"] != v1_receipt["continuous_lp"]["elapsed_seconds"]
            or v2_receipt["lower"] != v1_receipt["normalized_lower_bound"]
        ):
            raise ValueError(f"{case_id}: scalar receipt mismatch")
        margins.append(margin)
        arithmetic_checked += 1
    certificate_bytes = sum(
        (ROOT / json.loads((ROOT / row["receipt_path"]).read_text())["certificate"]["path"]).stat().st_size
        for row in v1_index["rows"]
    )
    receipt_bytes = sum(path.stat().st_size for path in (TARGET / "receipts").glob("*.json"))
    metadata_bytes = PROTOCOL.stat().st_size + ASSIGNMENT.stat().st_size + INDEX.stat().st_size
    measured = certificate_bytes + receipt_bytes + metadata_bytes
    projected = math.ceil(measured * 4402 / 256 * 1.1)
    maximum = protocol["success_gate"]["maximum_projected_complete_bytes_with_10pct_safety"]
    gate = (
        source_bound == certificate_bound == domains_checked == arithmetic_checked == 256
        and projected <= maximum
    )
    if summary["measured_package_bytes"] != measured or summary["projected_complete_4402_bytes_with_10pct_safety"] != projected:
        raise ValueError("producer size summary mismatch")
    report = {
        "schema_version": 2,
        "status": "VALID",
        "case_count": 256,
        "source_receipts_bound": source_bound,
        "certificates_bound": certificate_bound,
        "residual_domains_independently_reconstructed": domains_checked,
        "arithmetic_certificates_independently_checked": arithmetic_checked,
        "minimum_margin": min(margins),
        "maximum_margin": max(margins),
        "certificate_bytes_reused_once": certificate_bytes,
        "compact_v2_receipt_bytes": receipt_bytes,
        "protocol_assignment_index_bytes": metadata_bytes,
        "measured_package_bytes": measured,
        "projected_complete_4402_bytes_with_10pct_safety": projected,
        "maximum_projected_bytes": maximum,
        "success_gate_passed": gate,
        "protocol_sha256": sha(PROTOCOL),
        "index_sha256": sha(INDEX),
        "summary_sha256": sha(SUMMARY),
        "claim_limit": "Storage-only audit. The 256 mathematical closures remain those certified by the immutable segment-000 v1 audit.",
    }
    write_immutable(OUTPUT, compact_json(report))
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
