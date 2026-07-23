#!/usr/bin/env python3
"""Independent audit for compact weighted certificates and frozen scale membership."""

from __future__ import annotations

import argparse
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
GATE = BASE / "multi-deficit-propagation-gate-v1"
STRUCTURAL = GATE / "manifest.json"
WEIGHTED = GATE / "weighted-generalization-gate-v1"
PROTOCOL = WEIGHTED / "protocol.json"
SUMMARY = WEIGHTED / "summary.json"
ILP_PROTOCOL = GATE / "ilp-forced-gate-v1/protocol.json"
TARGET = WEIGHTED / "compact-package-v1"
SOURCE_INDEX = TARGET / "source-index.json"
BUILD_SUMMARY = TARGET / "build-summary.json"
RECEIPTS = TARGET / "receipts"
AGGREGATE_INDEX = TARGET / "aggregate-index.json.gz"
OUTPUT = TARGET / "independent-audit.json"
SCALE_MANIFEST = TARGET / "scale-manifest.json"
SCALE_AUDIT = TARGET / "scale-audit.json"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
SAFETY_NUMERATOR = 11
SAFETY_DENOMINATOR = 10
MAX_PROJECTED_BYTES = 50_000_000
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
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def gzip_bytes(raw: bytes) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0, compresslevel=9) as stream:
        stream.write(raw)
    return buffer.getvalue()


