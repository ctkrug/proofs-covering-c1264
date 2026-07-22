#!/usr/bin/env python3
"""Build an audited retry of the rejected 32-node sequential lab job."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "8ac4fa372810784ab2182cbe58b0c503757c4599"
BASE_PATH = "artifacts/experiments/sequential-open-frontier-32-v5-20260722/manifest.json"
RUN_ID = "sequential-open-frontier-32-v5-20260722-registration-retry-01"
OUT = ROOT / "artifacts/experiments" / RUN_ID / "manifest.json"
AUDIT = OUT.parent / "protocol-equivalence-audit.json"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canonical_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def main() -> None:
    base_bytes = subprocess.check_output(
        ["git", "show", f"{BASE_COMMIT}:{BASE_PATH}"], cwd=ROOT
    )
    if sha_bytes(base_bytes) != "65f3e3105d146fef368f1c36f491e11d605437876fbbbaa7cf8dfaea32c28a61":
        raise ValueError("historical manifest does not match the rejected job pin")
    base = json.loads(base_bytes)
    retry = json.loads(base_bytes)
    retry["expected_leaf_count"] = 32
    retry["run_id"] = RUN_ID
    historical_portfolio = subprocess.check_output(
        ["git", "show", f"{BASE_COMMIT}:artifacts/portfolio/frontier-manifest-v1.json"], cwd=ROOT
    )
    frozen_portfolio = OUT.parent / "frozen-inputs/frontier-manifest-v1.json"
    frozen_portfolio.parent.mkdir(parents=True, exist_ok=True)
    frozen_portfolio.write_bytes(historical_portfolio)
    original_portfolio_path = "artifacts/portfolio/frontier-manifest-v1.json"
    frozen_portfolio_path = str(frozen_portfolio.relative_to(ROOT))
    expected_portfolio_sha = retry["input_sha256"].pop(original_portfolio_path)
    if sha_bytes(historical_portfolio) != expected_portfolio_sha:
        raise ValueError("historical portfolio does not match the rejected manifest pin")
    retry["input_sha256"][frozen_portfolio_path] = expected_portfolio_sha
    retry["input_sha256"]["scripts/build_sequential_frontier_sweep.py"] = sha(
        ROOT / "scripts/build_sequential_frontier_sweep.py"
    )
    retry["input_sha256"]["scripts/run_sequential_frontier_sweep.py"] = sha(
        ROOT / "scripts/run_sequential_frontier_sweep.py"
    )

    invariant_fields = [
        "blocking_cnf", "catalog", "cold_runs", "drat_trim", "frontier_summary",
        "hypothesis", "leaves", "maximum_projected_proof_bytes",
        "maximum_solver_cpu_seconds", "method", "portfolio_manifest_sha256",
        "predecessor", "preserved_certified_nodes", "run_order", "seconds_per_run",
        "selection_basis", "solver", "success_rule",
    ]
    disagreements = [field for field in invariant_fields if retry[field] != base[field]]
    if disagreements:
        raise ValueError(f"retry changed protocol fields: {disagreements}")
    if len(retry["leaves"]) != 32:
        raise ValueError("retry must retain exactly 32 leaves")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(retry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit = {
        "schema_version": 1,
        "status": "protocol_identical_immutable_input_retry",
        "rejected_job_id": "lab-covering-c1264-263259d8a84d",
        "base_commit": BASE_COMMIT,
        "base_manifest_path": BASE_PATH,
        "base_manifest_sha256": sha_bytes(base_bytes),
        "retry_manifest_path": str(OUT.relative_to(ROOT)),
        "retry_manifest_sha256": sha(OUT),
        "leaf_count": 32,
        "ordered_leaf_list_sha256": canonical_sha([row["id"] for row in base["leaves"]]),
        "ordered_leaf_records_sha256": canonical_sha(base["leaves"]),
        "unchanged_protocol_fields": invariant_fields,
        "allowed_changes": {
            "run_id": {"from": base["run_id"], "to": RUN_ID},
            "expected_leaf_count": {"from": None, "to": 32, "reason": "current runner preflight"},
            "input_sha256.scripts/build_sequential_frontier_sweep.py": {
                "from": base["input_sha256"]["scripts/build_sequential_frontier_sweep.py"],
                "to": retry["input_sha256"]["scripts/build_sequential_frontier_sweep.py"],
            },
            "input_sha256.scripts/run_sequential_frontier_sweep.py": {
                "from": base["input_sha256"]["scripts/run_sequential_frontier_sweep.py"],
                "to": retry["input_sha256"]["scripts/run_sequential_frontier_sweep.py"],
                "reason": "registration-repaired checkout compatibility",
            },
            "input_sha256.artifacts/portfolio/frontier-manifest-v1.json": {
                "from": original_portfolio_path,
                "to": frozen_portfolio_path,
                "sha256": expected_portfolio_sha,
                "reason": "retain the rejected job's audited 15/47 frontier binding despite later local ledger artifacts",
            },
        },
        "claim_limit": "This audit proves retry protocol identity, not a solver or mathematical result.",
    }
    AUDIT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(OUT), "sha256": sha(OUT), "audit": str(AUDIT)}, sort_keys=True))


if __name__ == "__main__":
    main()
