#!/usr/bin/env python3
"""Freeze or run compact shallow weighted-certificate scale segments."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import os
import statistics
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
SOURCE_AUDIT = BASE / "independent-audit.json"
SAMPLE = BASE / "discriminator-5s/protocol.json"
SHALLOW_AUDIT = BASE / "shallow-weighted-gate-v1/independent-audit.json"
DEEP_AUDIT = BASE / "multi-deficit-propagation-gate-v1/weighted-complete-aggregation-v1/independent-audit.json"
TARGET = BASE / "shallow-weighted-scale-v1"
MANIFEST = TARGET / "manifest.json"
SEGMENTS = TARGET / "segments"
SEGMENT_SIZE = 2048
LP_SECONDS = 1
DENOMINATOR = 1_000_000
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from run_ordinary_c1153_ilp_forced_gate import residual_domain, solve_cover  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def compact(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_immutable(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing to replace incompatible artifact: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def all_jobs() -> list[dict[str, object]]:
    source = json.loads(SOURCE.read_text())
    rows = []
    for case in sorted(source["target_cases"], key=lambda row: row["id"]):
        for index in range(case["second_partition_children"]):
            cid = f"{case['id']}-second-{index:03d}"
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
    if len(rows) != 173_880 or len({row["case_id"] for row in rows}) != 173_880:
        raise ValueError("second-live universe is not exactly 173,880 unique formulas")
    return rows


def open_jobs() -> list[dict[str, object]]:
    closed = {row["leaf_id"] for row in json.loads(SAMPLE.read_text())["sample"]}
    rows = [row for row in all_jobs() if row["case_id"] not in closed]
    if len(closed) != 48 or len(rows) != 173_832:
        raise ValueError("scale universe is not exactly 173,832 formulas after 48 certified exclusions")
    return rows


def freeze() -> dict[str, object]:
    source_audit = json.loads(SOURCE_AUDIT.read_text())
    shallow_audit = json.loads(SHALLOW_AUDIT.read_text())
    deep_audit = json.loads(DEEP_AUDIT.read_text())
    if source_audit["status"] != "VALID" or source_audit["manifest_sha256"] != sha(SOURCE):
        raise ValueError("source second-live audit failed")
    if shallow_audit["status"] != "VALID" or shallow_audit["independently_checked_weighted_formulas"] != 36:
        raise ValueError("36-formula shallow gate did not pass")
    if deep_audit["status"] != "VALID" or deep_audit["formulas_independently_aggregated_closed"] != 12:
        raise ValueError("12-formula deep aggregation did not pass")
    rows = open_jobs()
    segments = []
    for start in range(0, len(rows), SEGMENT_SIZE):
        cases = rows[start:start + SEGMENT_SIZE]
        segments.append({
            "segment_id": f"shallow-weighted-scale-{start // SEGMENT_SIZE:03d}",
            "start": start,
            "stop": start + len(cases),
            "case_count": len(cases),
            "case_ids_sha256": object_sha([row["case_id"] for row in cases]),
        })
    manifest = {
        "schema_version": 1,
        "status": "FROZEN",
        "bindings": {
            "second_live_manifest": {"path": str(SOURCE.relative_to(ROOT)), "sha256": sha(SOURCE)},
            "second_live_audit": {"path": str(SOURCE_AUDIT.relative_to(ROOT)), "sha256": sha(SOURCE_AUDIT)},
            "sample_protocol": {"path": str(SAMPLE.relative_to(ROOT)), "sha256": sha(SAMPLE)},
            "shallow_audit": {"path": str(SHALLOW_AUDIT.relative_to(ROOT)), "sha256": sha(SHALLOW_AUDIT)},
            "deep_aggregation_audit": {"path": str(DEEP_AUDIT.relative_to(ROOT)), "sha256": sha(DEEP_AUDIT)},
        },
        "complete_formula_universe": 173_880,
        "already_certified_formulas": 48,
        "open_formula_count": len(rows),
        "open_case_ids_sha256": object_sha([row["case_id"] for row in rows]),
        "segment_size": SEGMENT_SIZE,
        "segment_count": len(segments),
        "segments": segments,
        "representation": "Formula membership is deterministically regenerated from the exact audited source manifest; each segment binds its sorted case-ID slice without duplicating the full 173,832-row universe.",
        "fixed_route": {
            "continuous_lp_seconds_per_formula": LP_SECONDS,
            "parallelism": 1,
            "compact_artifact": "one deterministic gzip JSONL certificate/receipt archive plus one summary per segment",
            "sat_solver_calls": 0,
        },
        "continuation_gate": "Continue consecutive segments while every formula receives an independently checked exact certificate, median runtime stays below 0.5 seconds, and projected compressed storage remains below 500 MB.",
        "claim_limit": "Individual formulas close only after independent checking. Target children and higher ancestors require complete child-by-child aggregation.",
    }
    write_immutable(MANIFEST, compact(manifest))
    return manifest


def exact_certificate(duals: list[dict[str, object]], available: list[int], slots: int) -> dict[str, object] | None:
    positive = [(tuple(row["triple"]), max(0.0, row["value"])) for row in duals]
    max_float_load = max(
        (sum(weight for triple, weight in positive if triple in BLOCK_TRIPLES[value - 1]) for value in available),
        default=0.0,
    )
    scale = max(1.0, max_float_load)
    weights = {
        triple: math.floor(weight / scale * DENOMINATOR)
        for triple, weight in positive if weight > 0
    }
    weights = {triple: weight for triple, weight in weights.items() if weight > 0}
    total = sum(weights.values())
    maximum = max((
        sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
        for value in available
    ), default=0)
    if total <= slots * DENOMINATOR or maximum > DENOMINATOR:
        return None
    return {
        "denominator": DENOMINATOR,
        "remaining_slots": slots,
        "weights": [[*triple, numerator] for triple, numerator in sorted(weights.items())],
        "total_numerator": total,
        "maximum_eligible_block_load": maximum,
        "margin": total / DENOMINATOR - slots,
    }


def run_segment(number: int) -> dict[str, object]:
    manifest = freeze()
    segment = manifest["segments"][number]
    rows = open_jobs()[segment["start"]:segment["stop"]]
    if object_sha([row["case_id"] for row in rows]) != segment["case_ids_sha256"]:
        raise ValueError("segment membership hash mismatch")
    source = json.loads(SOURCE.read_text())
    cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    outcomes = []
    with tempfile.TemporaryDirectory(prefix=f"shallow-weighted-{number:03d}-") as temporary:
        temp = Path(temporary)
        for index, job in enumerate(rows):
            case = cases[job["target_child_id"]]
            parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
            parent_raw = parents[parent_id]
            if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
                raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
            domain = residual_domain(job, case, parent_raw)
            report = solve_cover(
                [tuple(row) for row in domain["uncovered"]],
                domain["available"],
                LP_SECONDS,
                temp / f"{index:04d}.log",
                continuous=True,
            )
            certificate = exact_certificate(report["duals"], domain["available"], domain["remaining_slots"]) if report["status"] == "Optimal" else None
            outcomes.append({
                **job,
                "parent_cnf_sha256": sha_bytes(parent_raw),
                "domain": {
                    "fixed_sha256": object_sha(domain["fixed"]),
                    "forbidden_sha256": object_sha(domain["forbidden"]),
                    "available_sha256": object_sha(domain["available"]),
                    "uncovered_sha256": object_sha(domain["uncovered"]),
                    "unit_recipe_sha256": object_sha(domain["units"]),
                    "remaining_slots": domain["remaining_slots"],
                },
                "lp_status": report["status"],
                "lp_runtime_seconds": report["elapsed_seconds"],
                "certificate": certificate,
                "status": "WEIGHTED_OBSTRUCTION_PENDING_AUDIT" if certificate else "OPEN_NO_CERTIFICATE",
            })
    raw = b"".join(compact(row) for row in outcomes)
    archive_raw = gzip.compress(raw, compresslevel=9, mtime=0)
    folder = SEGMENTS / segment["segment_id"]
    archive = folder / "outcomes.jsonl.gz"
    write_immutable(archive, archive_raw)
    certified = [row for row in outcomes if row["certificate"] is not None]
    runtimes = [row["lp_runtime_seconds"] for row in outcomes]
    margins = [row["certificate"]["margin"] for row in certified]
    projected = math.ceil(len(archive_raw) * manifest["open_formula_count"] / len(rows))
    summary = {
        "schema_version": 1,
        "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "segment_id": segment["segment_id"],
        "manifest_sha256": sha(MANIFEST),
        "selected": len(rows),
        "completed": len(outcomes),
        "weighted_certificate_count": len(certified),
        "open_no_certificate_count": len(outcomes) - len(certified),
        "median_runtime_seconds": statistics.median(runtimes),
        "minimum_margin": min(margins) if margins else None,
        "maximum_margin": max(margins) if margins else None,
        "outcome_archive": {
            "path": str(archive.relative_to(ROOT)),
            "sha256": sha(archive),
            "bytes": len(archive_raw),
            "uncompressed_sha256": sha_bytes(raw),
        },
        "projected_complete_compressed_bytes": projected,
        "claim_limit": "Pending independent exact domain and arithmetic audit.",
    }
    write_immutable(folder / "summary.json", compact(summary))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    parser.add_argument("--segment", type=int)
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run_segment(args.segment)
    print(json.dumps({key: report[key] for key in report if key in (
        "status", "open_formula_count", "segment_count", "segment_id", "selected",
        "weighted_certificate_count", "open_no_certificate_count", "median_runtime_seconds",
        "minimum_margin", "maximum_margin", "projected_complete_compressed_bytes",
    )}, indent=2, sort_keys=True))
