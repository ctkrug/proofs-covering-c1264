#!/usr/bin/env python3
"""Independently audit one compact shallow weighted scale segment."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
SAMPLE = BASE / "discriminator-5s/protocol.json"
TARGET = BASE / "shallow-weighted-scale-v1"
MANIFEST = TARGET / "manifest.json"
SEGMENTS = TARGET / "segments"
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


def all_open_jobs() -> list[dict[str, object]]:
    source = json.loads(SOURCE.read_text())
    closed = {row["leaf_id"] for row in json.loads(SAMPLE.read_text())["sample"]}
    rows = []
    for case in sorted(source["target_cases"], key=lambda row: row["id"]):
        for index in range(case["second_partition_children"]):
            cid = f"{case['id']}-second-{index:03d}"
            if cid in closed:
                continue
            rows.append({
                "case_id": cid,
                "formula_id": cid,
                "target_child_id": case["id"],
                "second_index": index,
                "cube_path": [],
                "root_class": case["root_class"],
                "rank_band": case["rank_band"],
                "branch_count_quantile": case["branch_count_quantile"],
                "stabilizer_tier": case["stabilizer_tier"],
            })
    return rows


def audit_manifest() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    for binding in manifest["bindings"].values():
        path = ROOT / binding["path"]
        if sha(path) != binding["sha256"]:
            raise ValueError(f"manifest binding mismatch: {path}")
    rows = all_open_jobs()
    if len(rows) != 173_832 or len({row["case_id"] for row in rows}) != 173_832:
        raise ValueError("open formula universe is not exactly 173,832 unique cases")
    if manifest["complete_formula_universe"] != 173_880 or manifest["already_certified_formulas"] != 48:
        raise ValueError("complete/certified formula counts mismatch")
    if manifest["open_case_ids_sha256"] != object_sha([row["case_id"] for row in rows]):
        raise ValueError("open formula identity hash mismatch")
    cursor = 0
    covered = []
    for index, segment in enumerate(manifest["segments"]):
        if segment["segment_id"] != f"shallow-weighted-scale-{index:03d}":
            raise ValueError("segment ID sequence mismatch")
        if segment["start"] != cursor or segment["stop"] - segment["start"] != segment["case_count"]:
            raise ValueError("segment range gap, overlap, or count mismatch")
        selected = rows[segment["start"]:segment["stop"]]
        if object_sha([row["case_id"] for row in selected]) != segment["case_ids_sha256"]:
            raise ValueError("segment membership hash mismatch")
        covered.extend(row["case_id"] for row in selected)
        cursor = segment["stop"]
    if cursor != len(rows) or covered != [row["case_id"] for row in rows]:
        raise ValueError("segments are not an exhaustive ordered partition")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": sha(MANIFEST),
        "complete_formula_universe": 173_880,
        "already_certified_formulas_excluded": 48,
        "open_formula_count": len(rows),
        "segment_count": len(manifest["segments"]),
        "missing_duplicate_or_extra_cases": 0,
        "claim_limit": "Manifest coverage only; no unsolved formula closes.",
    }
    output = TARGET / "independent-manifest-audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def audit(number: int) -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    for binding in manifest["bindings"].values():
        path = ROOT / binding["path"]
        if sha(path) != binding["sha256"]:
            raise ValueError(f"manifest binding mismatch: {path}")
    if manifest["open_formula_count"] != 173_832:
        raise ValueError("open formula universe mismatch")
    segment = manifest["segments"][number]
    expected = all_open_jobs()[segment["start"]:segment["stop"]]
    if len(expected) != segment["case_count"] or object_sha([row["case_id"] for row in expected]) != segment["case_ids_sha256"]:
        raise ValueError("segment membership mismatch")
    folder = SEGMENTS / segment["segment_id"]
    summary_path = folder / "summary.json"
    summary = json.loads(summary_path.read_text())
    archive = ROOT / summary["outcome_archive"]["path"]
    if sha(archive) != summary["outcome_archive"]["sha256"]:
        raise ValueError("outcome archive hash mismatch")
    raw = gzip.decompress(archive.read_bytes())
    if sha_bytes(raw) != summary["outcome_archive"]["uncompressed_sha256"]:
        raise ValueError("uncompressed outcome hash mismatch")
    outcomes = [json.loads(line) for line in raw.splitlines()]
    if len(outcomes) != len(expected) or [row["case_id"] for row in outcomes] != [row["case_id"] for row in expected]:
        raise ValueError("outcome order/membership mismatch")
    source_cases = {row["id"]: row for row in json.loads(SOURCE.read_text())["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    certified = 0
    margins = []
    for job, result in zip(expected, outcomes):
        if any(result[key] != value for key, value in job.items()):
            raise ValueError(f"{job['case_id']}: immutable job mismatch")
        case = source_cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != result["parent_cnf_sha256"]:
            raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
        domain = residual_domain(job, case, parent_raw)
        checks = {
            "fixed_sha256": object_sha(domain["fixed"]),
            "forbidden_sha256": object_sha(domain["forbidden"]),
            "available_sha256": object_sha(domain["available"]),
            "uncovered_sha256": object_sha([list(row) for row in domain["uncovered"]]),
            "unit_recipe_sha256": object_sha(domain["units"]),
            "remaining_slots": domain["remaining_slots"],
        }
        if any(result["domain"][key] != value for key, value in checks.items()):
            raise ValueError(f"{job['case_id']}: residual-domain mismatch")
        cert = result["certificate"]
        if cert is None:
            if result["status"] != "OPEN_NO_CERTIFICATE":
                raise ValueError(f"{job['case_id']}: open status mismatch")
            continue
        weights = {}
        uncovered = set(domain["uncovered"])
        for row in cert["weights"]:
            triple, numerator = tuple(row[:3]), row[3]
            if triple not in uncovered or triple in weights or not isinstance(numerator, int) or numerator <= 0:
                raise ValueError(f"{job['case_id']}: invalid weight")
            weights[triple] = numerator
        total = sum(weights.values())
        denominator = cert["denominator"]
        if total != cert["total_numerator"] or total <= domain["remaining_slots"] * denominator:
            raise ValueError(f"{job['case_id']}: insufficient weighted lower bound")
        maximum = max((
            sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
            for value in domain["available"]
        ), default=0)
        if maximum != cert["maximum_eligible_block_load"] or maximum > denominator:
            raise ValueError(f"{job['case_id']}: eligible block overload")
        margins.append(total / denominator - domain["remaining_slots"])
        certified += 1
    median = statistics.median(row["lp_runtime_seconds"] for row in outcomes)
    valid = certified == len(expected) and median < 0.5 and summary["projected_complete_compressed_bytes"] < 500_000_000
    report = {
        "schema_version": 1,
        "status": "VALID" if valid else "VALID_GATE_FAILED",
        "segment_id": segment["segment_id"],
        "manifest_sha256": sha(MANIFEST),
        "summary_sha256": sha(summary_path),
        "selected": len(expected),
        "independently_checked_weighted_formulas": certified,
        "open_no_certificate_count": len(expected) - certified,
        "median_runtime_seconds": median,
        "minimum_margin": min(margins) if margins else None,
        "maximum_margin": max(margins) if margins else None,
        "projected_complete_compressed_bytes": summary["projected_complete_compressed_bytes"],
        "continuation_gate_passed": valid,
        "claim_limit": "Only exact formulas in this segment close; target-child aggregation is separate.",
    }
    output = folder / "independent-audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", type=int)
    parser.add_argument("--manifest", action="store_true")
    args = parser.parse_args()
    if args.manifest == (args.segment is not None):
        parser.error("choose exactly one of --manifest or --segment")
    report = audit_manifest() if args.manifest else audit(args.segment)
    print(json.dumps(report, indent=2, sort_keys=True))
