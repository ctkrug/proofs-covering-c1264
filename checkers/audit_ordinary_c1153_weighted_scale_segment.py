#!/usr/bin/env python3
"""Independently audit compact weighted-certificate scale segment 000."""

from __future__ import annotations

import gzip
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
COMPACT = BASE / "multi-deficit-propagation-gate-v1/weighted-generalization-gate-v1/compact-package-v1"
SCALE_MANIFEST = COMPACT / "scale-manifest.json"
SCALE_AUDIT = COMPACT / "scale-audit.json"
REVIEW = COMPACT / "review-gate.json"
TARGET = COMPACT / "scale-segments/weighted-scale-000"
PROTOCOL = TARGET / "protocol.json"
ASSIGNMENT = TARGET / "assignment.json"
INDEX = TARGET / "index.json.gz"
SUMMARY = TARGET / "summary.json"
PRIOR_OUTPUT = TARGET / "independent-audit.json"
OUTPUT = TARGET / "independent-audit-v2.json"
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
        raise ValueError("eligible block exceeds unit weight")
    lower = total / denominator
    if abs(lower - certificate["normalized_lower_bound"]) > 1e-12:
        raise ValueError("normalized lower bound mismatch")
    if abs(lower - slots - certificate["margin_over_remaining_slots"]) > 1e-12:
        raise ValueError("arithmetic margin mismatch")
    return lower - slots


