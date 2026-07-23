#!/usr/bin/env python3
"""Independently reconstruct and replay every sixth-discriminator UNSAT."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-sixth-discriminator-final"
MANIFEST = BASE / "manifest.json"
PROTOCOL = BASE / "discriminator-protocol.json"
SUMMARY = BASE / "discriminator-summary.json"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def reconstruct(parent: Path, units: list[int], target: Path) -> None:
    with parent.open() as source, target.open("w") as output:
        header = source.readline().split()
        variables, clauses = int(header[2]), int(header[3])
        output.write(f"p cnf {variables} {clauses + len(units)}\n")
        output.writelines(source)
        output.writelines(f"{value} 0\n" for value in units)


def audit() -> dict[str, object]:
    manifest, protocol, summary = map(lambda path: json.loads(path.read_text()), (MANIFEST, PROTOCOL, SUMMARY))
    if protocol["partition_manifest"]["sha256"] != sha(MANIFEST):
        raise ValueError("protocol/partition binding mismatch")
    if summary["protocol"]["sha256"] != sha(PROTOCOL):
        raise ValueError("summary/protocol binding mismatch")
    jobs = {row["leaf_id"]: row for row in protocol["sample"]}
    cases = {case["id"]: case for case in manifest["cases"]}
    if set(jobs) != {row["leaf_id"] for row in summary["outcomes"]}:
        raise ValueError("sample result membership mismatch")
    verified = 0
    for result in summary["outcomes"]:
        job, case = jobs[result["leaf_id"]], cases[result["fifth_case_id"]]
        if any(result[key] != job[key] for key in job):
            raise ValueError(f"{result['leaf_id']}: frozen job mismatch")
        index = job["sixth_index"]
        added = [-value for orbit in case["sixth_orbits"][:index] for value in orbit["member_variables"]] + [case["sixth_orbits"][index]["canonical_variable"]]
        if unit_sha(added) != result["sixth_unit_sha256"]:
            raise ValueError(f"{result['leaf_id']}: sixth recipe mismatch")
        if result["status"] != "UNSAT_VERIFIED_BY_RUNNER":
            continue
        proof_gz = ROOT / result["proof"]["path"]
        if sha(proof_gz) != result["proof"]["sha256"]:
            raise ValueError(f"{result['leaf_id']}: compressed proof mismatch")
        parent = ROOT / case["third_level_parent_cnf"]["path"]
        if sha(parent) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{result['leaf_id']}: parent mismatch")
        with tempfile.TemporaryDirectory(prefix="audit-sixth-discriminator-") as temporary:
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
            replay = subprocess.run([str(CHECKER), str(cnf), str(proof)], capture_output=True, text=True, timeout=600)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                raise ValueError(f"{result['leaf_id']}: external replay failed")
        verified += 1
    counts = Counter(row["status"] for row in summary["outcomes"])
    early_to = sum(row["sixth_position"] == "early_orbit_zero" and row["status"] == "FIXED_CAP_TIMEOUT" for row in summary["outcomes"])
    latter_to = sum(row["sixth_position"] == "latter_three_quarter" and row["status"] == "FIXED_CAP_TIMEOUT" for row in summary["outcomes"])
    latter_verified = sum(row["sixth_position"] == "latter_three_quarter" and row["status"] == "UNSAT_VERIFIED_BY_RUNNER" for row in summary["outcomes"])
    return {
        "schema_version": 1, "status": "VALID", "protocol_sha256": sha(PROTOCOL), "summary_sha256": sha(SUMMARY),
        "sample_count": len(summary["outcomes"]), "counts": dict(counts), "independently_replayed_unsat": verified,
        "hypothesis_supported": latter_verified >= 18 and early_to > latter_to,
        "latter_verified_unsat": latter_verified, "early_timeouts": early_to, "latter_timeouts": latter_to,
        "claim_limit": "Exact 48-child discriminator audit only; no unsampled sixth child or parent is closed.",
    }


if __name__ == "__main__":
    report = audit()
    output = BASE / "discriminator-independent-audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
