#!/usr/bin/env python3
"""Independently reconstruct and replay the second-live-triple sample."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
MANIFEST = BASE / "manifest.json"
STRUCTURAL_AUDIT = BASE / "independent-audit.json"
PROTOCOL = BASE / "discriminator-5s/protocol.json"
SUMMARY = BASE / "discriminator-5s/summary.json"
OUTPUT = BASE / "discriminator-5s/independent-audit.json"
CHECKER = ROOT / "toolchains/drat-trim/drat-trim"
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def unit_sha(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + "\n").encode()).hexdigest()


def second_units(case: dict[str, object], index: int) -> list[int]:
    return [
        *[-value for orbit in case["second_covering_block_orbits"][:index] for value in orbit["member_variables"]],
        case["second_covering_block_orbits"][index]["canonical_variable"],
    ]


def exact_cnf(parent_raw: bytes, units: list[int]) -> bytes:
    header, body = parent_raw.split(b"\n", 1)
    fields = header.decode("ascii").split()
    return (
        f"p cnf {fields[2]} {int(fields[3]) + len(units)}\n".encode("ascii")
        + body
        + b"".join(f"{value} 0\n".encode("ascii") for value in units)
    )


def tails(values: list[float | int]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {}
    at = lambda fraction: ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p50": at(0.50),
        "p90": at(0.90),
        "p95": at(0.95),
        "max": ordered[-1],
        "total": sum(ordered),
    }


def audit() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    structural = json.loads(STRUCTURAL_AUDIT.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    summary = json.loads(SUMMARY.read_text())
    if structural["status"] != "VALID" or structural["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("structural audit binding mismatch")
    if protocol["manifest"]["sha256"] != sha(MANIFEST) or protocol["audit"]["sha256"] != sha(STRUCTURAL_AUDIT):
        raise ValueError("protocol source binding mismatch")
    if summary["protocol"]["sha256"] != sha(PROTOCOL):
        raise ValueError("summary protocol binding mismatch")
    jobs = {row["leaf_id"]: row for row in protocol["sample"]}
    results = {row["leaf_id"]: row for row in summary["outcomes"]}
    if len(jobs) != protocol["sample_size"] or set(jobs) != set(results):
        raise ValueError("sample/result membership mismatch")
    if len(jobs) != 48:
        raise ValueError("frozen sample size changed")
    categories = Counter((row["root_class"], row["sample_category"], row["second_position"]) for row in jobs.values())
    expected = {
        (root, category, position): quota
        for root in ("intersection-3", "intersection-4")
        for category, quota in (("rank_zero", 6), ("q3_nonzero", 3), ("q4_nonzero", 3))
        for position in ("first_second_orbit", "last_second_orbit")
    }
    if categories != expected:
        raise ValueError("frozen stratum quotas mismatch")
    cases = {case["id"]: case for case in manifest["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    verified = 0
    replay_seconds: list[float] = []
    for leaf_id in sorted(jobs):
        job, result = jobs[leaf_id], results[leaf_id]
        if any(result[key] != value for key, value in job.items()):
            raise ValueError(f"{leaf_id}: frozen job mismatch")
        case = cases[job["target_child_id"]]
        index = job["second_index"]
        if not 0 <= index < case["second_partition_children"]:
            raise ValueError(f"{leaf_id}: second index outside audited partition")
        added = second_units(case, index)
        if unit_sha(added) != result["second_unit_sha256"]:
            raise ValueError(f"{leaf_id}: second unit recipe mismatch")
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{leaf_id}: reconstructed parent mismatch")
        raw = exact_cnf(parent_raw, [*case["inherited_units"], *added])
        if sha_bytes(raw) != result["exact_cnf_sha256"]:
            raise ValueError(f"{leaf_id}: exact CNF hash mismatch")
        if result["status"] != "UNSAT_VERIFIED_BY_RUNNER":
            continue
        proof_gz = ROOT / result["proof"]["path"]
        if sha(proof_gz) != result["proof"]["sha256"]:
            raise ValueError(f"{leaf_id}: compressed proof hash mismatch")
        with tempfile.TemporaryDirectory(prefix="audit-second-live-") as temporary:
            directory = Path(temporary)
            cnf, proof = directory / "instance.cnf", directory / "proof.drat"
            cnf.write_bytes(raw)
            with gzip.open(proof_gz, "rb") as source, proof.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            if sha(proof) != result["proof"]["uncompressed_sha256"]:
                raise ValueError(f"{leaf_id}: proof content hash mismatch")
            started = time.monotonic()
            replay = subprocess.run(
                [str(CHECKER), str(cnf), str(proof)],
                capture_output=True, text=True, timeout=600,
            )
            replay_seconds.append(time.monotonic() - started)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                raise ValueError(f"{leaf_id}: external replay failed")
        verified += 1
    counts = Counter(row["status"] for row in results.values())
    by_dimension = {}
    for field in ("second_position", "sample_category", "root_class", "rank_band", "branch_count_quantile", "stabilizer_tier"):
        by_dimension[field] = {
            value: dict(Counter(row["status"] for row in results.values() if row[field] == value))
            for value in sorted({row[field] for row in results.values()})
        }
    complete_targets = []
    by_target: dict[str, list[dict[str, object]]] = {}
    for result in results.values():
        by_target.setdefault(result["target_child_id"], []).append(result)
    for target_id, rows in by_target.items():
        if (
            len(rows) == cases[target_id]["second_partition_children"]
            and all(row["status"] == "UNSAT_VERIFIED_BY_RUNNER" for row in rows)
        ):
            complete_targets.append(target_id)
    report = {
        "schema_version": 1,
        "status": "VALID",
        "protocol_sha256": sha(PROTOCOL),
        "summary_sha256": sha(SUMMARY),
        "sample_count": len(results),
        "counts": dict(counts),
        "counts_by_dimension": by_dimension,
        "independently_replayed_unsat": verified,
        "complete_target_children": sorted(complete_targets),
        "complete_target_child_count": len(complete_targets),
        "solver_elapsed_seconds": tails([row["solver_elapsed_seconds"] for row in results.values()]),
        "independent_replay_seconds": tails(replay_seconds),
        "compressed_proof_bytes": tails([
            row["proof"]["compressed_bytes"] for row in results.values()
            if row["status"] == "UNSAT_VERIFIED_BY_RUNNER"
        ]),
        "uncompressed_proof_bytes": tails([
            row["proof"]["uncompressed_bytes"] for row in results.values()
            if row["status"] == "UNSAT_VERIFIED_BY_RUNNER"
        ]),
        "claim_limit": "Exact 48-child sample only. No unsampled child or ancestor closes from this audit.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
