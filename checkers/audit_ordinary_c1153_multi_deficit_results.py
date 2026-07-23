#!/usr/bin/env python3
"""Independently reconstruct and replay the exact 24-cube discriminator."""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
GATE = BASE / "multi-deficit-propagation-gate-v1"
MANIFEST = GATE / "manifest.json"
STRUCTURAL_AUDIT = GATE / "independent-audit.json"
PROTOCOL = GATE / "discriminator-5s/protocol.json"
SUMMARY = GATE / "discriminator-5s/summary.json"
OUTPUT = GATE / "discriminator-5s/independent-audit.json"
CHECKER = ROOT / "toolchains/drat-trim/drat-trim"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from audit_ordinary_c1153_multi_deficit_gate import (  # noqa: E402
    added_second_literals,
    close_under_semantics,
    cnf_primary_assignments,
    independent_orbits,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def exact_cnf(parent_raw: bytes, units: list[int]) -> bytes:
    header, body = parent_raw.split(b"\n", 1)
    fields = header.decode("ascii").split()
    return (
        f"p cnf {fields[2]} {int(fields[3]) + len(units)}\n".encode("ascii")
        + body
        + b"".join(f"{literal} 0\n".encode("ascii") for literal in units)
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


def derive_units(job: dict[str, object], case: dict[str, object], parent_raw: bytes) -> tuple[list[int], str]:
    parent_fixed, parent_forbidden = cnf_primary_assignments(parent_raw)
    inherited = [*case["inherited_units"], *added_second_literals(case, job["second_index"])]
    fixed = parent_fixed | {value for value in inherited if value > 0}
    forbidden = parent_forbidden | {-value for value in inherited if value < 0}
    distinguished = (
        tuple(case["first_selected_triple"]),
        tuple(case["selected_second_uncovered_triple"]),
    )
    for depth, expected_index in enumerate(job["cube_path"]):
        status, fixed, forbidden, detail = close_under_semantics(fixed, forbidden)
        if status != "OPEN":
            raise ValueError(f"{job['case_id']}: independent path became {status} at depth {depth}")
        triple = min(detail["missing"], key=lambda value: (len(detail["options"][value]), value))
        orbits = independent_orbits(
            set(detail["options"][triple]), fixed, forbidden, (*distinguished, triple)
        )
        if not 0 <= expected_index < len(orbits):
            raise ValueError(f"{job['case_id']}: independent orbit index mismatch")
        earlier = {value for orbit in orbits[:expected_index] for value in orbit}
        fixed.add(orbits[expected_index][0])
        forbidden.update(earlier)
        distinguished = (*distinguished, triple)
    status, fixed, forbidden, _ = close_under_semantics(fixed, forbidden)
    if status != "OPEN":
        raise ValueError(f"{job['case_id']}: independent terminal is {status}, not frontier")
    units = [*sorted(fixed - parent_fixed), *[-value for value in sorted(forbidden - parent_forbidden)]]
    state_sha = object_sha({
        "fixed": sorted(fixed),
        "forbidden": sorted(forbidden),
        "distinguished": [list(value) for value in distinguished],
    })
    return units, state_sha


def audit() -> dict[str, object]:
    source = json.loads(SOURCE.read_text())
    manifest = json.loads(MANIFEST.read_text())
    structural = json.loads(STRUCTURAL_AUDIT.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    summary = json.loads(SUMMARY.read_text())
    if structural["status"] != "VALID" or structural["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("structural gate binding mismatch")
    if protocol["manifest"]["sha256"] != sha(MANIFEST) or protocol["audit"]["sha256"] != sha(STRUCTURAL_AUDIT):
        raise ValueError("protocol source binding mismatch")
    if protocol["sample_size"] != 24 or summary["completed"] != 24:
        raise ValueError("the exact 24-case stop condition was not met")
    if summary["protocol"]["sha256"] != sha(PROTOCOL):
        raise ValueError("summary protocol binding mismatch")
    jobs = {row["case_id"]: row for row in protocol["sample"]}
    results = {row["case_id"]: row for row in summary["outcomes"]}
    if len(jobs) != 24 or set(jobs) != set(results):
        raise ValueError("protocol/result membership mismatch")
    formulas = {row["leaf_id"]: row for row in manifest["formulas"]}
    for formula_id, formula in formulas.items():
        frontier = sorted(tuple(row["path"]) for row in formula["terminal_partition"] if row["kind"] == "frontier")
        expected = {frontier[0], frontier[-1]}
        observed = {tuple(row["cube_path"]) for row in jobs.values() if row["formula_id"] == formula_id}
        if observed != expected:
            raise ValueError(f"{formula_id}: first/last cube selection mismatch")
    cases = {case["id"]: case for case in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    replay_seconds = []
    verified = 0
    for case_id in sorted(jobs):
        job, result = jobs[case_id], results[case_id]
        if any(result[key] != value for key, value in job.items()):
            raise ValueError(f"{case_id}: immutable job fields changed")
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{case_id}: parent reconstruction mismatch")
        units, state_sha = derive_units(job, case, parent_raw)
        if object_sha(units) != result["unit_recipe_sha256"]:
            raise ValueError(f"{case_id}: exact unit recipe mismatch")
        if state_sha != result["terminal_state_sha256"]:
            raise ValueError(f"{case_id}: terminal residual state mismatch")
        raw = exact_cnf(parent_raw, units)
        if sha_bytes(raw) != result["exact_cnf_sha256"]:
            raise ValueError(f"{case_id}: exact CNF hash mismatch")
        if result["status"] != "UNSAT_VERIFIED_BY_RUNNER":
            continue
        proof_gz = ROOT / result["proof"]["path"]
        if sha(proof_gz) != result["proof"]["sha256"]:
            raise ValueError(f"{case_id}: compressed proof hash mismatch")
        with tempfile.TemporaryDirectory(prefix="audit-multi-deficit-") as temporary:
            directory = Path(temporary)
            cnf, proof = directory / "instance.cnf", directory / "proof.drat"
            cnf.write_bytes(raw)
            with gzip.open(proof_gz, "rb") as source_proof, proof.open("wb") as target:
                while chunk := source_proof.read(1024 * 1024):
                    target.write(chunk)
            if sha(proof) != result["proof"]["uncompressed_sha256"]:
                raise ValueError(f"{case_id}: uncompressed proof hash mismatch")
            started = time.monotonic()
            replay = subprocess.run([str(CHECKER), str(cnf), str(proof)], capture_output=True, text=True, timeout=600)
            replay_seconds.append(time.monotonic() - started)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                raise ValueError(f"{case_id}: independent external replay failed")
        verified += 1
    counts = Counter(row["status"] for row in results.values())
    category_verified = {
        category: sum(
            row["sample_category"] == category and row["status"] == "UNSAT_VERIFIED_BY_RUNNER"
            for row in results.values()
        )
        for category in ("rank_zero", "q3_nonzero", "q4_nonzero")
    }
    material = verified >= 8 and all(value >= 1 for value in category_verified.values())
    report = {
        "schema_version": 1,
        "status": "VALID",
        "protocol_sha256": sha(PROTOCOL),
        "summary_sha256": sha(SUMMARY),
        "sample_count": 24,
        "counts": dict(sorted(counts.items())),
        "independently_replayed_unsat": verified,
        "verified_unsat_by_sample_category": category_verified,
        "material_signal_passed": material,
        "solver_elapsed_seconds": tails([row["solver_elapsed_seconds"] for row in results.values()]),
        "independent_replay_seconds": tails(replay_seconds),
        "compressed_proof_bytes": tails([
            row["proof"]["compressed_bytes"] for row in results.values()
            if row["status"] == "UNSAT_VERIFIED_BY_RUNNER"
        ]),
        "complete_formula_count": 0,
        "claim_limit": "Exact 24-cube discriminator only. No formula, fifth leaf, fourth parent, ordinary classification, or C(12,6,4) theorem is closed by this sample.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
