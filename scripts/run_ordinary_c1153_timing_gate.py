#!/usr/bin/env python3
"""Short proofless timing sample for the audited ordinary-link leaves."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty

from pysat.formula import CNF
from pysat.solvers import Solver


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def worker(cnf_path: str, queue: multiprocessing.Queue) -> None:
    cnf = CNF(from_file=cnf_path)
    with Solver(name="cadical195", bootstrap_with=cnf.clauses) as solver:
        status = solver.solve()
        result = {"status": "SAT_PROVISIONAL" if status else "UNSAT_PROVISIONAL", "stats": solver.accum_stats()}
        if status:
            result["positive_primary_literals"] = [value for value in solver.get_model() if 0 < value <= 462]
        queue.put(result)


def run_one(leaf: dict[str, object], seconds: int) -> dict[str, object]:
    path = ROOT / leaf["cnf"]["path"]
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=worker, args=(str(path), queue))
    started = time.monotonic()
    process.start()
    process.join(seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
        outcome: dict[str, object] = {"status": "TIMEOUT"}
    elif process.exitcode != 0:
        outcome = {"status": "ERROR", "exitcode": process.exitcode}
    else:
        try:
            outcome = queue.get(timeout=1)
        except Empty:
            outcome = {"status": "ERROR", "detail": "no child result"}
    outcome.update({
        "id": leaf["id"],
        "cnf_sha256": sha(path),
        "wall_seconds": time.monotonic() - started,
        "seconds_cap": seconds,
    })
    return outcome


def run(seconds: int = 10, parallelism: int = 4) -> dict[str, object]:
    manifest_path = ROOT / "artifacts/classification/ordinary-c1153-v1/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    leaves = list(manifest["leaves"])
    outcomes: list[dict[str, object]] = []
    # Explicit batches avoid oversubscribing the eight physical/logical cores.
    for start in range(0, len(leaves), parallelism):
        batch = leaves[start:start + parallelism]
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            outcomes.extend(pool.map(lambda leaf: run_one(leaf, seconds), batch))
    result = {
        "schema_version": 1,
        "status": "BOUNDED_TIMING_GATE_COMPLETE",
        "manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "solver": "PySAT CaDiCaL 1.9.5, proofless timing only",
        "parallelism": parallelism,
        "seconds_cap_per_leaf": seconds,
        "outcomes": outcomes,
        "runtime_projection": "A timeout supplies only a lower bound. Proof-producing scale is not authorized until these measurements are reviewed and a leaf-specific split or budget is chosen.",
        "claim_limit": "No provisional SAT/UNSAT status is a classification certificate; the global C(12,6,4) ledger is unchanged.",
    }
    target = manifest_path.parent / "timing-gate.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