def write_immutable(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing to replace incompatible immutable file: {path}")
        return
    path.write_bytes(raw)


def check_arithmetic(
    certificate: dict[str, object],
    uncovered: list[tuple[int, ...]],
    available: list[int],
    slots: int,
) -> None:
    denominator = certificate["denominator"]
    if denominator <= 0 or certificate["remaining_slots"] != slots:
        raise ValueError("certificate residual budget mismatch")
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
        raise ValueError("weighted total does not exceed the residual budget")
    maximum = max(
        (
            sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
            for value in available
        ),
        default=0,
    )
    if maximum != certificate["maximum_eligible_block_load"] or maximum > denominator:
        raise ValueError("eligible block exceeds unit normalized load")


def audit_compact() -> dict[str, object]:
    protocol = json.loads(PROTOCOL.read_text())
    summary = json.loads(SUMMARY.read_text())
    source_index = json.loads(SOURCE_INDEX.read_text())
    build = json.loads(BUILD_SUMMARY.read_text())
    if source_index["case_count"] != 96 or build["case_count"] != 96:
        raise ValueError("compact package membership is not 96")
    jobs = {row["case_id"]: row for row in protocol["cases"]}
    outcomes = {row["case_id"]: row for row in summary["outcomes"]}
    rows = {row["case_id"]: row for row in source_index["cases"]}
    if len(jobs) != 96 or set(jobs) != set(outcomes) or set(jobs) != set(rows):
        raise ValueError("compact/source membership mismatch")
    if source_index["case_ids_sha256"] != object_sha(sorted(rows)):
        raise ValueError("compact case ID binding mismatch")
    source = json.loads(SOURCE.read_text())
    target_cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    receipt_rows = []
    certificate_bytes = 0
    receipt_bytes = 0
    for case_id in sorted(jobs):
        job, outcome, row = jobs[case_id], outcomes[case_id], rows[case_id]
        source_result = ROOT / row["source_result"]["path"]
        if sha(source_result) != row["source_result"]["sha256"]:
            raise ValueError(f"{case_id}: source result hash mismatch")
        if json.loads(source_result.read_text()) != outcome:
            raise ValueError(f"{case_id}: source result content mismatch")
        source_certificate = ROOT / row["source_certificate"]["path"]
        source_raw = source_certificate.read_bytes()
        if sha_bytes(source_raw) != row["source_certificate"]["sha256"]:
            raise ValueError(f"{case_id}: source certificate hash mismatch")
        compact_certificate = ROOT / row["compact_certificate"]["path"]
        if sha(compact_certificate) != row["compact_certificate"]["sha256"]:
            raise ValueError(f"{case_id}: compact certificate hash mismatch")
        with gzip.open(compact_certificate, "rb") as stream:
            expanded = stream.read()
        if expanded != source_raw or sha_bytes(expanded) != row["compact_certificate"]["uncompressed_sha256"]:
            raise ValueError(f"{case_id}: compact certificate is not byte-identical")
        case = target_cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        domain = residual_domain(job, case, parent_raw)
        recorded_domain = outcome["domain"]
        domain_hashes = {
            "fixed_sha256": object_sha(domain["fixed"]),
            "forbidden_sha256": object_sha(domain["forbidden"]),
            "available_sha256": object_sha(domain["available"]),
            "uncovered_sha256": object_sha([list(value) for value in domain["uncovered"]]),
            "unit_recipe_sha256": object_sha(domain["units"]),
            "terminal_state_sha256": domain["state_sha"],
        }
        if any(recorded_domain[key] != value for key, value in domain_hashes.items()):
            raise ValueError(f"{case_id}: independently reconstructed domain mismatch")
        certificate = json.loads(expanded)
        check_arithmetic(
            certificate,
            domain["uncovered"],
            domain["available"],
            domain["remaining_slots"],
        )
        receipt = {
            "v": 1,
            "case_id": case_id,
            "source_result_sha256": row["source_result"]["sha256"],
            "source_certificate_sha256": row["source_certificate"]["sha256"],
            "compact_certificate_path": row["compact_certificate"]["path"],
            "compact_certificate_sha256": row["compact_certificate"]["sha256"],
            "domain_hashes": domain_hashes,
            "remaining_slots": domain["remaining_slots"],
            "normalized_lower_bound": certificate["normalized_lower_bound"],
            "margin": certificate["margin_over_remaining_slots"],
            "lp_status": outcome["continuous_lp"]["status"],
            "lp_runtime_seconds": outcome["continuous_lp"]["elapsed_seconds"],
            "checker_status": "VALID",
        }
        receipt_path = RECEIPTS / f"{case_id}.json"
        write_immutable(receipt_path, compact_json(receipt))
        receipt_bytes += receipt_path.stat().st_size
        certificate_bytes += compact_certificate.stat().st_size
        receipt_rows.append({
            "case_id": case_id,
            "status": "VALID",
            "receipt_path": str(receipt_path.relative_to(ROOT)),
            "receipt_sha256": sha(receipt_path),
            "certificate_path": row["compact_certificate"]["path"],
            "certificate_sha256": row["compact_certificate"]["sha256"],
        })
    aggregate_raw = compact_json({
        "v": 1,
        "status": "VALID",
        "case_count": 96,
        "rows": receipt_rows,
    })
    write_immutable(AGGREGATE_INDEX, gzip_bytes(aggregate_raw))
    package_bytes = certificate_bytes + receipt_bytes + AGGREGATE_INDEX.stat().st_size
    projected_without_safety = math.ceil(package_bytes * 4402 / 96)
    projected_with_safety = math.ceil(
        projected_without_safety * SAFETY_NUMERATOR / SAFETY_DENOMINATOR
    )
    report = {
        "schema_version": 1,
        "status": "VALID",
        "case_count": 96,
        "source_index_sha256": sha(SOURCE_INDEX),
        "build_summary_sha256": sha(BUILD_SUMMARY),
        "independently_bound_source_results": 96,
        "independently_bound_byte_identical_certificates": 96,
        "independently_reconstructed_domains": 96,
        "independently_checked_arithmetic_certificates": 96,
        "compact_certificate_bytes": certificate_bytes,
        "compact_receipt_bytes": receipt_bytes,
        "aggregate_index_bytes": AGGREGATE_INDEX.stat().st_size,
        "measured_package_bytes": package_bytes,
        "projected_full_4402_bytes_without_safety": projected_without_safety,
        "safety_margin_percent": 10,
        "projected_full_4402_bytes_with_safety": projected_with_safety,
        "maximum_projected_bytes": MAX_PROJECTED_BYTES,
        "success_gate_passed": projected_with_safety < MAX_PROJECTED_BYTES,
        "original_artifacts_preserved": True,
        "new_mathematical_compute": False,
        "claim_limit": "Representation audit only. It preserves the 96 existing arithmetic cube closures and changes no ancestor or campaign ledger.",
    }
    write_immutable(OUTPUT, compact_json(report))
    return report


def make_id(formula_id: str, path: list[int]) -> str:
    return f"{formula_id}-cube-{path[0]:03d}-{path[1]:03d}"


def audit_scale() -> dict[str, object]:
    compact = json.loads(OUTPUT.read_text())
    if compact["status"] != "VALID" or not compact["success_gate_passed"]:
        raise ValueError("compact gate is not eligible for scale freeze")
    manifest = json.loads(SCALE_MANIFEST.read_text())
    structural = json.loads(STRUCTURAL.read_text())
    weighted = json.loads(PROTOCOL.read_text())
    ilp = json.loads(ILP_PROTOCOL.read_text())
    all_ids = {
        make_id(formula["leaf_id"], row["path"])
        for formula in structural["formulas"]
        for row in formula["terminal_partition"]
        if row["kind"] == "frontier"
    }
    closed = {row["case_id"] for row in weighted["cases"]} | {row["case_id"] for row in ilp["cases"]}
    expected_open = all_ids - closed
    seen = []
    for segment in manifest["segments"]:
        ids = [row["case_id"] for row in segment["cases"]]
        if len(ids) != segment["case_count"] or object_sha(ids) != segment["case_ids_sha256"]:
            raise ValueError(f"{segment['segment_id']}: segment binding mismatch")
        seen.extend(ids)
    if len(all_ids) != 4402 or len(closed) != 102 or len(expected_open) != 4300:
        raise ValueError("independent frontier count mismatch")
    if len(seen) != 4300 or len(set(seen)) != 4300 or set(seen) != expected_open:
        raise ValueError("scale segments are not an exhaustive disjoint open-case partition")
    if object_sha(seen) != manifest["open_case_ids_sha256"]:
        raise ValueError("scale open-case order binding mismatch")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "scale_manifest_sha256": sha(SCALE_MANIFEST),
        "frontier_case_count": 4402,
        "already_certified_weighted_cases": 102,
        "open_case_count": 4300,
        "segment_count": len(manifest["segments"]),
        "segment_size": manifest["segment_size"],
        "membership_exhaustive": True,
        "segments_pairwise_disjoint": True,
        "execution_authorized": False,
        "claim_limit": "Manifest coverage only. No scale case has been run or closed.",
    }
    write_immutable(SCALE_AUDIT, compact_json(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("compact", "scale"))
    args = parser.parse_args()
    report = audit_compact() if args.mode == "compact" else audit_scale()
    print(json.dumps(report, indent=2, sort_keys=True))
