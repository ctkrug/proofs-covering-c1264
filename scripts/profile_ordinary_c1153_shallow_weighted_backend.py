#!/usr/bin/env python3
"""Profile the frozen shallow-weighted backend on a copied completed segment.

This is performance research only. It never writes into the theorem-evidence
segment tree and accepts a proposed certificate only through an exact local
check plus comparison with the immutable completed segment.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import multiprocessing
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
SCALE = BASE / "shallow-weighted-scale-v1"
REFERENCE = SCALE / "segments/shallow-weighted-scale-002/outcomes.jsonl.gz"
OUTPUT = SCALE / "performance-engineering-v1"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from run_ordinary_c1153_ilp_forced_gate import residual_domain, solve_cover  # noqa: E402
from run_ordinary_c1153_shallow_weighted_scale import (  # noqa: E402
    LP_SECONDS,
    exact_certificate,
    object_sha,
    open_jobs,
    sha_bytes,
)
from ordinary_c1153_weighted_backend_v2 import (  # noqa: E402
    exact_check as backend_exact_check,
    install_exact_identity_cache as backend_install_exact_identity_cache,
    solve_highs as backend_solve_highs,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def domain_hashes(domain: dict[str, object]) -> dict[str, object]:
    return {
        "fixed_sha256": object_sha(domain["fixed"]),
        "forbidden_sha256": object_sha(domain["forbidden"]),
        "available_sha256": object_sha(domain["available"]),
        "uncovered_sha256": object_sha(domain["uncovered"]),
        "unit_recipe_sha256": object_sha(domain["units"]),
        "remaining_slots": domain["remaining_slots"],
    }


def quantiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum": ordered[0],
        "q1": ordered[len(ordered) // 4],
        "median": statistics.median(ordered),
        "q3": ordered[(3 * len(ordered)) // 4],
        "maximum": ordered[-1],
    }


def run_baseline() -> dict[str, object]:
    reference_raw = gzip.decompress(REFERENCE.read_bytes())
    references = [json.loads(line) for line in reference_raw.splitlines()]
    jobs = open_jobs()[4096:6144]
    if [row["case_id"] for row in references] != [row["case_id"] for row in jobs]:
        raise ValueError("copied benchmark membership differs from immutable segment 002")
    source_cases = {row["id"]: row for row in json.loads(SOURCE.read_text())["target_cases"]}

    stages = {
        "hierarchy_reconstruction": 0.0,
        "residual_domain_construction": 0.0,
        "lp_certificate_proposal": 0.0,
        "certificate_normalization": 0.0,
        "independent_exact_verification": 0.0,
        "serialization_compression_write": 0.0,
    }
    start = time.perf_counter()
    before = time.perf_counter()
    _, parents, _, _ = reconstruct_hierarchy()
    stages["hierarchy_reconstruction"] = time.perf_counter() - before

    outcomes = []
    proposal_times: list[float] = []
    with tempfile.TemporaryDirectory(prefix="c1264-perf-baseline-") as temporary:
        temp = Path(temporary)
        for index, (job, reference) in enumerate(zip(jobs, references)):
            case = source_cases[job["target_child_id"]]
            parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
            parent_raw = parents[parent_id]
            if sha_bytes(parent_raw) != reference["parent_cnf_sha256"]:
                raise ValueError(f"{job['case_id']}: parent CNF mismatch")

            before = time.perf_counter()
            domain = residual_domain(job, case, parent_raw)
            stages["residual_domain_construction"] += time.perf_counter() - before
            hashes = domain_hashes(domain)
            if hashes != reference["domain"]:
                raise ValueError(f"{job['case_id']}: residual-domain hash mismatch")

            before = time.perf_counter()
            report = solve_cover(
                [tuple(row) for row in domain["uncovered"]],
                domain["available"],
                LP_SECONDS,
                temp / f"{index:04d}.log",
                continuous=True,
            )
            elapsed = time.perf_counter() - before
            stages["lp_certificate_proposal"] += elapsed
            proposal_times.append(elapsed)

            before = time.perf_counter()
            cert = (
                exact_certificate(report["duals"], domain["available"], domain["remaining_slots"])
                if report["status"] == "Optimal"
                else None
            )
            stages["certificate_normalization"] += time.perf_counter() - before

            before = time.perf_counter()
            verified = backend_exact_check(domain, cert)
            stages["independent_exact_verification"] += time.perf_counter() - before
            terminal = verified
            if terminal != (reference["certificate"] is not None):
                raise ValueError(f"{job['case_id']}: terminal verdict differs from immutable result")
            outcomes.append(
                {
                    "case_id": job["case_id"],
                    "domain": hashes,
                    "terminal": terminal,
                    "certificate": cert,
                }
            )

        before = time.perf_counter()
        raw = b"".join(
            (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for row in outcomes
        )
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        scratch = temp / "profile-outcomes.jsonl.gz"
        scratch.write_bytes(compressed)
        if scratch.read_bytes() != compressed:
            raise ValueError("scratch artifact round-trip mismatch")
        stages["serialization_compression_write"] = time.perf_counter() - before

    wall = time.perf_counter() - start
    usage = resource.getrusage(resource.RUSAGE_SELF)
    measured = sum(stages.values())
    report = {
        "schema_version": 1,
        "status": "VALID_BASELINE_PROFILE",
        "purpose": "Performance-only replay on a copied completed segment; no mathematical ledger effect.",
        "benchmark": {
            "segment_id": "shallow-weighted-scale-002",
            "formula_count": len(jobs),
            "case_ids_sha256": object_sha([row["case_id"] for row in jobs]),
            "reference_archive": {
                "path": str(REFERENCE.relative_to(ROOT)),
                "sha256": sha(REFERENCE),
            },
            "git_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "command": "nice -n 10 /private/tmp/c1264-pulp270/bin/python scripts/profile_ordinary_c1153_shallow_weighted_backend.py baseline",
            "python": sys.version,
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "results": {
            "terminal": sum(row["terminal"] for row in outcomes),
            "nonterminal": sum(not row["terminal"] for row in outcomes),
            "domain_hash_agreement": len(outcomes),
            "verdict_agreement": len(outcomes),
            "exact_checker_acceptances": sum(row["terminal"] for row in outcomes),
            "stage_wall_seconds": stages,
            "unattributed_wall_seconds": wall - measured,
            "total_wall_seconds": wall,
            "total_cpu_seconds": usage.ru_utime + usage.ru_stime,
            "maximum_resident_kib": usage.ru_maxrss,
            "proposal_wall_seconds_distribution": quantiles(proposal_times),
            "scratch_uncompressed_bytes": len(raw),
            "scratch_compressed_bytes": len(compressed),
        },
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "baseline-profile.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["results"], indent=2, sort_keys=True))
    return report


_PARENTS: dict[str, bytes] = {}
_CASES: dict[str, dict[str, object]] = {}
_REFERENCES: dict[str, dict[str, object]] = {}


def optimized_one(job: dict[str, object]) -> tuple[dict[str, object], dict[str, float]]:
    stages = {
        "residual_domain_construction": 0.0,
        "lp_certificate_proposal": 0.0,
        "certificate_normalization": 0.0,
        "independent_exact_verification": 0.0,
    }
    reference = _REFERENCES[job["case_id"]]
    case = _CASES[job["target_child_id"]]
    parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
    parent_raw = _PARENTS[parent_id]
    if sha_bytes(parent_raw) != reference["parent_cnf_sha256"]:
        raise ValueError(f"{job['case_id']}: parent CNF mismatch")
    before = time.perf_counter()
    domain = residual_domain(job, case, parent_raw)
    stages["residual_domain_construction"] = time.perf_counter() - before
    hashes = domain_hashes(domain)
    if hashes != reference["domain"]:
        raise ValueError(f"{job['case_id']}: residual-domain hash mismatch")
    status, duals, elapsed = backend_solve_highs(
        [tuple(row) for row in domain["uncovered"]], domain["available"]
    )
    stages["lp_certificate_proposal"] = elapsed
    before = time.perf_counter()
    cert = exact_certificate(duals, domain["available"], domain["remaining_slots"]) if status == "Optimal" else None
    stages["certificate_normalization"] = time.perf_counter() - before
    before = time.perf_counter()
    verified = backend_exact_check(domain, cert)
    stages["independent_exact_verification"] = time.perf_counter() - before
    reference_terminal = reference["certificate"] is not None
    if reference_terminal and not verified:
        raise ValueError(f"{job['case_id']}: terminal verdict differs from immutable result")
    # The equivalence benchmark deliberately does not promote any additional
    # terminal result that the copied completed segment left open. A future
    # workload may accept such a certificate after review.
    if not reference_terminal:
        cert = None
        verified = False
    outcome = {
        "case_id": job["case_id"],
        "parent_cnf_sha256": reference["parent_cnf_sha256"],
        "domain": hashes,
        "residual_matrix_identity_sha256": object_sha(
            {
                "available": domain["available"],
                "uncovered": domain["uncovered"],
                "remaining_slots": domain["remaining_slots"],
            }
        ),
        "proposal_engine": "highspy-1.11.0",
        "terminal": verified,
        "certificate": cert,
    }
    return outcome, stages


def worker_chunk(payload: tuple[int, list[dict[str, object]], str]) -> dict[str, object]:
    chunk_index, jobs, output_root = payload
    backend_install_exact_identity_cache()
    stages = {
        "residual_domain_construction": 0.0,
        "lp_certificate_proposal": 0.0,
        "certificate_normalization": 0.0,
        "independent_exact_verification": 0.0,
        "serialization_compression_write": 0.0,
    }
    outcomes = []
    for job in jobs:
        outcome, measured = optimized_one(job)
        outcomes.append(outcome)
        for key, value in measured.items():
            stages[key] += value
    before = time.perf_counter()
    raw = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in outcomes
    )
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    folder = Path(output_root) / "chunks"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"chunk-{chunk_index:03d}.jsonl.gz"
    if path.exists() and path.read_bytes() != compressed:
        raise ValueError(f"refusing incompatible benchmark chunk {path}")
    path.write_bytes(compressed)
    stages["serialization_compression_write"] = time.perf_counter() - before
    return {
        "chunk_index": chunk_index,
        "first_case_id": jobs[0]["case_id"],
        "last_case_id": jobs[-1]["case_id"],
        "count": len(jobs),
        "terminal": sum(row["terminal"] for row in outcomes),
        "archive_sha256": sha(path),
        "archive_bytes": path.stat().st_size,
        "stages": stages,
    }


def run_optimized(workers: int) -> dict[str, object]:
    if workers not in (1, 2, 4, 6):
        raise ValueError("worker count must be 1, 2, 4, or 6")
    reference_raw = gzip.decompress(REFERENCE.read_bytes())
    references = [json.loads(line) for line in reference_raw.splitlines()]
    jobs = open_jobs()[4096:6144]
    if [row["case_id"] for row in references] != [row["case_id"] for row in jobs]:
        raise ValueError("copied benchmark membership differs from immutable segment 002")
    source_cases = {row["id"]: row for row in json.loads(SOURCE.read_text())["target_cases"]}

    started = time.perf_counter()
    before = time.perf_counter()
    _, parents, _, _ = reconstruct_hierarchy()
    hierarchy_seconds = time.perf_counter() - before
    global _PARENTS, _CASES, _REFERENCES
    _PARENTS = parents
    _CASES = source_cases
    _REFERENCES = {row["case_id"]: row for row in references}

    size = (len(jobs) + workers - 1) // workers
    chunks = [jobs[start:start + size] for start in range(0, len(jobs), size)]
    run_root = OUTPUT / f"optimized-workers-{workers}"
    payloads = [(index, chunk, str(run_root)) for index, chunk in enumerate(chunks)]
    before_cpu = resource.getrusage(resource.RUSAGE_SELF)
    child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    context = multiprocessing.get_context("fork")
    with context.Pool(processes=workers) as pool:
        chunk_reports = pool.map(worker_chunk, payloads)
    child_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    after_cpu = resource.getrusage(resource.RUSAGE_SELF)

    before = time.perf_counter()
    merged = []
    for report in sorted(chunk_reports, key=lambda row: row["chunk_index"]):
        path = run_root / "chunks" / f"chunk-{report['chunk_index']:03d}.jsonl.gz"
        merged.extend(json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines())
    if [row["case_id"] for row in merged] != [row["case_id"] for row in jobs]:
        raise ValueError("deterministic chunk merge changed formula coverage/order")
    for row in merged:
        if not row["terminal"] == (_REFERENCES[row["case_id"]]["certificate"] is not None):
            raise ValueError(f"{row['case_id']}: merged verdict mismatch")
    aggregate = {
        "case_ids_sha256": object_sha([row["case_id"] for row in merged]),
        "terminal": sum(row["terminal"] for row in merged),
        "nonterminal": sum(not row["terminal"] for row in merged),
        "unique_residual_matrix_count": len(
            {row["residual_matrix_identity_sha256"] for row in merged}
        ),
        "chunk_rows": [
            {
                "chunk_index": row["chunk_index"],
                "count": row["count"],
                "archive_sha256": row["archive_sha256"],
                "archive_bytes": row["archive_bytes"],
            }
            for row in sorted(chunk_reports, key=lambda row: row["chunk_index"])
        ],
    }
    aggregate_raw = (json.dumps(aggregate, indent=2, sort_keys=True) + "\n").encode()
    aggregate_path = run_root / "aggregate-index.json"
    if aggregate_path.exists() and aggregate_path.read_bytes() != aggregate_raw:
        raise ValueError("refusing incompatible aggregate benchmark index")
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_bytes(aggregate_raw)
    aggregation_seconds = time.perf_counter() - before
    wall = time.perf_counter() - started
    stage_totals = {
        key: sum(row["stages"][key] for row in chunk_reports)
        for key in chunk_reports[0]["stages"]
    }
    self_cpu = (after_cpu.ru_utime + after_cpu.ru_stime) - (before_cpu.ru_utime + before_cpu.ru_stime)
    child_cpu = (child_after.ru_utime + child_after.ru_stime) - (child_before.ru_utime + child_before.ru_stime)
    report = {
        "schema_version": 1,
        "status": "VALID_OPTIMIZED_BENCHMARK",
        "purpose": "Performance-only run on copied segment 002; no theorem-evidence or ledger effect.",
        "benchmark": {
            "segment_id": "shallow-weighted-scale-002",
            "formula_count": len(jobs),
            "case_ids_sha256": object_sha([row["case_id"] for row in jobs]),
            "reference_archive_sha256": sha(REFERENCE),
            "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "python": sys.version,
            "platform": platform.platform(),
            "workers": workers,
            "proposal_engine": "highspy==1.11.0",
            "command": f"nice -n 10 /private/tmp/c1264-performance-py312/bin/python scripts/profile_ordinary_c1153_shallow_weighted_backend.py optimized --workers {workers}",
        },
        "results": {
            "terminal": aggregate["terminal"],
            "nonterminal": aggregate["nonterminal"],
            "domain_hash_agreement": len(merged),
            "verdict_agreement": len(merged),
            "exact_checker_acceptances": aggregate["terminal"],
            "hierarchy_reconstruction_wall_seconds": hierarchy_seconds,
            "worker_stage_cpu_wall_seconds": stage_totals,
            "deterministic_aggregation_wall_seconds": aggregation_seconds,
            "total_wall_seconds": wall,
            "total_cpu_seconds": self_cpu + child_cpu,
            "maximum_child_resident_kib": child_after.ru_maxrss,
            "chunk_count": len(chunk_reports),
            "compressed_bytes": sum(row["archive_bytes"] for row in chunk_reports),
            "aggregate_index_bytes": len(aggregate_raw),
        },
        "chunks": chunk_reports,
    }
    report_path = run_root / "benchmark.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["results"], indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("baseline", "optimized"))
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    run_baseline() if args.mode == "baseline" else run_optimized(args.workers)
