#!/usr/bin/env python3
"""Independent audit of the six-case ILP/PB forced-substructure gate."""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
GATE = BASE / "multi-deficit-propagation-gate-v1"
PROTOCOL = GATE / "ilp-forced-gate-v1/protocol.json"
SUMMARY = GATE / "ilp-forced-gate-v1/summary.json"
OUTPUT = GATE / "ilp-forced-gate-v1/independent-audit.json"
DRAT_TRIM = ROOT / "toolchains/drat-trim/drat-trim"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)
ALL_TRIPLES = tuple(itertools.combinations(range(1, 12), 3))
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from audit_ordinary_c1153_multi_deficit_results import derive_units, exact_cnf  # noqa: E402
from audit_ordinary_c1153_multi_deficit_gate import cnf_primary_assignments  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def residual_domain(job: dict[str, object], case: dict[str, object], parent_raw: bytes) -> dict[str, object]:
    units, state_sha = derive_units(job, case, parent_raw)
    parent_fixed, parent_forbidden = cnf_primary_assignments(parent_raw)
    fixed = parent_fixed | {value for value in units if value > 0}
    forbidden = parent_forbidden | {-value for value in units if value < 0}
    covered = set().union(*(BLOCK_TRIPLES[value - 1] for value in fixed))
    uncovered = [triple for triple in ALL_TRIPLES if triple not in covered]
    available = sorted(set(range(1, len(BLOCKS) + 1)) - fixed - forbidden)
    return {
        "units": units,
        "state_sha": state_sha,
        "fixed": sorted(fixed),
        "forbidden": sorted(forbidden),
        "available": available,
        "uncovered": uncovered,
        "remaining_slots": 20 - len(fixed),
    }


def audit_weighted(
    reference: dict[str, object],
    uncovered: list[tuple[int, ...]],
    available: list[int],
    slots: int,
) -> None:
    path = ROOT / reference["path"]
    if sha(path) != reference["sha256"]:
        raise ValueError("weighted certificate file hash mismatch")
    certificate = json.loads(path.read_text())
    if certificate["denominator"] <= 0 or certificate["remaining_slots"] != slots:
        raise ValueError("weighted certificate budget mismatch")
    uncovered_set = set(uncovered)
    weights = {}
    for row in certificate["weighted_triples"]:
        triple = tuple(row["triple"])
        numerator = row["numerator"]
        if triple not in uncovered_set or numerator <= 0 or triple in weights:
            raise ValueError("invalid weighted triple")
        weights[triple] = numerator
    total = sum(weights.values())
    if total != certificate["total_numerator"] or total <= slots * certificate["denominator"]:
        raise ValueError("weighted objective does not exceed block budget")
    loads = [
        sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
        for value in available
    ]
    maximum = max(loads, default=0)
    if maximum != certificate["maximum_eligible_block_load"] or maximum > certificate["denominator"]:
        raise ValueError("eligible block violates weighted capacity")


def tails(values: list[float | int]) -> dict[str, float | int]:
    values = sorted(values)
    if not values:
        return {}
    at = lambda q: values[min(len(values) - 1, int(q * (len(values) - 1)))]
    return {
        "count": len(values),
        "min": values[0],
        "p50": at(0.5),
        "p90": at(0.9),
        "max": values[-1],
        "total": sum(values),
    }


