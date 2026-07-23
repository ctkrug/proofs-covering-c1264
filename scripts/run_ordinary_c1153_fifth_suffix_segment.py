#!/usr/bin/env python3
"""Run one frozen, resumable fifth-level suffix-scale segment."""

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

from pysat.formula import CNF


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
CADICAL = ROOT / ".venv/sat-audit-tools/cadical/build/cadical"
CHECKER = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def fifth_units(parent: dict[str, object], index: int) -> list[int]:
    earlier = [value for orbit in parent["fifth_orbits"][:index] for value in orbit["member_variables"]]
    return [-value for value in earlier] + [parent["fifth_orbits"][index]["canonical_variable"]]


def write_exact_cnf(parent_path: Path, units: list[int], target: Path) -> tuple[int, int]:
    """Append unit recipes without reparsing; byte-identical to PySAT output."""
    with parent_path.open() as source, target.open("w") as output:
        header = source.readline().split()
        if header[:2] != ["p", "cnf"]:
            raise ValueError(f"bad cached parent header: {parent_path}")
        variables, clauses = int(header[2]), int(header[3])
        output.write(f"p cnf {variables} {clauses + len(units)}\n")
        for line in source:
            output.write(line)
        for value in units:
            output.write(f"{value} 0\n")
    return variables, clauses + len(units)


def position(parent: dict[str, object], index: int) -> str:
    fraction = index / parent["branch_count"]
    if fraction < 0.5:
        return "first_quartile"
    if fraction < 0.75:
        return "middle_quartile"
    return "last_quartile"


def validate_cover(stdout: str, folder: Path) -> dict[str, object]:
    model = [int(value) for line in stdout.splitlines() if line.startswith("v ") for value in line.split()[1:] if value != "0"]
    selected = [literal for literal in model if 0 < literal <= 462]
    blocks = tuple(itertools.combinations(range(1, 12), 5))
    design = tuple(sorted(blocks[value - 1] for value in selected))
    covered = {triple for block in design for triple in itertools.combinations(block, 3)}
    if len(design) != 20 or len(set(design)) != 20 or covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("SAT model is not an ordinary 20-block C(11,5,3) cover")
    witness = folder / "witness.txt"
    witness.write_text("".join(" ".join(map(str, block)) + "\n" for block in design))
    return {"path": str(witness.relative_to(ROOT)), "sha256": sha(witness), "bytes": witness.stat().st_size}