def audit() -> dict[str, object]:
    manifest = json.loads(SCALE_MANIFEST.read_text())
    scale_audit = json.loads(SCALE_AUDIT.read_text())
    review = json.loads(REVIEW.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    assignment = json.loads(ASSIGNMENT.read_text())
    summary = json.loads(SUMMARY.read_text())
    selected = [row for row in manifest["segments"] if row["segment_id"] == "weighted-scale-000"]
    if len(selected) != 1 or selected[0]["case_count"] != 256:
        raise ValueError("frozen segment membership mismatch")
    jobs = selected[0]["cases"]
    if protocol["cases"] != jobs or protocol["case_ids_sha256"] != object_sha([row["case_id"] for row in jobs]):
        raise ValueError("protocol does not preserve the frozen segment")
    if protocol["bindings"] != {
        "scale_manifest_sha256": sha(SCALE_MANIFEST),
        "scale_audit_sha256": sha(SCALE_AUDIT),
        "review_gate_sha256": sha(REVIEW),
    }:
        raise ValueError("protocol binding mismatch")
    if (
        scale_audit["status"] != "VALID"
        or not scale_audit["membership_exhaustive"]
        or not scale_audit["segments_pairwise_disjoint"]
    ):
        raise ValueError("scale audit is not valid")
    if review["single_next_action"]["name"] != "weighted-scale-segment-000":
        raise ValueError("review did not authorize segment 000")
    if assignment["cloud"]["case_ids"] != [row["case_id"] for row in jobs] or assignment["local"]["case_ids"]:
        raise ValueError("assignment exclusivity mismatch")
    if summary["completed"] != 256 or summary["protocol_sha256"] != sha(PROTOCOL):
        raise ValueError("segment completion or protocol binding mismatch")
    if summary["index_sha256"] != sha(INDEX):
        raise ValueError("summary index binding mismatch")
    with gzip.open(INDEX, "rb") as stream:
        index = json.loads(stream.read())
    rows = index["rows"]
    expected_ids = [row["case_id"] for row in jobs]
    if [row["case_id"] for row in rows] != expected_ids or len(set(expected_ids)) != 256:
        raise ValueError("index membership, order, or uniqueness mismatch")
    job_map = {row["case_id"]: row for row in jobs}
    source = json.loads(SOURCE.read_text())
    target_cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    certified = 0
    margins = []
    runtimes = []
    by_stratum: dict[str, dict[str, int]] = {}
    for row in rows:
        case_id = row["case_id"]
        receipt_path = ROOT / row["receipt_path"]
        if sha(receipt_path) != row["receipt_sha256"]:
            raise ValueError(f"{case_id}: receipt hash mismatch")
        receipt = json.loads(receipt_path.read_text())
        job = job_map[case_id]
        if any(receipt[key] != value for key, value in job.items()):
            raise ValueError(f"{case_id}: immutable case fields changed")
        if receipt["protocol_sha256"] != sha(PROTOCOL):
            raise ValueError(f"{case_id}: protocol hash mismatch")
        case = target_cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != receipt["parent_cnf_sha256"]:
            raise ValueError(f"{case_id}: parent reconstruction mismatch")
        domain = residual_domain(job, case, parent_raw)
        recorded = receipt["domain"]
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
        runtimes.append(receipt["continuous_lp"]["elapsed_seconds"])
        reference = receipt["certificate"]
        if reference is None:
            if receipt["status"] != "OPEN_NO_CERTIFICATE" or row["certificate_path"] is not None:
                raise ValueError(f"{case_id}: open status mismatch")
            stratum["open"] += 1
            continue
        certificate_path = ROOT / reference["path"]
        compressed = certificate_path.read_bytes()
        if (
            sha_bytes(compressed) != reference["sha256"]
            or row["certificate_sha256"] != reference["sha256"]
            or row["certificate_path"] != reference["path"]
        ):
            raise ValueError(f"{case_id}: certificate binding mismatch")
        raw = gzip.decompress(compressed)
        if sha_bytes(raw) != reference["uncompressed_sha256"]:
            raise ValueError(f"{case_id}: certificate content hash mismatch")
        margin = check_certificate(
            raw,
            domain["uncovered"],
            domain["available"],
            domain["remaining_slots"],
        )
        if abs(margin - receipt["margin_over_remaining_slots"]) > 1e-12:
            raise ValueError(f"{case_id}: receipt margin mismatch")
        certified += 1
        margins.append(margin)
        stratum["certified"] += 1
    if summary["weighted_certificate_count"] != certified:
        raise ValueError("summary certified count mismatch")
    receipt_bytes = sum(path.stat().st_size for path in TARGET.glob("receipts/*.json"))
    certificate_bytes = sum(path.stat().st_size for path in TARGET.glob("certificates/*.gz"))
    index_bytes = INDEX.stat().st_size
    protocol_assignment_bytes = PROTOCOL.stat().st_size + ASSIGNMENT.stat().st_size
    compact_bytes = receipt_bytes + certificate_bytes + index_bytes + protocol_assignment_bytes
    projected = math.ceil(compact_bytes * 4402 / 256 * 1.1)
    median_runtime = statistics.median(runtimes)
    expected_projection = protocol["continuation_gate"]["projected_complete_bytes_with_safety"]
    storage_consistent = projected <= expected_projection
    gate_passed = certified >= 240 and median_runtime < 0.5 and storage_consistent
    report = {
        "schema_version": 1,
        "status": "VALID",
        "segment_id": "weighted-scale-000",
        "protocol_sha256": sha(PROTOCOL),
        "summary_sha256": sha(SUMMARY),
        "index_sha256": sha(INDEX),
        "selected": 256,
        "completed": 256,
        "independently_checked_weighted_obstructions": certified,
        "open_no_certificate_count": 256 - certified,
        "sat_count": 0,
        "minimum_arithmetic_margin": min(margins) if margins else None,
        "maximum_arithmetic_margin": max(margins) if margins else None,
        "median_runtime_seconds": median_runtime,
        "compact_byte_breakdown": {
            "certificates": certificate_bytes,
            "receipts": receipt_bytes,
            "index": index_bytes,
            "protocol_and_assignment": protocol_assignment_bytes,
            "total_before_summary_and_audit": compact_bytes,
        },
        "compact_artifact_bytes_before_summary_and_audit": compact_bytes,
        "projected_complete_4402_bytes_with_10pct_safety": projected,
        "predeclared_projection_bytes_with_10pct_safety": expected_projection,
        "projection_ratio_observed_to_predeclared": projected / expected_projection,
        "storage_projection_consistent": storage_consistent,
        "by_formula_stratum": dict(sorted(by_stratum.items())),
        "continuation_gate_passed": gate_passed,
        "supersedes_gate_evaluation": {
            "path": str(PRIOR_OUTPUT.relative_to(ROOT)),
            "sha256": sha(PRIOR_OUTPUT),
            "reason": "The first immutable audit correctly checked all 256 domains and certificates but omitted the predeclared storage-consistency predicate from its continuation-gate Boolean.",
        },
        "claim_limit": "Only these independently checked cubes are semantic arithmetic closures. No ancestor or campaign ledger changes.",
    }
    write_immutable(OUTPUT, compact_json(report))
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
