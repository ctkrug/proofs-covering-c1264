#!/usr/bin/env python3
"""Proof-producing tranche for the three measured-easy ordinary-link leaves."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEAVES = ("intersection-2", "intersection-1", "intersection-0")
SECONDS = 60
CADICAL = ROOT / ".venv/sat-audit-tools/cadical/build/cadical"
DRAT_TRIM = ROOT / ".venv/sat-audit-tools/drat-trim/drat-trim"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_leaf(leaf_id: str, expected_cnf_sha256: str) -> dict[str, object]:
    folder = ROOT / "artifacts/classification/ordinary-c1153-v1" / leaf_id
    cnf = folder / "instance.cnf"
    proof = folder / "proof.drat"
    solver_log = folder / "solver.log"
    replay_log = folder / "replay.log"
    if sha(cnf) != expected_cnf_sha256:
        raise ValueError(f"{leaf_id}: frozen CNF hash mismatch")
    started = time.monotonic()
    completed = subprocess.run(
        [str(CADICAL), "-q", "-t", str(SECONDS), str(cnf), str(proof)],
        capture_output=True, text=True, timeout=SECONDS + 15,
    )
    solver_log.write_text(completed.stdout + completed.stderr)
    elapsed = time.monotonic() - started
    if completed.returncode == 10:
        return {"id": leaf_id, "status": "SAT_PROVISIONAL", "elapsed_seconds": elapsed}
    if completed.returncode != 20:
        return {"id": leaf_id, "status": "TIMEOUT_OR_ERROR", "returncode": completed.returncode, "elapsed_seconds": elapsed}
    replay = subprocess.run([str(DRAT_TRIM), str(cnf), str(proof)], capture_output=True, text=True, timeout=300)
    replay_text = replay.stdout + replay.stderr
    replay_log.write_text(replay_text)
    if replay.returncode != 0 or "VERIFIED" not in replay_text:
        return {"id": leaf_id, "status": "INVALID_PROOF", "elapsed_seconds": elapsed, "replay_returncode": replay.returncode}
    receipt = {
        "schema_version": 1,
        "status": "UNSAT_VERIFIED",
        "leaf_id": leaf_id,
        "cnf": {"path": str(cnf.relative_to(ROOT)), "sha256": sha(cnf), "bytes": cnf.stat().st_size},
        "proof": {"path": str(proof.relative_to(ROOT)), "sha256": sha(proof), "bytes": proof.stat().st_size},
        "solver": {"path": str(CADICAL.relative_to(ROOT)), "sha256": sha(CADICAL), "returncode": completed.returncode, "elapsed_seconds": elapsed, "seconds_cap": SECONDS},
        "checker": {"path": str(DRAT_TRIM.relative_to(ROOT)), "sha256": sha(DRAT_TRIM), "returncode": replay.returncode},
        "solver_log": {"path": str(solver_log.relative_to(ROOT)), "sha256": sha(solver_log)},
        "replay_log": {"path": str(replay_log.relative_to(ROOT)), "sha256": sha(replay_log)},
        "claim_limit": "Replay-verified UNSAT for this exact ordinary-classification leaf only.",
    }
    receipt_path = folder / "replay-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    result_path = folder / "result.json"
    result_path.write_text(json.dumps({
        "schema_version": 1,
        "status": "UNSAT_VERIFIED",
        "proof": receipt["proof"],
        "replay_receipt": {"path": str(receipt_path.relative_to(ROOT)), "sha256": sha(receipt_path)},
        "claim_limit": receipt["claim_limit"],
    }, indent=2, sort_keys=True) + "\n")
    return receipt


def main() -> None:
    manifest_path = ROOT / "artifacts/classification/ordinary-c1153-v1/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    expected = {leaf["id"]: leaf["cnf"]["sha256"] for leaf in manifest["leaves"]}
    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(lambda leaf_id: run_leaf(leaf_id, expected[leaf_id]), LEAVES))
    tranche = {
        "schema_version": 1,
        "status": "COMPLETE",
        "fixed_protocol": {"leaves": list(LEAVES), "seconds_cap": SECONDS, "parallelism": 3},
        "manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "outcomes": outcomes,
        "claim_limit": "These receipts contribute to the separate ordinary C(11,5,3) classification only; they do not change the C(12,6,4) frontier ledger.",
    }
    target = manifest_path.parent / "easy-proof-tranche.json"
    target.write_text(json.dumps(tranche, indent=2, sort_keys=True) + "\n")
    print(json.dumps(tranche, sort_keys=True))


if __name__ == "__main__":
    main()
