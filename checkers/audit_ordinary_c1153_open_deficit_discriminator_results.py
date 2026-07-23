#!/usr/bin/env python3
"""Independently reconstruct and replay the bounded deficit discriminator."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"
MANIFEST = BASE / "manifest.json"
PROTOCOL = BASE / "discriminator-v2/protocol.json"
SUMMARY = BASE / "discriminator-v2/summary.json"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def reconstruct(parent: Path, units: list[int], target: Path) -> None:
    with parent.open() as source, target.open("w") as output:
        header = source.readline().split()
        if header[:2] != ["p", "cnf"]:
            raise ValueError("invalid cached parent header")
        variables, clauses = int(header[2]), int(header[3])
        output.write(f"p cnf {variables} {clauses + len(units)}\n")
        output.writelines(source)
        output.writelines(f"{value} 0\n" for value in units)


def added_units(case: dict[str, object], index: int) -> list[int]:
    return [
        *[
            -value
            for orbit in case["covering_block_orbits"][:index]
            for value in orbit["member_variables"]
        ],
        case["covering_block_orbits"][index]["canonical_variable"],
    ]


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
    manifest, protocol, summary = map(
        lambda path: json.loads(path.read_text()), (MANIFEST, PROTOCOL, SUMMARY)
    )
    if protocol["partition_manifest"]["sha256"] != sha(MANIFEST):
        raise ValueError("protocol/partition binding mismatch")
    if summary["protocol"]["sha256"] != sha(PROTOCOL):
        raise ValueError("summary/protocol binding mismatch")
    jobs = {row["leaf_id"]: row for row in protocol["sample"]}
    cases = {case["id"]: case for case in manifest["cases"]}
    if len(jobs) != protocol["sample_size"] or set(jobs) != {
        row["leaf_id"] for row in summary["outcomes"]
    }:
        raise ValueError("sample result membership mismatch")
    verified = 0
    replay_seconds: list[float] = []
    for result in summary["outcomes"]:
        job = jobs[result["leaf_id"]]
        case = cases[result["fifth_case_id"]]
        if any(result[key] != value for key, value in job.items()):
            raise ValueError(f"{result['leaf_id']}: frozen job mismatch")
        added = added_units(case, job["deficit_index"])
        if unit_sha(added) != result["deficit_unit_sha256"]:
            raise ValueError(f"{result['leaf_id']}: deficit recipe mismatch")
        if result["status"] != "UNSAT_VERIFIED_BY_RUNNER":
            continue
        proof_gz = ROOT / result["proof"]["path"]
        if sha(proof_gz) != result["proof"]["sha256"]:
            raise ValueError(f"{result['leaf_id']}: compressed proof mismatch")
        parent = ROOT / case["third_level_parent_cnf"]["path"]
        if sha(parent) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{result['leaf_id']}: parent mismatch")
        with tempfile.TemporaryDirectory(prefix="audit-open-deficit-") as temporary:
            temp = Path(temporary)
            cnf, proof = temp / "instance.cnf", temp / "proof.drat"
            reconstruct(parent, [*case["inherited_units"], *added], cnf)
            if sha(cnf) != result["exact_cnf_sha256"]:
                raise ValueError(f"{result['leaf_id']}: exact CNF mismatch")
            with gzip.open(proof_gz, "rb") as source, proof.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            if sha(proof) != result["proof"]["uncompressed_sha256"]:
                raise ValueError(f"{result['leaf_id']}: proof content mismatch")
            started = time.monotonic()
            replay = subprocess.run(
                [str(CHECKER), str(cnf), str(proof)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            replay_seconds.append(time.monotonic() - started)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                raise ValueError(f"{result['leaf_id']}: external replay failed")
        verified += 1
    counts = Counter(row["status"] for row in summary["outcomes"])
    by_position = {
        position: dict(
            Counter(
                row["status"]
                for row in summary["outcomes"]
                if row["deficit_position"] == position
            )
        )
        for position in ("first_deficit_orbit", "last_deficit_orbit")
    }
    result_by_parent: dict[str, list[dict[str, object]]] = {}
    for result in summary["outcomes"]:
        result_by_parent.setdefault(result["fifth_case_id"], []).append(result)
    complete_parents = sorted(
        case_id
        for case_id, results in result_by_parent.items()
        if len(results) == cases[case_id]["branch_count"]
        and all(result["status"] == "UNSAT_VERIFIED_BY_RUNNER" for result in results)
    )
    return {
        "schema_version": 1,
        "status": "VALID",
        "protocol_sha256": sha(PROTOCOL),
        "summary_sha256": sha(SUMMARY),
        "sample_count": len(summary["outcomes"]),
        "counts": dict(counts),
        "counts_by_position": by_position,
        "independently_replayed_unsat": verified,
        "complete_fifth_parents": complete_parents,
        "complete_fifth_parent_count": len(complete_parents),
        "remaining_nonempty_children": manifest["deficit_children"] - verified,
        "solver_elapsed_seconds": tails(
            [row["solver_elapsed_seconds"] for row in summary["outcomes"]]
        ),
        "independent_replay_seconds": tails(replay_seconds),
        "compressed_proof_bytes": tails(
            [
                row["proof"]["compressed_bytes"]
                for row in summary["outcomes"]
                if row["status"] == "UNSAT_VERIFIED_BY_RUNNER"
            ]
        ),
        "uncompressed_proof_bytes": tails(
            [
                row["proof"]["uncompressed_bytes"]
                for row in summary["outcomes"]
                if row["status"] == "UNSAT_VERIFIED_BY_RUNNER"
            ]
        ),
        "claim_limit": (
            "Exact 48-child discriminator audit only. No unsampled child closes; a fifth "
            "parent closes only if it appears in complete_fifth_parents after all of its "
            "deficit children independently replay."
        ),
    }


if __name__ == "__main__":
    report = audit()
    output = BASE / "discriminator-v2/independent-audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
