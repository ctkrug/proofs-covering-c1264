#!/usr/bin/env python3
"""Freeze the audited active ledger and bind only never-measured sequential leaves."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = Path("artifacts/portfolio/frontier-manifest-v1.json")
SNAPSHOT = Path("artifacts/portfolio/frontier-manifest-26of47-seven-orbit-snapshot.json")
OUTPUT = Path("artifacts/experiments/sequential-unmeasured-frontier-12-v7-20260722/manifest.json")
ASSIGNMENT = Path("artifacts/portfolio/seven-orbit-dynamic-assignment.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(manifest: dict[str, object], portfolio: dict[str, object]) -> None:
    """Fail closed before a frozen tranche can be submitted or executed."""
    snapshot = manifest.get("portfolio_snapshot", {})
    if not isinstance(snapshot, dict):
        raise ValueError("missing portfolio snapshot binding")
    snapshot_path = ROOT / str(snapshot.get("path", ""))
    if not snapshot_path.is_file() or snapshot.get("sha256") != sha(snapshot_path):
        raise ValueError("portfolio snapshot hash mismatch")
    if manifest.get("portfolio_manifest_sha256") != snapshot.get("sha256"):
        raise ValueError("portfolio manifest binding mismatch")

    active = portfolio["active_link_blocker"]
    blocker_path = str(active["path"])
    if manifest.get("blocking_cnf") != blocker_path:
        raise ValueError("manifest uses a superseded blocker")
    inputs = manifest.get("input_sha256", {})
    if not isinstance(inputs, dict) or inputs.get(blocker_path) != active["sha256"]:
        raise ValueError("active blocker hash is absent or stale")
    if sha(ROOT / blocker_path) != active["sha256"]:
        raise ValueError("active blocker file hash mismatch")

    nodes = {row["id"]: row for row in portfolio["nodes"]}
    leaf_ids = [row["id"] for row in manifest.get("leaves", [])]
    if len(leaf_ids) != len(set(leaf_ids)):
        raise ValueError("manifest contains duplicate nodes")
    unknown = set(leaf_ids) - set(nodes)
    if unknown:
        raise ValueError(f"manifest contains unknown nodes: {sorted(unknown)}")
    certified = {
        node_id for node_id, row in nodes.items()
        if row["final_coverage_status"] != "open"
    }
    overlap = set(leaf_ids) & certified
    if overlap:
        raise ValueError(f"manifest contains already-certified nodes: {sorted(overlap)}")
    if set(manifest.get("preserved_certified_nodes", [])) != certified:
        raise ValueError("preserved certified-node set is incomplete")


def build() -> dict[str, object]:
    portfolio = json.loads((ROOT / PORTFOLIO).read_text(encoding="utf-8"))
    if portfolio["counts"] != {"total": 47, "closed": 26, "open": 21}:
        raise ValueError("portfolio must be at the audited 26/47 seven-orbit checkpoint")
    if portfolio["frontier_revision"] != 3:
        raise ValueError("unexpected frontier revision")
    assignment = json.loads((ROOT / ASSIGNMENT).read_text(encoding="utf-8"))
    if portfolio.get("dynamic_assignment", {}).get("sha256") != sha(ROOT / ASSIGNMENT):
        raise ValueError("dynamic assignment hash mismatch")
    selected = {
        row["node_id"] for row in assignment["assignments"]
        if row["structural_class"] == "unmeasured_active_frontier"
    }
    leaves = []
    for node in portfolio["nodes"]:
        if node["id"] not in selected:
            continue
        inherited = json.loads((ROOT / node["source_path"] / "result.json").read_text(encoding="utf-8"))
        leaf = {key: node[key] for key in (
            "id", "kind", "root_index", "secondary_index", "tertiary_index", "inherited_result_sha256"
        )}
        leaf.update({
            "priority_basis": "never measured by sequential; ordered by inherited clause count",
            "inherited_variables": inherited.get("variables"),
            "inherited_clauses": inherited.get("clauses"),
            "prior_sequential_runtime_seconds": None,
        })
        leaves.append(leaf)
    leaves.sort(key=lambda row: (row["inherited_clauses"] or 10**18, row["id"]))
    for priority, leaf in enumerate(leaves, 1):
        leaf["priority"] = priority
    if len(leaves) != 12 or len({leaf["id"] for leaf in leaves}) != 12:
        raise ValueError("expected exactly 12 never-measured open leaves")

    snapshot_path = ROOT / SNAPSHOT
    snapshot_path.write_text(json.dumps(portfolio, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    catalog = Path(portfolio["active_link_catalog"]["path"])
    blocker = Path(portfolio["active_link_blocker"]["path"])
    inputs = [
        SNAPSHOT,
        ASSIGNMENT,
        Path("scripts/build_active_sequential_tranche.py"),
        Path("scripts/run_sequential_frontier_sweep.py"),
        Path("scripts/run_cardinality_encoding_benchmark.py"),
        Path("checkers/audit_cardinality_encoding_cnf.py"),
        Path("checkers/replay_drat.py"),
        catalog,
        blocker,
        Path("artifacts/pilot/link-campaign-summary.json"),
        Path("artifacts/pilot/link-root-0-secondary-partition.json"),
        Path("artifacts/pilot/link-root-1-secondary-partition.json"),
        Path("artifacts/pilot/link-root0-secondary0-tertiary-partition.json"),
        Path("toolchains/drat-trim/drat-trim"),
        Path("toolchains/drat-trim/PROVENANCE.md"),
        Path("requirements-pilot-lock.txt"),
    ]
    value = {
        "schema_version": 3,
        "expected_leaf_count": len(leaves),
        "run_id": "sequential-unmeasured-frontier-12-v7-20260722",
        "hypothesis": "The remaining never-measured leaves still offer the highest cheap certified-closure yield after the seven-orbit rebuild.",
        "success_rule": "Retain only reconstructed-CNF, independently replayed UNSAT closures; preserve catalogue-expanding SAT link witnesses as structural signals, not global closures.",
        "selection_basis": "Exactly the 12 audited open nodes with no prior sequential outcome; all 26 closures and nine measured open nodes are excluded.",
        "method": "sequential",
        "seconds_per_run": 60,
        "cold_runs": True,
        "run_order": "inherited clause count, then canonical node ID",
        "maximum_solver_cpu_seconds": 60 * len(leaves),
        "maximum_projected_proof_bytes": 20_000_000_000,
        "blocking_cnf": str(blocker),
        "catalog": str(catalog),
        "solver": "/usr/bin/cadical",
        "solver_environment_gate": "live host /usr/bin/cadical SHA-256 7b73df0a6d9cf3c751a1948300e5baff8e82c4d39bcd88f0c063b5f5cfb8b33e; every result records the observed solver hash",
        "drat_trim": "toolchains/drat-trim/drat-trim",
        "frontier_summary": "artifacts/pilot/link-campaign-summary.json",
        "portfolio_manifest_sha256": sha(snapshot_path),
        "portfolio_snapshot": {"path": str(SNAPSHOT), "sha256": sha(snapshot_path)},
        "preserved_certified_nodes": sorted(
            node["id"] for node in portfolio["nodes"] if node["final_coverage_status"] != "open"
        ),
        "leaves": leaves,
        "input_sha256": {str(path): sha(ROOT / path) for path in inputs},
        "claim_limit": "This tranche can add replayed local closures or validated link-orbit signals only; global exclusion still requires 47/47 and an independent frontier audit.",
    }
    validate(value, portfolio)
    return value


def main() -> None:
    value = build()
    output = ROOT / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"built {len(value['leaves'])}-node active sequential tranche: {OUTPUT}")


if __name__ == "__main__":
    main()