def audit() -> dict[str, object]:
    protocol = json.loads(PROTOCOL.read_text())
    summary = json.loads(SUMMARY.read_text())
    if protocol["case_count"] != 6 or summary["completed"] != 6:
        raise ValueError("exact six-case gate did not complete")
    if summary["protocol"]["sha256"] != sha(PROTOCOL):
        raise ValueError("summary protocol binding mismatch")
    jobs = {row["case_id"]: row for row in protocol["cases"]}
    results = {row["case_id"]: row for row in summary["outcomes"]}
    if len(jobs) != 6 or set(jobs) != set(results):
        raise ValueError("case membership mismatch")
    cells = {(row["root_class"], row["sample_category"]) for row in jobs.values()}
    if cells != {
        (root, category)
        for root in ("intersection-3", "intersection-4")
        for category in ("rank_zero", "q3_nonzero", "q4_nonzero")
    }:
        raise ValueError("root/category cells are not exhaustive")
    source = json.loads(SOURCE.read_text())
    cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    weighted_count = 0
    replay_count = 0
    replay_seconds = []
    sat_count = 0
    for case_id in sorted(jobs):
        job, result = jobs[case_id], results[case_id]
        if any(result[key] != value for key, value in job.items()):
            raise ValueError(f"{case_id}: immutable case fields changed")
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != result["parent_cnf_sha256"]:
            raise ValueError(f"{case_id}: parent hash mismatch")
        domain = residual_domain(job, case, parent_raw)
        recorded = result["domain"]
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
        if result["base_weighted_certificate"] is not None:
            audit_weighted(
                result["base_weighted_certificate"],
                domain["uncovered"],
                domain["available"],
                domain["remaining_slots"],
            )
            weighted_count += 1
        seen_probes = set()
        for probe in result["probes"]:
            key = (probe["direction"], probe["variable"])
            if key in seen_probes:
                raise ValueError(f"{case_id}: duplicate probe")
            seen_probes.add(key)
            variable = probe["variable"]
            if variable not in domain["available"]:
                raise ValueError(f"{case_id}: probe variable outside residual domain")
            if probe["direction"] == "ASSUME_FALSE":
                child_uncovered = domain["uncovered"]
                child_available = [value for value in domain["available"] if value != variable]
                child_slots = domain["remaining_slots"]
                assumption = -variable
            elif probe["direction"] == "ASSUME_TRUE":
                child_uncovered = [
                    triple for triple in domain["uncovered"]
                    if triple not in BLOCK_TRIPLES[variable - 1]
                ]
                child_available = [value for value in domain["available"] if value != variable]
                child_slots = domain["remaining_slots"] - 1
                assumption = variable
            else:
                raise ValueError(f"{case_id}: unknown probe direction")
            if probe["assumption"] != assumption:
                raise ValueError(f"{case_id}: assumption mismatch")
            if probe["weighted_certificate"] is not None:
                audit_weighted(probe["weighted_certificate"], child_uncovered, child_available, child_slots)
                weighted_count += 1
            proof_result = probe["exact_cnf_validation"]
            if proof_result is None:
                continue
            if proof_result["assumption"] != assumption:
                raise ValueError(f"{case_id}: proof assumption mismatch")
            raw = exact_cnf(parent_raw, [*domain["units"], assumption])
            if sha_bytes(raw) != proof_result["exact_cnf_sha256"]:
                raise ValueError(f"{case_id}: assumption CNF mismatch")
            if proof_result["status"] == "SAT_COUNTEREXAMPLE":
                sat_count += 1
                raise ValueError(f"{case_id}: SAT requires immediate witness audit")
            if proof_result["status"] != "UNSAT_VERIFIED_BY_RUNNER":
                continue
            proof_gz = ROOT / proof_result["proof"]["path"]
            if sha(proof_gz) != proof_result["proof"]["sha256"]:
                raise ValueError(f"{case_id}: compressed proof hash mismatch")
            with tempfile.TemporaryDirectory(prefix="audit-ilp-forced-") as temporary:
                folder = Path(temporary)
                cnf, proof = folder / "instance.cnf", folder / "proof.drat"
                cnf.write_bytes(raw)
                with gzip.open(proof_gz, "rb") as source_proof, proof.open("wb") as target:
                    while chunk := source_proof.read(1024 * 1024):
                        target.write(chunk)
                if sha(proof) != proof_result["proof"]["uncompressed_sha256"]:
                    raise ValueError(f"{case_id}: proof content hash mismatch")
                started = time.monotonic()
                replay = subprocess.run(
                    [str(DRAT_TRIM), str(cnf), str(proof)],
                    capture_output=True, text=True, timeout=600,
                )
                replay_seconds.append(time.monotonic() - started)
                if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                    raise ValueError(f"{case_id}: independent DRAT replay failed")
            replay_count += 1
    report = {
        "schema_version": 1,
        "status": "VALID",
        "protocol_sha256": sha(PROTOCOL),
        "summary_sha256": sha(SUMMARY),
        "case_count": 6,
        "independently_checked_weighted_obstructions": weighted_count,
        "independently_replayed_literal_proofs": replay_count,
        "sat_count": sat_count,
        "success_gate_passed": weighted_count > 0 or replay_count > 0,
        "independent_replay_seconds": tails(replay_seconds),
        "claim_limit": "Only the recorded weighted subproblems or opposite-assumption literals are certified. No ancestor closes without complete audited aggregation.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
