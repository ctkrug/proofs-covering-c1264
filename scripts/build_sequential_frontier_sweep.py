#!/usr/bin/env python3
"""Build the hash-bound short-cap sequential sweep over the current open nodes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/experiments/sequential-open-frontier-32-v5-20260722/manifest.json"
PORTFOLIO = ROOT / "artifacts/portfolio/frontier-manifest-v1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    portfolio = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
    closed = sorted(row["id"] for row in portfolio["nodes"] if row["final_coverage_status"] != "open")
    if len(closed) != portfolio["counts"]["closed"]:
        raise ValueError("certified predecessor count disagrees with the portfolio")
    leaves = []
    for row in portfolio["nodes"]:
        if row["final_coverage_status"] != "open":
            continue
        inherited = json.loads((ROOT / row["source_path"] / "result.json").read_text())
        prior = next((outcome for outcome in row["outcomes"] if outcome.get("method") == "sequential"), None)
        if row["id"] == "s-r1-3":
            tier, reason = 0, "fifth-orbit/tree-invariant case; predecessor run discovered the now-blocked orbit"
        elif prior is None:
            tier, reason = 1, "unmeasured by sequential; prioritize smaller inherited CNF"
        else:
            tier, reason = 2, "predecessor-blocker short-cap survivor; rerun is justified only by the stronger five-orbit blocker"
        leaf = {key: row[key] for key in (
            "id", "kind", "root_index", "secondary_index", "tertiary_index", "inherited_result_sha256"
        )}
        leaf["priority_basis"] = reason
        leaf["inherited_variables"] = inherited.get("variables")
        leaf["inherited_clauses"] = inherited.get("clauses")
        leaf["prior_sequential_runtime_seconds"] = None if prior is None else prior["runtime_seconds"]
        leaf["_tier"] = tier
        leaves.append(leaf)
    leaves.sort(key=lambda row: (
        row["_tier"], row["inherited_clauses"] or 10**18,
        row["prior_sequential_runtime_seconds"] or 0, row["id"],
    ))
    for priority, row in enumerate(leaves, 1):
        row["priority"] = priority
        row.pop("_tier")
    if len(leaves) != 32 or len({row["id"] for row in leaves}) != len(leaves):
        raise ValueError("replacement sweep must bind exactly the 32 audited open nodes")
    inputs = [
        Path("scripts/build_sequential_frontier_sweep.py"),
        Path("scripts/run_sequential_frontier_sweep.py"),
        Path("scripts/profile_sequential_survivors.py"),
        Path("scripts/run_cardinality_encoding_benchmark.py"),
        Path("checkers/audit_cardinality_encoding_cnf.py"),
        Path("scripts/find_next_link_orbit.py"),
        Path("scripts/analyze_link_orbit.py"),
        Path("checkers/replay_drat.py"),
        Path("artifacts/portfolio/frontier-manifest-v1.json"),
        Path("artifacts/pilot/link-campaign-summary.json"),
        Path("artifacts/discoveries/link-orbit-catalog-5.json"),
        Path("artifacts/discoveries/link-orbit-catalog-5-blocking.cnf"),
        Path("artifacts/pilot/link-root-0-secondary-partition.json"),
        Path("artifacts/pilot/link-root-1-secondary-partition.json"),
        Path("artifacts/pilot/link-root0-secondary0-tertiary-partition.json"),
        Path("toolchains/drat-trim/drat-trim"),
        Path("toolchains/drat-trim/PROVENANCE.md"),
        Path("requirements-pilot-lock.txt"),
    ]
    return {
        "schema_version": 1,
        "run_id": "sequential-open-frontier-32-v5-20260722",
        "predecessor": {
            "run_id": "cardinality-encoding-20-leaf-20260722",
            "rule": "finish and review unchanged before this live-host sweep starts",
        },
        "hypothesis": "A uniform short-cap sequential pass over every currently open canonical node will cheaply harvest at least one net-new replay-verified closure and measure the hard tail without committing to a uniform timeout increase.",
        "success_rule": "Retain every net-new closure whose reconstructed CNF audit and DRAT replay pass; UNKNOWN is a measured survivor, not evidence of satisfiability.",
        "selection_basis": "All 32 audited open nodes. The 15 transferred closures are excluded. Five predecessor-blocker survivors may be remeasured because the active blocker gained the newly discovered orbit; this is not a symmetry rerun.",
        "method": "sequential",
        "seconds_per_run": 60,
        "cold_runs": True,
        "run_order": "s-r1-3 structural discriminator first; then sequential-unmeasured nodes by inherited CNF size; predecessor-blocker short-cap survivors last; no solver state is reused",
        "maximum_solver_cpu_seconds": 60 * len(leaves),
        "maximum_projected_proof_bytes": 20_000_000_000,
        "blocking_cnf": "artifacts/discoveries/link-orbit-catalog-5-blocking.cnf",
        "catalog": "artifacts/discoveries/link-orbit-catalog-5.json",
        "solver": "/usr/bin/cadical",
        "drat_trim": "toolchains/drat-trim/drat-trim",
        "frontier_summary": "artifacts/pilot/link-campaign-summary.json",
        "portfolio_manifest_sha256": sha(PORTFOLIO),
        "preserved_certified_nodes": closed,
        "leaves": leaves,
        "input_sha256": {str(path): sha(ROOT / path) for path in inputs},
        "claim_limit": "This tranche can add replayed local closures only. A global exclusion still requires 47/47 valid closures and independent frontier coverage validation.",
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    value = build()
    OUT.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"built {len(value['leaves'])}-node sequential sweep: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
