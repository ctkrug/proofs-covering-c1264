#!/usr/bin/env python3
"""Freeze the 20/47 portfolio and bind the 24 sequential-unmeasured remainder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("artifacts/experiments/sequential-open-frontier-30-v5-native-replay-20260722/manifest.json")
CHECKPOINT = Path("artifacts/sequential-frontier-sweep/sequential-open-frontier-30-v5-native-replay-20260722/checkpoint.json")
PORTFOLIO = Path("artifacts/portfolio/frontier-manifest-v1.json")
SNAPSHOT = Path("artifacts/portfolio/frontier-manifest-20of47-snapshot.json")
OUTPUT = Path("artifacts/experiments/sequential-unmeasured-frontier-24-v5-20260722/manifest.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    source = json.loads((ROOT / SOURCE).read_text())
    checkpoint = json.loads((ROOT / CHECKPOINT).read_text())
    portfolio = json.loads((ROOT / PORTFOLIO).read_text())
    if checkpoint["manifest_sha256"] != sha(ROOT / SOURCE):
        raise ValueError("source checkpoint/manifest hash disagreement")
    if portfolio["counts"] != {"total": 47, "closed": 20, "open": 27}:
        raise ValueError("portfolio must be at the audited 20/47 checkpoint")
    completed = {row["leaf_id"] for row in checkpoint["results"]}
    if completed != {"s-r0-2", "t-3", "t-4", "t-7", "t-8", "t-9"}:
        raise ValueError("unexpected completed continuation units")
    snapshot = ROOT / SNAPSHOT
    snapshot.write_text(json.dumps(portfolio, indent=2, sort_keys=True) + "\n")
    value = dict(source)
    value["schema_version"] = 3
    value["run_id"] = "sequential-unmeasured-frontier-24-v5-20260722"
    value["expected_leaf_count"] = 24
    value["leaves"] = [row for row in source["leaves"] if row["id"] not in completed]
    value["maximum_solver_cpu_seconds"] = 60 * len(value["leaves"])
    value["portfolio_manifest_sha256"] = sha(snapshot)
    value["portfolio_snapshot"] = {"path": str(SNAPSHOT), "sha256": sha(snapshot)}
    value["predecessor_tranche"] = {
        "manifest": {"path": str(SOURCE), "sha256": sha(ROOT / SOURCE)},
        "checkpoint": {"path": str(CHECKPOINT), "sha256": sha(ROOT / CHECKPOINT)},
        "completed_units": sorted(completed),
        "certified_closures": ["t-3", "t-4", "t-7", "t-8", "t-9"],
        "measured_unknown": ["s-r0-2"],
    }
    inputs = dict(source["input_sha256"])
    inputs.pop("artifacts/portfolio/frontier-manifest-v1.json", None)
    for relative in (
        str(SNAPSHOT),
        "scripts/run_sequential_frontier_sweep.py",
        "scripts/build_sequential_remaining_tranche.py",
    ):
        inputs[relative] = sha(ROOT / relative)
    value["input_sha256"] = inputs
    assert len(value["leaves"]) == 24
    return value


def main() -> None:
    value = build()
    output = ROOT / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"built {len(value['leaves'])}-node remaining tranche: {OUTPUT}")


if __name__ == "__main__":
    main()