def run_one(parent: dict[str, object], index: int, leaf_id: str, folder: Path, seconds: int, full_runner_replay: bool) -> dict[str, object]:
    result_path = folder / "result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text())
        if result["leaf_id"] != leaf_id or result["seconds_cap"] != seconds:
            raise ValueError(f"{leaf_id}: incompatible resumable result")
        return result
    folder.mkdir(parents=True, exist_ok=True)
    parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
    if sha(parent_path) != parent["third_level_parent_cnf"]["sha256"]:
        raise ValueError(f"{leaf_id}: cached parent CNF hash mismatch")
    inherited = parent["inherited_fourth_units"]
    if unit_sha(inherited) != parent["inherited_fourth_unit_sha256"]:
        raise ValueError(f"{leaf_id}: inherited recipe hash mismatch")
    units = fifth_units(parent, index)
    with tempfile.TemporaryDirectory(prefix="ordinary-fifth-suffix-") as temporary:
        temp = Path(temporary)
        cnf_path, proof_path = temp / "instance.cnf", temp / "proof.drat"
        exact_variables, exact_clauses = write_exact_cnf(parent_path, inherited + units, cnf_path)
        started = time.monotonic()
        solved = subprocess.run(
            [str(CADICAL), "-q", "-t", str(seconds), str(cnf_path), str(proof_path)],
            capture_output=True, text=True, timeout=seconds + 20,
        )
        elapsed = time.monotonic() - started
        solver_log = folder / "solver.log"
        solver_log.write_text(solved.stdout + solved.stderr)
        result = {
            "schema_version": 1,
            "leaf_id": leaf_id,
            "fourth_parent_id": parent["id"],
            "fifth_index": index,
            "position": position(parent, index),
            "parent_branch_count": parent["branch_count"],
            "parent_cnf_sha256": parent["third_level_parent_cnf"]["sha256"],
            "inherited_fourth_unit_sha256": parent["inherited_fourth_unit_sha256"],
            "fifth_unit_sha256": unit_sha(units),
            "exact_cnf_sha256": sha(cnf_path),
            "exact_cnf_variables": exact_variables,
            "exact_cnf_clauses": exact_clauses,
            "seconds_cap": seconds,
            "solver_elapsed_seconds": elapsed,
            "solver_log": {"path": str(solver_log.relative_to(ROOT)), "sha256": sha(solver_log)},
        }
        if solved.returncode == 10:
            result.update(status="SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT", witness=validate_cover(solved.stdout, folder))
        elif solved.returncode == 20:
            compressed = folder / "proof.drat.gz"
            with proof_path.open("rb") as source, compressed.open("wb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
            proof = {"path": str(compressed.relative_to(ROOT)), "sha256": sha(compressed), "compressed_bytes": compressed.stat().st_size,
                     "uncompressed_sha256": sha(proof_path), "uncompressed_bytes": proof_path.stat().st_size}
            if full_runner_replay:
                replayed = subprocess.run([str(CHECKER), str(cnf_path), str(proof_path)], capture_output=True, text=True, timeout=600)
                replay_log = folder / "runner-replay.log"
                replay_log.write_text(replayed.stdout + replayed.stderr)
                if replayed.returncode != 0 or "VERIFIED" not in replayed.stdout + replayed.stderr:
                    result.update(status="INVALID_PROOF", proof=proof, replay_log={"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)})
                else:
                    result.update(
                        status="UNSAT_VERIFIED_BY_RUNNER", proof=proof,
                        replay_log={"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)},
                        checker={"path": str(CHECKER.relative_to(ROOT)), "sha256": sha(CHECKER)},
                    )
            else:
                result.update(
                    status="PROVISIONAL_UNSAT_PROOF_RETAINED", proof=proof,
                    claim_limit="Solver UNSAT with a retained hash-bound proof; not a certified closure until later external replay.",
                )
        else:
            result.update(status="FIXED_CAP_TIMEOUT", returncode=solved.returncode,
                          partial_proof_sha256=sha(proof_path) if proof_path.exists() else None,
                          claim_limit="UNKNOWN closes no branch.")
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", type=int, default=0)
    args = parser.parse_args()
    route_path = BASE / "suffix-scale-manifest.json"
    audit_path = BASE / "suffix-scale-independent-audit.json"
    route, audit = json.loads(route_path.read_text()), json.loads(audit_path.read_text())
    if audit["status"] != "VALID" or audit["route_manifest_sha256"] != sha(route_path):
        raise ValueError("independent suffix selection/storage gate failed")
    segment_dir = BASE / "segments" / f"segment-{args.segment:04d}"
    manifest_path = segment_dir / "manifest.json"
    if not manifest_path.exists():
        segment_entry = route["segments"][args.segment]
        if segment_entry["segment"] != args.segment:
            raise ValueError("route segment index mismatch")
        segment_dir.mkdir(parents=True, exist_ok=False)
        frozen = {
            "schema_version": 1, "status": "FROZEN_NOT_RUN",
            "route_manifest": {"path": str(route_path.relative_to(ROOT)), "sha256": sha(route_path)},
            "segment": args.segment, "selected": segment_entry["count"],
            "selection_sha256": segment_entry["selection_sha256"], "leaf_ids": segment_entry["leaf_ids"],
            "fixed_protocol": route["fixed_protocol"],
            "artifact_budget": {"compressed_proof_bytes": 64 * 1024**2,
                                "worst_solver_wall_seconds": segment_entry["count"] * route["fixed_protocol"]["seconds_cap"] / route["fixed_protocol"]["parallelism"]},
            "claim_limit": "Immutable bounded suffix-scale segment; solver UNSAT is provisional until certification replay.",
        }
        manifest_path.write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    manifest = json.loads(manifest_path.read_text())
    if manifest["route_manifest"]["sha256"] != sha(route_path):
        raise ValueError("segment/route binding failed")
    fifth_path = ROOT / route["fifth_manifest"]["path"]
    fifth = json.loads(fifth_path.read_text())
    parents = {row["id"]: row for row in fifth["parents"]}
    lookup = {f"{parent['id']}-fifth-{index:03d}": (parent, index)
              for parent in fifth["parents"] for index in range(parent["branch_count"])}
    leaf_ids = manifest["leaf_ids"]
    if len(leaf_ids) != len(set(leaf_ids)) or any(leaf_id not in lookup for leaf_id in leaf_ids):
        raise ValueError("invalid segment leaf set")
    seconds = manifest["fixed_protocol"]["seconds_cap"]
    parallelism = manifest["fixed_protocol"]["parallelism"]
    policy_path = BASE / "suffix-scale-verification-policy-v2.json"
    policy = json.loads(policy_path.read_text())
    full_runner_replay = args.segment <= policy["effective_after_segment"]
    outcomes: list[dict[str, object]] = []
    stopped_for_sat = False
    started = time.monotonic()
    for offset in range(0, len(leaf_ids), parallelism):
        batch = leaf_ids[offset:offset + parallelism]
        with ThreadPoolExecutor(max_workers=parallelism) as pool:
            futures = []
            for leaf_id in batch:
                parent, index = lookup[leaf_id]
                futures.append(pool.submit(run_one, parent, index, leaf_id, segment_dir / leaf_id, seconds, full_runner_replay))
            for future in as_completed(futures):
                outcomes.append(future.result())
        if any(row["status"].startswith("SAT_") for row in outcomes):
            stopped_for_sat = True
            break
    outcomes.sort(key=lambda row: leaf_ids.index(row["leaf_id"]))
    statuses = sorted({row["status"] for row in outcomes})
    counts = {status: sum(row["status"] == status for row in outcomes) for status in statuses}
    by_position = {label: {status: sum(row["position"] == label and row["status"] == status for row in outcomes) for status in statuses}
                   for label in ("first_quartile", "middle_quartile", "last_quartile")}
    receipt = {
        "schema_version": 1,
        "status": "STOPPED_FOR_SAT" if stopped_for_sat else ("COMPLETE_PENDING_INDEPENDENT_AUDIT" if len(outcomes) == len(leaf_ids) else "PARTIAL"),
        "segment": args.segment,
        "segment_manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "selection_audit": {"path": str(audit_path.relative_to(ROOT)), "sha256": sha(audit_path)},
        "verification_policy": {"path": str(policy_path.relative_to(ROOT)), "sha256": sha(policy_path), "full_runner_replay": full_runner_replay},
        "selected": len(leaf_ids), "completed": len(outcomes), "counts": counts, "counts_by_position": by_position,
        "compressed_proof_bytes": sum(row.get("proof", {}).get("compressed_bytes", 0) for row in outcomes),
        "wall_seconds": time.monotonic() - started,
        "remaining_route_branches_after_completed": route["accounting"]["pending_scale_workload"] - len(outcomes),
        "claim_limit": "Future-policy solver UNSATs are provisional until exhaustive replay; sampled immediate QA is operational only. No fourth parent is closed here.",
    }
    receipt_path = segment_dir / "runner-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
