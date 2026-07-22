#!/usr/bin/env python3
"""Build the hash-bound short-cap sequential sweep over the 44 open nodes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/experiments/sequential-open-frontier-44-20260722/manifest.json"
PORTFOLIO = ROOT / "artifacts/portfolio/frontier-manifest-v1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    portfolio = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
    closed = sorted(row["id"] for row in portfolio["nodes"] if row["final_coverage_status"] != "open")
    if closed != ["s-r0-6", "s-r1-5", "s-r1-8"]:
        raise ValueError(f"unexpected certified predecessor coverage: {closed}")
    leaves = [{key: row[key] for key in (
        "id", "kind", "root_index", "secondary_index", "tertiary_index", "inherited_result_sha256"
    )} for row in portfolio["nodes"] if row["final_coverage_status"] == "open"]
    leaves.sort(key=lambda row: (
        0 if row["kind"] == "secondary" else 1,
        int(row["root_index"]), int(row["secondary_index"]),
        -1 if row["tertiary_index"] is None else int(row["tertiary_index"]),
    ))
    if len(leaves) != 44 or len({row["id"] for row in leaves}) != 44:
        raise ValueError("sweep must bind exactly the 44 currently open nodes")
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
        Path("artifacts/pilot/link-orbit-catalog-4.json"),
        Path("artifacts/pilot/link-orbit-catalog-4-blocking.cnf"),
        Path("artifacts/pilot/link-root-0-secondary-partition.json"),
        Path("artifacts/pilot/link-root-1-secondary-partition.json"),
        Path("artifacts/pilot/link-root0-secondary0-tertiary-partition.json"),
        Path("toolchains/drat-trim/drat-trim"),
        Path("toolchains/drat-trim/PROVENANCE.md"),
        Path("requirements-pilot-lock.txt"),
    ]
    return {
        "schema_version": 1,
        "run_id": "sequential-open-frontier-44-20260722",
        "predecessor": {
            "run_id": "cardinality-encoding-20-leaf-20260722",
            "rule": "finish and review unchanged before this live-host sweep starts",
        },
        "hypothesis": "A uniform short-cap sequential pass over every currently open canonical node will cheaply harvest at least one net-new replay-verified closure and measure the hard tail without committing to a uniform timeout increase.",
        "success_rule": "Retain every net-new closure whose reconstructed CNF audit and DRAT replay pass; UNKNOWN is a measured survivor, not evidence of satisfiability.",
        "selection_basis": "All and only the 44 nodes still open after preserving three fresh sequential certificates; already certified nodes are excluded to avoid duplicate compute.",
        "method": "sequential",
        "seconds_per_run": 60,
        "cold_runs": True,
        "run_order": "all secondary nodes in canonical order, then all tertiary nodes in canonical order; no solver state is reused",
        "maximum_solver_cpu_seconds": 2640,
        "maximum_projected_proof_bytes": 20_000_000_000,
        "blocking_cnf": "artifacts/pilot/link-orbit-catalog-4-blocking.cnf",
        "catalog": "artifacts/pilot/link-orbit-catalog-4.json",
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
