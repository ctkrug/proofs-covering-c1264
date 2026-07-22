#!/usr/bin/env python3
"""Version the five-orbit sweep after preserving completed preflight units."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = Path("artifacts/experiments/sequential-open-frontier-32-v5-20260722/manifest.json")
CHECKPOINT = Path("artifacts/sequential-frontier-sweep/sequential-open-frontier-32-v5-20260722/checkpoint.json")
OUTPUT = Path("artifacts/experiments/sequential-open-frontier-30-v5-native-replay-20260722/manifest.json")
NATIVE_CHECKER = Path(".venv/sat-audit-tools/drat-trim/drat-trim")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    base = json.loads((ROOT / BASE).read_text())
    checkpoint = json.loads((ROOT / CHECKPOINT).read_text())
    if checkpoint["manifest_sha256"] != sha(ROOT / BASE):
        raise ValueError("predecessor checkpoint/manifest hash disagreement")
    completed = {row["leaf_id"]: row for row in checkpoint["results"]}
    if set(completed) != {"s-r1-3", "s-r0-1"} or any(row["status"] != "UNKNOWN" for row in completed.values()):
        raise ValueError("unexpected predecessor completion set")
    value = dict(base)
    value["schema_version"] = 2
    value["run_id"] = "sequential-open-frontier-30-v5-native-replay-20260722"
    value["expected_leaf_count"] = 30
    value["leaves"] = [row for row in base["leaves"] if row["id"] not in completed]
    value["drat_trim"] = str(NATIVE_CHECKER)
    value["maximum_solver_cpu_seconds"] = 60 * len(value["leaves"])
    value["predecessor_completed_units"] = {
        "manifest": {"path": str(BASE), "sha256": sha(ROOT / BASE)},
        "checkpoint": {"path": str(CHECKPOINT), "sha256": sha(ROOT / CHECKPOINT)},
        "preserved_results": [
            {
                "leaf_id": ident,
                "status": completed[ident]["status"],
                "cnf_sha256": completed[ident]["cnf_sha256"],
                "solver_sha256": completed[ident]["solver_sha256"],
                "runtime_seconds": completed[ident]["solver_elapsed_seconds"],
            }
            for ident in sorted(completed)
        ],
        "claim_limit": "Both preserved units are measured UNKNOWN results, not closures; they are excluded only to avoid duplicate work.",
    }
    inputs = dict(base["input_sha256"])
    for relative in ("scripts/build_sequential_frontier_sweep.py", "scripts/run_sequential_frontier_sweep.py"):
        inputs[relative] = sha(ROOT / relative)
    inputs[str(NATIVE_CHECKER)] = sha(ROOT / NATIVE_CHECKER)
    inputs[str(Path("scripts/build_sequential_frontier_continuation.py"))] = sha(
        ROOT / "scripts/build_sequential_frontier_continuation.py"
    )
    value["input_sha256"] = inputs
    assert len(value["leaves"]) == 30
    return value


def main() -> None:
    value = build()
    output = ROOT / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"built {len(value['leaves'])}-node native-replay continuation: {OUTPUT}")


if __name__ == "__main__":
    main()
