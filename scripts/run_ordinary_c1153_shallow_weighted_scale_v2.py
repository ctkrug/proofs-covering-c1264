#!/usr/bin/env python3
"""Run one frozen shallow-weighted segment with the audited v2 backend.

HiGHS proposes floating duals.  Exact integer checking here and the unchanged
campaign checker are the acceptance gates.  Workers write disjoint immutable
chunks; the parent merges them deterministically into the v1-compatible
outcomes archive.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import multiprocessing
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "checkers")]

from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from ordinary_c1153_weighted_backend_v2 import (  # noqa: E402
    exact_check,
    install_exact_identity_cache,
    solve_highs,
)
from run_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402
from run_ordinary_c1153_shallow_weighted_scale import (  # noqa: E402
    MANIFEST,
    SEGMENTS,
    SOURCE,
    compact,
    exact_certificate,
    freeze,
    object_sha,
    open_jobs,
    sha,
    sha_bytes,
    write_immutable,
)


BACKEND = ROOT / "scripts/ordinary_c1153_weighted_backend_v2.py"
_PARENTS: dict[str, bytes] = {}
_CASES: dict[str, dict[str, object]] = {}


def file_ref(path: Path) -> dict[str, object]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def domain_hashes(domain: dict[str, object]) -> dict[str, object]:
    return {
        "fixed_sha256": object_sha(domain["fixed"]),
        "forbidden_sha256": object_sha(domain["forbidden"]),
        "available_sha256": object_sha(domain["available"]),
        "uncovered_sha256": object_sha(domain["uncovered"]),
        "unit_recipe_sha256": object_sha(domain["units"]),
        "remaining_slots": domain["remaining_slots"],
    }


def solve_one(job: dict[str, object]) -> dict[str, object]:
    case = _CASES[job["target_child_id"]]
    parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
    parent_raw = _PARENTS[parent_id]
    if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
        raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
    domain = residual_domain(job, case, parent_raw)
    status, duals, elapsed = solve_highs(
        [tuple(row) for row in domain["uncovered"]],
        domain["available"],
    )
    certificate = (
        exact_certificate(duals, domain["available"], domain["remaining_slots"])
        if status == "Optimal"
        else None
    )
    if certificate is not None and not exact_check(domain, certificate):
        raise ValueError(f"{job['case_id']}: v2 exact acceptance failed")
    return {
        **job,
        "parent_cnf_sha256": sha_bytes(parent_raw),
        "domain": domain_hashes(domain),
        "lp_status": status,
        "lp_runtime_seconds": elapsed,
        "certificate": certificate,
        "status": (
            "WEIGHTED_OBSTRUCTION_PENDING_AUDIT"
            if certificate is not None
            else "OPEN_NO_CERTIFICATE"
        ),
    }


def run_chunk(payload: tuple[int, list[dict[str, object]], str]) -> dict[str, object]:
    index, jobs, folder_text = payload
    install_exact_identity_cache()
    started = time.perf_counter()
    outcomes = [solve_one(job) for job in jobs]
    raw = b"".join(compact(row) for row in outcomes)
    archive_raw = gzip.compress(raw, compresslevel=9, mtime=0)
    folder = Path(folder_text)
    archive = folder / "chunks" / f"chunk-{index:03d}.jsonl.gz"
    write_immutable(archive, archive_raw)
    receipt = {
        "schema_version": 1,
        "chunk_index": index,
        "first_case_id": jobs[0]["case_id"],
        "last_case_id": jobs[-1]["case_id"],
        "case_count": len(jobs),
        "case_ids_sha256": object_sha([row["case_id"] for row in jobs]),
        "weighted_certificate_count": sum(
            row["certificate"] is not None for row in outcomes
        ),
        "open_no_certificate_count": sum(
            row["certificate"] is None for row in outcomes
        ),
        "archive": {
            "path": str(archive.relative_to(ROOT)),
            "sha256": sha(archive),
            "bytes": len(archive_raw),
            "uncompressed_sha256": sha_bytes(raw),
        },
        "backend": file_ref(BACKEND),
        "generator": file_ref(Path(__file__)),
        "wall_seconds": time.perf_counter() - started,
    }
    receipt_path = folder / "receipts" / f"chunk-{index:03d}.json"
    write_immutable(receipt_path, compact(receipt))
    return {**receipt, "receipt": file_ref(receipt_path)}


def run_segment(number: int, workers: int) -> dict[str, object]:
    if workers < 1 or workers > 6:
        raise ValueError("v2 workers must be between one and six")
    manifest = freeze()
    segment = manifest["segments"][number]
    rows = open_jobs()[segment["start"] : segment["stop"]]
    if object_sha([row["case_id"] for row in rows]) != segment["case_ids_sha256"]:
        raise ValueError("segment membership hash mismatch")
    folder = SEGMENTS / segment["segment_id"]
    if folder.exists():
        raise ValueError(f"{segment['segment_id']}: refusing to overwrite existing segment")

    source = json.loads(SOURCE.read_text())
    global _PARENTS, _CASES
    _CASES = {row["id"]: row for row in source["target_cases"]}
    _, _PARENTS, _, _ = reconstruct_hierarchy()

    size = math.ceil(len(rows) / workers)
    chunks = [rows[start : start + size] for start in range(0, len(rows), size)]
    payloads = [(index, chunk, str(folder / "backend-v2")) for index, chunk in enumerate(chunks)]
    context = multiprocessing.get_context("fork")
    with context.Pool(processes=len(chunks)) as pool:
        chunk_receipts = pool.map(run_chunk, payloads)

    outcomes: list[dict[str, object]] = []
    for row in sorted(chunk_receipts, key=lambda item: item["chunk_index"]):
        archive = ROOT / row["archive"]["path"]
        outcomes.extend(
            json.loads(line) for line in gzip.decompress(archive.read_bytes()).splitlines()
        )
    if [row["case_id"] for row in outcomes] != [row["case_id"] for row in rows]:
        raise ValueError("deterministic v2 merge changed formula membership or order")

    raw = b"".join(compact(row) for row in outcomes)
    archive_raw = gzip.compress(raw, compresslevel=9, mtime=0)
    archive = folder / "outcomes.jsonl.gz"
    write_immutable(archive, archive_raw)
    index = {
        "schema_version": 1,
        "segment_id": segment["segment_id"],
        "manifest_sha256": sha(MANIFEST),
        "generator": file_ref(Path(__file__)),
        "backend": file_ref(BACKEND),
        "worker_count": len(chunks),
        "case_ids_sha256": object_sha([row["case_id"] for row in outcomes]),
        "chunks": [
            {
                "chunk_index": row["chunk_index"],
                "case_count": row["case_count"],
                "case_ids_sha256": row["case_ids_sha256"],
                "receipt": row["receipt"],
                "archive": row["archive"],
            }
            for row in sorted(chunk_receipts, key=lambda item: item["chunk_index"])
        ],
        "merged_archive": file_ref(archive),
    }
    write_immutable(folder / "backend-v2/index.json", compact(index))

    certified = [row for row in outcomes if row["certificate"] is not None]
    runtimes = [row["lp_runtime_seconds"] for row in outcomes]
    margins = [row["certificate"]["margin"] for row in certified]
    projected = math.ceil(
        len(archive_raw) * manifest["open_formula_count"] / len(rows)
    )
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
        "backend_v2": {
            "generator": file_ref(Path(__file__)),
            "backend": file_ref(BACKEND),
            "index": file_ref(folder / "backend-v2/index.json"),
            "worker_count": len(chunks),
        },
        "claim_limit": "Pending unchanged independent exact domain and arithmetic audit.",
    }
    write_immutable(folder / "summary.json", compact(summary))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("run",))
    parser.add_argument("--segment", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    args = parser.parse_args()
    report = run_segment(args.segment, args.workers)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "segment_id",
                    "selected",
                    "weighted_certificate_count",
                    "open_no_certificate_count",
                    "median_runtime_seconds",
                    "projected_complete_compressed_bytes",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )
