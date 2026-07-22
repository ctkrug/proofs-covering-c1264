#!/usr/bin/env python3
"""Frozen stratified proof discriminator over the audited fifth split."""

from __future__ import annotations

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
SECONDS = 5
PARALLELISM = 4


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def choose_parents(manifest: dict[str, object]) -> list[dict[str, object]]:
    groups = {}
    for parent in manifest["parents"]:
        groups.setdefault((parent["prior_status"], parent["top_parent"]), []).append(parent)
    chosen = []
    for key in sorted(groups):
        rows = sorted(groups[key], key=lambda row: (row["branch_count"], row["id"]))
        indices = sorted({round(step * (len(rows) - 1) / 5) for step in range(6)})
        if len(indices) != 6:
            raise ValueError(f"stratum {key} cannot supply six quantiles")
        chosen.extend(rows[index] for index in indices)
    if len(chosen) != 24 or len({row["id"] for row in chosen}) != 24:
        raise ValueError("expected 24 unique stratified parents")
    return chosen


def branch_units(parent: dict[str, object], index: int) -> list[int]:
    earlier = [value for orbit in parent["fifth_orbits"][:index] for value in orbit["member_variables"]]
    return [-value for value in earlier] + [parent["fifth_orbits"][index]["canonical_variable"]]


def validate_sat(stdout: str, folder: Path) -> dict[str, object]:
    model = [int(value) for line in stdout.splitlines() if line.startswith("v ") for value in line.split()[1:] if value != "0"]
    selected = [literal for literal in model if 0 < literal <= 462]
    blocks = tuple(itertools.combinations(range(1, 12), 5))
    design = tuple(sorted(blocks[value - 1] for value in selected))
    covered = {triple for block in design for triple in itertools.combinations(block, 3)}
    if len(design) != 20 or len(set(design)) != 20 or covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("SAT model is not an ordinary 20-block cover")
    witness = folder / "witness.txt"
    witness.write_text("".join(" ".join(map(str, block)) + "\n" for block in design))
    return {"path": str(witness.relative_to(ROOT)), "sha256": sha(witness), "bytes": witness.stat().st_size}


