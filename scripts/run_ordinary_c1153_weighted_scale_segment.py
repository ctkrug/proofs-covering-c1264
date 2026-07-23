#!/usr/bin/env python3
"""Run exactly the reviewed first compact weighted-certificate scale segment."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import statistics
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
GATE = BASE / "multi-deficit-propagation-gate-v1/weighted-generalization-gate-v1"
COMPACT = GATE / "compact-package-v1"
SCALE_MANIFEST = COMPACT / "scale-manifest.json"
SCALE_AUDIT = COMPACT / "scale-audit.json"
REVIEW = COMPACT / "review-gate.json"
TARGET = COMPACT / "scale-segments/weighted-scale-000"
PROTOCOL = TARGET / "protocol.json"
ASSIGNMENT = TARGET / "assignment.json"
CERTIFICATES = TARGET / "certificates"
RECEIPTS = TARGET / "receipts"
INDEX = TARGET / "index.json.gz"
SUMMARY = TARGET / "summary.json"
SEGMENT_ID = "weighted-scale-000"
LP_SECONDS = 1
DUAL_DENOMINATOR = 1_000_000
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
sys.path.insert(0, str(ROOT / "scripts"))
from run_ordinary_c1153_ilp_forced_gate import residual_domain, solve_cover  # noqa: E402
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


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


def segment() -> dict[str, object]:
    manifest = json.loads(SCALE_MANIFEST.read_text())
    audit = json.loads(SCALE_AUDIT.read_text())
    review = json.loads(REVIEW.read_text())
    if sha(SCALE_MANIFEST) != review["bindings"]["scale_manifest_sha256"]:
        raise ValueError("review does not bind the frozen scale manifest")
    if sha(SCALE_AUDIT) != review["bindings"]["scale_audit_sha256"]:
        raise ValueError("review does not bind the scale audit")
    if (
        audit["status"] != "VALID"
        or not audit["membership_exhaustive"]
        or not audit["segments_pairwise_disjoint"]
    ):
        raise ValueError("scale membership audit is not valid")
    if review["single_next_action"]["name"] != "weighted-scale-segment-000":
        raise ValueError("review does not authorize segment 000")
    selected = [row for row in manifest["segments"] if row["segment_id"] == SEGMENT_ID]
    if len(selected) != 1 or selected[0]["case_count"] != 256:
        raise ValueError("frozen segment 000 is not exactly 256 cases")
    if selected[0]["case_ids_sha256"] != object_sha([row["case_id"] for row in selected[0]["cases"]]):
        raise ValueError("segment case ID binding mismatch")
    return selected[0]


def freeze() -> dict[str, object]:
    selected = segment()
    protocol = {
        "schema_version": 1,
        "status": "AUTHORIZED_NOT_RUN",
        "segment_id": SEGMENT_ID,
        "case_count": 256,
        "cases": selected["cases"],
        "case_ids_sha256": selected["case_ids_sha256"],
        "bindings": {
            "scale_manifest_sha256": sha(SCALE_MANIFEST),
            "scale_audit_sha256": sha(SCALE_AUDIT),
            "review_gate_sha256": sha(REVIEW),
        },
        "fixed_route": {
            "continuous_lp_seconds_per_case": LP_SECONDS,
            "parallelism": 1,
            "dual_denominator": DUAL_DENOMINATOR,
            "artifact_format": "one deterministic gzip exact certificate plus one compact hash-bound receipt per case",
            "sat_pb_solver_calls": 0,
        },
        "continuation_gate": {
            "minimum_certified": 240,
            "required_checker_fraction": 1.0,
            "maximum_median_lp_seconds": 0.5,
            "projected_complete_bytes_with_safety": 12_102_474,
        },
        "stop_rule": "Stop after exactly 256 results or on any binding, reconstruction, checker, or resource failure. Segment 001 is not authorized.",
        "claim_limit": "Only independently checked exact arithmetic certificates close cubes. No ancestor or campaign ledger changes without separate aggregation.",
    }
    assignment = {
        "schema_version": 1,
        "segment_id": SEGMENT_ID,
        "protocol_object_sha256": object_sha(protocol),
        "cloud": {
            "role": "EXCLUSIVE_CONTINUOUS_LP_AND_RECEIPT_OWNER",
            "case_ids": [row["case_id"] for row in selected["cases"]],
        },
        "local": {"role": "INDEPENDENT_CHECK_AND_PUBLICATION_ONLY", "case_ids": []},
        "exclusivity": "Every case is assigned exactly once to cloud.",
    }
    write_immutable(PROTOCOL, compact_json(protocol))
    write_immutable(ASSIGNMENT, compact_json(assignment))
    return protocol


def exact_certificate(
    uncovered: list[tuple[int, ...]],
    available: list[int],
    slots: int,
) -> tuple[dict[str, object], dict[str, object] | None]:
    with tempfile.TemporaryDirectory(prefix="weighted-scale-000-") as temporary:
        report = solve_cover(
            uncovered,
            available,
            LP_SECONDS,
            Path(temporary) / "continuous-lp.log",
            continuous=True,
        )
    scalar_report = {
        "status": report["status"],
        "objective": report["objective"],
        "elapsed_seconds": report.get("elapsed_seconds"),
    }
    if report["status"] != "Optimal" or not report["duals"]:
        return scalar_report, None
    positive = [(tuple(row["triple"]), max(0.0, row["value"])) for row in report["duals"]]
    maximum_float_load = max(
        (
            sum(weight for triple, weight in positive if triple in BLOCK_TRIPLES[value - 1])
            for value in available
        ),
        default=0.0,
    )
    scale = max(1.0, maximum_float_load)
    weights = {
        triple: math.floor((weight / scale) * DUAL_DENOMINATOR)
        for triple, weight in positive
        if weight > 0
    }
    weights = {triple: weight for triple, weight in weights.items() if weight > 0}
    total = sum(weights.values())
    maximum = max(
        (
            sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
            for value in available
        ),
        default=0,
    )
    if total <= slots * DUAL_DENOMINATOR or maximum > DUAL_DENOMINATOR:
        return scalar_report, None
    certificate = {
        "schema_version": 1,
        "denominator": DUAL_DENOMINATOR,
        "remaining_slots": slots,
        "weighted_triples": [
            {"triple": list(triple), "numerator": numerator}
            for triple, numerator in sorted(weights.items())
        ],
        "total_numerator": total,
        "maximum_eligible_block_load": maximum,
        "eligible_block_count": len(available),
        "normalized_lower_bound": total / DUAL_DENOMINATOR,
        "margin_over_remaining_slots": total / DUAL_DENOMINATOR - slots,
    }
    return scalar_report, certificate


def run_case(
    job: dict[str, object],
    case: dict[str, object],
    parent_raw: bytes,
) -> dict[str, object]:
    receipt_path = RECEIPTS / f"{job['case_id']}.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if any(receipt[key] != value for key, value in job.items()):
            raise ValueError(f"{job['case_id']}: immutable receipt case mismatch")
        return receipt
    domain = residual_domain(job, case, parent_raw)
    uncovered = [tuple(triple) for triple in domain["uncovered"]]
    lp, certificate = exact_certificate(
        uncovered, domain["available"], domain["remaining_slots"]
    )
    certificate_reference = None
    if certificate is not None:
        raw = compact_json(certificate)
        certificate_path = CERTIFICATES / f"{job['case_id']}.json.gz"
        compressed = gzip_bytes(raw)
        write_immutable(certificate_path, compressed)
        certificate_reference = {
            "path": str(certificate_path.relative_to(ROOT)),
            "sha256": sha_bytes(compressed),
            "uncompressed_sha256": sha_bytes(raw),
            "bytes": len(compressed),
        }
    receipt = {
        "schema_version": 1,
        **job,
        "protocol_sha256": sha(PROTOCOL),
        "parent_cnf_sha256": sha_bytes(parent_raw),
        "domain": {
            "fixed_count": len(domain["fixed"]),
            "forbidden_count": len(domain["forbidden"]),
            "available_count": len(domain["available"]),
            "uncovered_triple_count": len(uncovered),
            "remaining_slots": domain["remaining_slots"],
            "fixed_sha256": object_sha(domain["fixed"]),
            "forbidden_sha256": object_sha(domain["forbidden"]),
            "available_sha256": object_sha(domain["available"]),
            "uncovered_sha256": object_sha(domain["uncovered"]),
            "unit_recipe_sha256": object_sha(domain["units"]),
            "terminal_state_sha256": domain["state"]["terminal_state_sha256"],
        },
        "continuous_lp": lp,
        "certificate": certificate_reference,
        "status": "WEIGHTED_OBSTRUCTION_PENDING_AUDIT" if certificate else "OPEN_NO_CERTIFICATE",
        "normalized_lower_bound": None if certificate is None else certificate["normalized_lower_bound"],
        "margin_over_remaining_slots": None if certificate is None else certificate["margin_over_remaining_slots"],
        "claim_limit": "Provisional until independent residual reconstruction and exact arithmetic checking pass.",
    }
    write_immutable(receipt_path, compact_json(receipt))
    return receipt


def distribution(values: list[float | int]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {}
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p50": statistics.median(ordered),
        "p90": ordered[round(0.9 * (len(ordered) - 1))],
        "max": ordered[-1],
        "total": sum(ordered),
    }


def run() -> dict[str, object]:
    protocol = freeze()
    source = json.loads(SOURCE.read_text())
    cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    receipts = []
    for job in protocol["cases"]:
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
        receipts.append(run_case(job, case, parent_raw))
    rows = []
    for receipt in receipts:
        path = RECEIPTS / f"{receipt['case_id']}.json"
        rows.append({
            "case_id": receipt["case_id"],
            "status": receipt["status"],
            "receipt_path": str(path.relative_to(ROOT)),
            "receipt_sha256": sha(path),
            "certificate_path": None if receipt["certificate"] is None else receipt["certificate"]["path"],
            "certificate_sha256": None if receipt["certificate"] is None else receipt["certificate"]["sha256"],
        })
    write_immutable(INDEX, gzip_bytes(compact_json({
        "schema_version": 1,
        "segment_id": SEGMENT_ID,
        "rows": rows,
    })))
    certified = [row for row in receipts if row["certificate"] is not None]
    artifact_paths = [PROTOCOL, ASSIGNMENT, INDEX, *RECEIPTS.glob("*.json"), *CERTIFICATES.glob("*.gz")]
    artifact_bytes = sum(path.stat().st_size for path in artifact_paths)
    summary = {
        "schema_version": 1,
        "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "segment_id": SEGMENT_ID,
        "protocol_sha256": sha(PROTOCOL),
        "index_sha256": sha(INDEX),
        "completed": len(receipts),
        "weighted_certificate_count": len(certified),
        "open_no_certificate_count": len(receipts) - len(certified),
        "sat_count": 0,
        "runtime_seconds": distribution([row["continuous_lp"]["elapsed_seconds"] for row in receipts]),
        "arithmetic_margin": distribution([row["margin_over_remaining_slots"] for row in certified]),
        "compact_artifact_bytes_before_summary": artifact_bytes,
        "projected_complete_4402_bytes_with_10pct_safety": math.ceil(artifact_bytes * 4402 / 256 * 1.1),
        "claim_limit": "No segment cube counts until the independent audit passes.",
    }
    write_immutable(SUMMARY, compact_json(summary))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run()
    print(json.dumps(report, indent=2, sort_keys=True))
