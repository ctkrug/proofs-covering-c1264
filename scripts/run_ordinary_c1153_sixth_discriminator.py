#!/usr/bin/env python3
"""Freeze and run the bounded final hard-tail sixth-block discriminator."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-sixth-discriminator-final"
MANIFEST = BASE / "manifest.json"
AUDIT = BASE / "independent-audit.json"
PROTOCOL = BASE / "discriminator-protocol.json"
RESULTS = BASE / "discriminator-results"
CADICAL = ROOT / ".venv/sat-audit-tools/cadical/build/cadical"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"
SECONDS = 5
PARALLELISM = 4


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def exact_cnf(parent: Path, units: list[int], target: Path) -> tuple[int, int]:
    with parent.open() as source, target.open("w") as output:
        header = source.readline().split()
        if header[:2] != ["p", "cnf"]:
            raise ValueError("invalid cached CNF header")
        variables, clauses = int(header[2]), int(header[3])
        output.write(f"p cnf {variables} {clauses + len(units)}\n")
        for line in source:
            output.write(line)
        for value in units:
            output.write(f"{value} 0\n")
    return variables, clauses + len(units)


def sixth_units(case: dict[str, object], index: int) -> list[int]:
    return [
        *[-value for orbit in case["sixth_orbits"][:index] for value in orbit["member_variables"]],
        case["sixth_orbits"][index]["canonical_variable"],
    ]


def choose_cases(manifest: dict[str, object]) -> list[dict[str, object]]:
    """Four deterministic quantiles in each root x stabilizer-tercile stratum."""
    chosen = []
    for root in sorted({case["top_parent"] for case in manifest["cases"]}):
        root_cases = sorted(
            (case for case in manifest["cases"] if case["top_parent"] == root),
            key=lambda case: (case["stabilizer_order"], case["branch_count"], case["id"]),
        )
        boundaries = [round(i * len(root_cases) / 3) for i in range(4)]
        for tier, (start, stop) in enumerate(zip(boundaries, boundaries[1:])):
            group = root_cases[start:stop]
            indices = sorted({round(i * (len(group) - 1) / 3) for i in range(4)})
            if len(indices) != 4:
                raise ValueError(f"{root} stabilizer tier {tier} lacks four quantiles")
            for index in indices:
                row = dict(group[index])
                row["sample_stabilizer_tier"] = ("low", "mid", "high")[tier]
                chosen.append(row)
    if len(chosen) != 24 or len({case["id"] for case in chosen}) != 24:
        raise ValueError("expected exactly 24 distinct stratified parents")
    return chosen


def freeze() -> dict[str, object]:
    manifest, audit = json.loads(MANIFEST.read_text()), json.loads(AUDIT.read_text())
    if audit["status"] != "VALID" or audit["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("final sixth partition audit gate failed")
    sample = []
    for case in choose_cases(manifest):
        for position, index in (("early_orbit_zero", 0), ("latter_three_quarter", 3 * case["branch_count"] // 4)):
            sample.append({
                "leaf_id": f"{case['id']}-sixth-{index:03d}",
                "fifth_case_id": case["id"],
                "top_parent": case["top_parent"],
                "stabilizer_order": case["stabilizer_order"],
                "stabilizer_tier": case["sample_stabilizer_tier"],
                "sixth_position": position,
                "sixth_index": index,
                "sixth_branch_count": case["branch_count"],
            })
    frozen = {
        "schema_version": 1,
        "status": "FROZEN_NOT_RUN",
        "partition_manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": sha(MANIFEST)},
        "partition_audit": {"path": str(AUDIT.relative_to(ROOT)), "sha256": sha(AUDIT)},
        "sample": sample,
        "sample_size": len(sample),
        "sample_sha256": hashlib.sha256(("\n".join(row["leaf_id"] for row in sample) + "\n").encode()).hexdigest(),
        "selection_rule": "Within each top-parent root class, sort by stabilizer order, branch count, and id; split into stabilizer-order terciles; choose four deterministic quantiles per tercile; test sixth orbit zero and floor(3*branch_count/4).",
        "fixed_protocol": {"solver": "CaDiCaL", "seconds_cap": SECONDS, "parallelism": PARALLELISM, "proof": "DRAT", "external_replay": "drat-trim"},
        "hypothesis": manifest["hypothesis"],
        "decision_gate": "Support requires at least 18/24 replay-verified latter-position UNSAT closures and strictly more timeouts in the 24 early children than in the 24 latter children. Otherwise reject orbit-rank propagation as the primary hard-tail explanation.",
        "storage_budget_bytes": 128 * 1024 * 1024,
        "worst_solver_wall_seconds": len(sample) * SECONDS / PARALLELISM,
        "claim_limit": "Bounded structural discriminator only; no generic sixth sweep or parent closure.",
    }
    BASE.mkdir(parents=True, exist_ok=True)
    if PROTOCOL.exists() and json.loads(PROTOCOL.read_text()) != frozen:
        raise ValueError("incompatible frozen protocol already exists")
    if not PROTOCOL.exists():
        PROTOCOL.write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    return frozen


def validate_cover(stdout: str, folder: Path) -> dict[str, object]:
    model = [int(value) for line in stdout.splitlines() if line.startswith("v ") for value in line.split()[1:] if value != "0"]
    blocks = tuple(itertools.combinations(range(1, 12), 5))
    design = tuple(sorted(blocks[value - 1] for value in model if 0 < value <= 462))
    covered = {triple for block in design for triple in itertools.combinations(block, 3)}
    if len(design) != 20 or len(set(design)) != 20 or covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("SAT model is not an ordinary 20-block cover")
    witness = folder / "witness.txt"
    witness.write_text("".join(" ".join(map(str, block)) + "\n" for block in design))
    return {"path": str(witness.relative_to(ROOT)), "sha256": sha(witness)}


def run_one(job: dict[str, object], case: dict[str, object]) -> dict[str, object]:
    folder = RESULTS / job["leaf_id"]
    result_path = folder / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    folder.mkdir(parents=True, exist_ok=False)
    parent = ROOT / case["third_level_parent_cnf"]["path"]
    if sha(parent) != case["third_level_parent_cnf"]["sha256"]:
        raise ValueError("parent CNF hash mismatch")
    added = sixth_units(case, job["sixth_index"])
    units = [*case["inherited_units"], *added]
    with tempfile.TemporaryDirectory(prefix="ordinary-sixth-discriminator-") as temporary:
        temp = Path(temporary)
        cnf, proof = temp / "instance.cnf", temp / "proof.drat"
        variables, clauses = exact_cnf(parent, units, cnf)
        started = time.monotonic()
        solved = subprocess.run([str(CADICAL), "-q", "-t", str(SECONDS), str(cnf), str(proof)], capture_output=True, text=True, timeout=SECONDS + 20)
        elapsed = time.monotonic() - started
        log = folder / "solver.log"
        log.write_text(solved.stdout + solved.stderr)
        result = {
            "schema_version": 1, **job,
            "protocol_sha256": sha(PROTOCOL),
            "parent_cnf_sha256": case["third_level_parent_cnf"]["sha256"],
            "inherited_unit_sha256": case["inherited_unit_sha256"],
            "sixth_unit_sha256": unit_sha(added),
            "exact_cnf_sha256": sha(cnf), "exact_cnf_variables": variables, "exact_cnf_clauses": clauses,
            "seconds_cap": SECONDS, "solver_elapsed_seconds": elapsed,
            "solver_log": {"path": str(log.relative_to(ROOT)), "sha256": sha(log)},
        }
        if solved.returncode == 10:
            result.update(status="SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT", witness=validate_cover(solved.stdout, folder))
        elif solved.returncode == 20:
            replay = subprocess.run([str(CHECKER), str(cnf), str(proof)], capture_output=True, text=True, timeout=600)
            replay_log = folder / "runner-replay.log"
            replay_log.write_text(replay.stdout + replay.stderr)
            if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
                result.update(status="INVALID_PROOF")
            else:
                compressed = folder / "proof.drat.gz"
                with proof.open("rb") as source, compressed.open("wb") as raw:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
                result.update(status="UNSAT_VERIFIED_BY_RUNNER", proof={"path": str(compressed.relative_to(ROOT)), "sha256": sha(compressed), "compressed_bytes": compressed.stat().st_size, "uncompressed_sha256": sha(proof), "uncompressed_bytes": proof.stat().st_size}, replay_log={"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)})
        else:
            result.update(status="FIXED_CAP_TIMEOUT", returncode=solved.returncode, claim_limit="UNKNOWN closes no branch")
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def run() -> dict[str, object]:
    protocol = freeze()
    manifest = json.loads(MANIFEST.read_text())
    cases = {case["id"]: case for case in manifest["cases"]}
    outcomes = []
    stopped_for_sat = False
    for offset in range(0, len(protocol["sample"]), PARALLELISM):
        batch = protocol["sample"][offset:offset + PARALLELISM]
        with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
            futures = [pool.submit(run_one, job, cases[job["fifth_case_id"]]) for job in batch]
            outcomes.extend(future.result() for future in as_completed(futures))
        if any(row["status"].startswith("SAT_") for row in outcomes):
            stopped_for_sat = True
            break
    outcomes.sort(key=lambda row: row["leaf_id"])
    statuses = sorted({row["status"] for row in outcomes})
    counts = {status: sum(row["status"] == status for row in outcomes) for status in statuses}
    by_position = {position: {status: sum(row["sixth_position"] == position and row["status"] == status for row in outcomes) for status in statuses} for position in ("early_orbit_zero", "latter_three_quarter")}
    latter_unsat = sum(row["sixth_position"] == "latter_three_quarter" and row["status"] == "UNSAT_VERIFIED_BY_RUNNER" for row in outcomes)
    early_timeouts = sum(row["sixth_position"] == "early_orbit_zero" and row["status"] == "FIXED_CAP_TIMEOUT" for row in outcomes)
    latter_timeouts = sum(row["sixth_position"] == "latter_three_quarter" and row["status"] == "FIXED_CAP_TIMEOUT" for row in outcomes)
    summary = {
        "schema_version": 1, "status": "STOPPED_FOR_SAT" if stopped_for_sat else "COMPLETE_PENDING_INDEPENDENT_AUDIT",
        "protocol": {"path": str(PROTOCOL.relative_to(ROOT)), "sha256": sha(PROTOCOL)},
        "completed": len(outcomes), "counts": counts, "counts_by_position": by_position,
        "hypothesis_gate_provisional": latter_unsat >= 18 and early_timeouts > latter_timeouts,
        "compressed_proof_bytes": sum(row.get("proof", {}).get("compressed_bytes", 0) for row in outcomes),
        "outcomes": outcomes,
        "claim_limit": "Runner replay is not the independent result audit; no generic scale follows automatically.",
    }
    (BASE / "discriminator-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    args = parser.parse_args()
    report = freeze() if args.mode == "freeze" else run()
    print(json.dumps({key: report[key] for key in report if key in ("status", "sample_size", "completed", "counts", "counts_by_position", "hypothesis_gate_provisional")}, indent=2, sort_keys=True))