def run_one(parent: dict[str, object], label: str, index: int) -> dict[str, object]:
    leaf_id = f"{parent['id']}-fifth-{index:03d}"
    folder = BASE / "discriminator-5s" / leaf_id
    folder.mkdir(parents=True, exist_ok=False)
    parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
    if sha(parent_path) != parent["third_level_parent_cnf"]["sha256"]:
        raise ValueError(f"{leaf_id}: parent CNF hash mismatch")
    inherited = parent["inherited_fourth_units"]
    if unit_sha(inherited) != parent["inherited_fourth_unit_sha256"]:
        raise ValueError(f"{leaf_id}: inherited recipe mismatch")
    fifth = branch_units(parent, index)
    with tempfile.TemporaryDirectory(prefix="ordinary-fifth-") as temporary:
        temp = Path(temporary)
        cnf_path = temp / "instance.cnf"
        proof_path = temp / "proof.drat"
        cnf = CNF(from_file=str(parent_path))
        exact = CNF(from_clauses=cnf.clauses + [[value] for value in inherited + fifth])
        exact.to_file(str(cnf_path))
        started = time.monotonic()
        solved = subprocess.run([str(CADICAL), "-q", "-t", str(SECONDS), str(cnf_path), str(proof_path)], capture_output=True, text=True, timeout=SECONDS + 15)
        elapsed = time.monotonic() - started
        solver_log = folder / "solver.log"
        solver_log.write_text(solved.stdout + solved.stderr)
        result = {
            "schema_version": 1,
            "leaf_id": leaf_id,
            "fourth_parent_id": parent["id"],
            "stratum": {"prior_status": parent["prior_status"], "top_parent": parent["top_parent"], "branch_count": parent["branch_count"], "position": label},
            "fifth_index": index,
            "parent_cnf_sha256": parent["third_level_parent_cnf"]["sha256"],
            "inherited_fourth_unit_sha256": parent["inherited_fourth_unit_sha256"],
            "fifth_unit_sha256": unit_sha(fifth),
            "exact_cnf_sha256": sha(cnf_path),
            "exact_cnf_variables": exact.nv,
            "exact_cnf_clauses": len(exact.clauses),
            "seconds_cap": SECONDS,
            "solver_elapsed_seconds": elapsed,
            "solver_log": {"path": str(solver_log.relative_to(ROOT)), "sha256": sha(solver_log)},
        }
        if solved.returncode == 10:
            result.update(status="SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT", witness=validate_sat(solved.stdout, folder))
        elif solved.returncode == 20:
            replayed = subprocess.run([str(CHECKER), str(cnf_path), str(proof_path)], capture_output=True, text=True, timeout=600)
            replay_log = folder / "replay.log"
            replay_log.write_text(replayed.stdout + replayed.stderr)
            if replayed.returncode != 0 or "VERIFIED" not in replayed.stdout + replayed.stderr:
                result.update(status="INVALID_PROOF", replay_log={"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)})
            else:
                compressed = folder / "proof.drat.gz"
                with proof_path.open("rb") as source, compressed.open("wb") as raw:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
                result.update(
                    status="UNSAT_VERIFIED",
                    proof={"path": str(compressed.relative_to(ROOT)), "sha256": sha(compressed), "compressed_bytes": compressed.stat().st_size, "uncompressed_sha256": sha(proof_path), "uncompressed_bytes": proof_path.stat().st_size},
                    replay_log={"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)},
                    checker={"path": str(CHECKER.relative_to(ROOT)), "sha256": sha(CHECKER)},
                )
        else:
            result.update(status="FIXED_CAP_TIMEOUT", returncode=solved.returncode, partial_proof_sha256=sha(proof_path) if proof_path.exists() else None, claim_limit="UNKNOWN closes no branch.")
    result_path = folder / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    manifest_path = BASE / "manifest.json"
    audit_path = BASE / "independent-partition-audit.json"
    manifest = json.loads(manifest_path.read_text())
    audit = json.loads(audit_path.read_text())
    if audit["status"] != "VALID" or audit["manifest_sha256"] != sha(manifest_path):
        raise ValueError("fifth partition audit gate failed")
    jobs = []
    selection = []
    for parent in choose_parents(manifest):
        positions = (("orbit_zero", 0), ("orbit_one", 1), ("first_quartile", parent["branch_count"] // 4), ("midpoint", parent["branch_count"] // 2))
        for label, index in positions:
            jobs.append((parent, label, index))
            selection.append({"parent_id": parent["id"], "prior_status": parent["prior_status"], "top_parent": parent["top_parent"], "parent_branch_count": parent["branch_count"], "position": label, "index": index, "leaf_id": f"{parent['id']}-fifth-{index:03d}"})
    protocol = {
        "schema_version": 1,
        "status": "FROZEN",
        "fifth_manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "partition_audit": {"path": str(audit_path.relative_to(ROOT)), "sha256": sha(audit_path)},
        "sample": selection,
        "sample_size": len(selection),
        "selection_rule": "Six deterministic branch-count quantiles from each prior-status x top-parent stratum; within each selected parent test orbit 0, orbit 1, first quartile, and midpoint.",
        "seconds_cap": SECONDS,
        "parallelism": PARALLELISM,
        "expected_worst_solver_wall_seconds": len(selection) * SECONDS / PARALLELISM,
        "compressed_proof_storage_budget_bytes": 64 * 1024 * 1024,
        "scale_gate": "After independent replay, a cheap suffix is demonstrated only if at least 39/48 first-quartile-plus-midpoint cases verify UNSAT, their mean compressed proof is at most 1 MiB, total artifacts remain within 64 MiB, and no SAT or audit disagreement occurs.",
        "route_rule": "If at least 36/48 orbit-zero-plus-orbit-one cases time out, split the early prefix deeper; otherwise compare the hard strata before choosing a method. Any SAT stops for independent isomorphism audit.",
    }
    protocol_path = BASE / "discriminator-5s-protocol.json"
    protocol_path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    outcomes = []
    with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
        futures = [pool.submit(run_one, *job) for job in jobs]
        for future in as_completed(futures):
            outcomes.append(future.result())
    outcomes.sort(key=lambda row: row["leaf_id"])
    suffix = [row for row in outcomes if row["stratum"]["position"] in ("first_quartile", "midpoint")]
    early = [row for row in outcomes if row["stratum"]["position"] in ("orbit_zero", "orbit_one")]
    proofs = [row for row in outcomes if row["status"] == "UNSAT_VERIFIED"]
    suffix_proofs = [row for row in suffix if row["status"] == "UNSAT_VERIFIED"]
    compressed_total = sum(row["proof"]["compressed_bytes"] for row in proofs)
    summary = {
        "schema_version": 1,
        "status": "COMPLETE",
        "protocol": {"path": str(protocol_path.relative_to(ROOT)), "sha256": sha(protocol_path)},
        "counts": {status: sum(row["status"] == status for row in outcomes) for status in sorted({row["status"] for row in outcomes})},
        "counts_by_position": {label: {status: sum(row["stratum"]["position"] == label and row["status"] == status for row in outcomes) for status in sorted({row["status"] for row in outcomes})} for label in ("orbit_zero", "orbit_one", "first_quartile", "midpoint")},
        "compressed_proof_bytes": compressed_total,
        "mean_suffix_compressed_proof_bytes": (sum(row["proof"]["compressed_bytes"] for row in suffix_proofs) / len(suffix_proofs)) if suffix_proofs else None,
        "scale_gate_provisional": len(suffix_proofs) >= 39 and bool(suffix_proofs) and sum(row["proof"]["compressed_bytes"] for row in suffix_proofs) / len(suffix_proofs) <= 1024 * 1024 and compressed_total <= 64 * 1024 * 1024 and all(row["status"] != "SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT" for row in outcomes),
        "early_deeper_split_trigger": sum(row["status"] == "FIXED_CAP_TIMEOUT" for row in early) >= 36,
        "outcomes": outcomes,
        "claim_limit": "Each verified result closes only its exact fifth branch; no fourth parent closes from this sample.",
    }
    summary_path = BASE / "discriminator-5s-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
