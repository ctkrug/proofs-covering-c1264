#!/usr/bin/env python3
"""Proof-producing fixed-cap run over the audited 42-child hard split."""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CADICAL = ROOT / ".venv/sat-audit-tools/cadical/build/cadical"
DRAT_TRIM = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"
SECONDS = 60
PARALLELISM = 4


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_sat(stdout: str, folder: Path) -> dict[str, object]:
    model = [int(value) for line in stdout.splitlines() if line.startswith("v ") for value in line.split()[1:] if value != "0"]
    selected = [literal for literal in model if 0 < literal <= 462]
    blocks = tuple(itertools.combinations(range(1, 12), 5))
    design = tuple(sorted(blocks[value - 1] for value in selected))
    if len(design) != 20 or len(set(design)) != 20:
        raise ValueError("SAT model does not select exactly 20 blocks")
    covered = {triple for block in design for triple in itertools.combinations(block, 3)}
    if covered != set(itertools.combinations(range(1, 12), 3)):
        raise ValueError("SAT model misses a triple")
    witness = folder / "witness.txt"
    witness.write_text("".join(" ".join(map(str, block)) + "\n" for block in design))
    return {"path": str(witness.relative_to(ROOT)), "sha256": sha(witness), "bytes": witness.stat().st_size}


def run_child(child: dict[str, object]) -> dict[str, object]:
    cnf = ROOT / child["cnf"]["path"]
    folder = cnf.parent
    proof = folder / "proof.drat"
    solver_log = folder / "solver.log"
    replay_log = folder / "replay.log"
    result_path = folder / "result.json"
    if sha(cnf) != child["cnf"]["sha256"]:
        raise ValueError(f"{child['id']}: CNF hash mismatch")
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [str(CADICAL), "-q", "-t", str(SECONDS), str(cnf), str(proof)],
            capture_output=True, text=True, timeout=SECONDS + 15,
        )
    except subprocess.TimeoutExpired as error:
        solver_log.write_text((error.stdout or "") + (error.stderr or ""))
        result = {"schema_version": 1, "status": "TIMEOUT", "leaf_id": child["id"], "elapsed_seconds": time.monotonic() - started, "seconds_cap": SECONDS}
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    solver_log.write_text(completed.stdout + completed.stderr)
    elapsed = time.monotonic() - started
    if completed.returncode == 10:
        witness = validate_sat(completed.stdout, folder)
        result = {"schema_version": 1, "status": "SAT_VALID_COVER_PENDING_ISOMORPHISM_AUDIT", "witness": witness}
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return {"id": child["id"], **result, "elapsed_seconds": elapsed}
    if completed.returncode != 20:
        result = {"schema_version": 1, "status": "TIMEOUT", "leaf_id": child["id"], "returncode": completed.returncode, "elapsed_seconds": elapsed, "seconds_cap": SECONDS}
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    replay = subprocess.run([str(DRAT_TRIM), str(cnf), str(proof)], capture_output=True, text=True, timeout=600)
    replay_log.write_text(replay.stdout + replay.stderr)
    if replay.returncode != 0 or "VERIFIED" not in replay.stdout + replay.stderr:
        return {"id": child["id"], "status": "INVALID_PROOF", "elapsed_seconds": elapsed}
    receipt = {
        "schema_version": 1,
        "status": "UNSAT_VERIFIED",
        "leaf_id": child["id"],
        "cnf": {"path": str(cnf.relative_to(ROOT)), "sha256": sha(cnf), "bytes": cnf.stat().st_size},
        "proof": {"path": str(proof.relative_to(ROOT)), "sha256": sha(proof), "bytes": proof.stat().st_size},
        "solver": {"path": str(CADICAL.relative_to(ROOT)), "sha256": sha(CADICAL), "returncode": completed.returncode, "elapsed_seconds": elapsed, "seconds_cap": SECONDS},
        "checker": {"path": str(DRAT_TRIM.relative_to(ROOT)), "sha256": sha(DRAT_TRIM), "returncode": replay.returncode},
        "solver_log": {"path": str(solver_log.relative_to(ROOT)), "sha256": sha(solver_log)},
        "replay_log": {"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)},
    }
    receipt_path = folder / "replay-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    result = {
        "schema_version": 1,
        "status": "UNSAT_VERIFIED",
        "proof": receipt["proof"],
        "replay_receipt": {"path": str(receipt_path.relative_to(ROOT)), "sha256": sha(receipt_path)},
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return receipt


def main() -> None:
    manifest_path = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-split/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    children = [child for parent in manifest["parents"] for child in parent["children"]]
    outcomes = []
    with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
        futures = {pool.submit(run_child, child): child["id"] for child in children}
        for future in as_completed(futures):
            outcomes.append(future.result())
    outcomes.sort(key=lambda row: row.get("id", row.get("leaf_id", "")))
    summary = {
        "schema_version": 1,
        "status": "COMPLETE",
        "fixed_protocol": {"seconds_cap": SECONDS, "parallelism": PARALLELISM, "children": len(children)},
        "manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "counts": {name: sum(row["status"] == name for row in outcomes) for name in sorted({row["status"] for row in outcomes})},
        "outcomes": outcomes,
        "claim_limit": "Each verified receipt closes one child only. A top-level parent closes only if its full audited child partition closes.",
    }
    target = manifest_path.parent / "proof-tranche-60s.json"
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
