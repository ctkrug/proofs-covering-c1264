#!/usr/bin/env python3
"""Freeze and validate the exact t-16, t-17, s-r0-1 review tranche."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = Path("artifacts/portfolio/frontier-manifest-v1.json")
SNAPSHOT = Path("artifacts/portfolio/frontier-manifest-32of47-seven-orbit-snapshot.json")
INDEX = Path("artifacts/classification/exhaustive-link-v1/certificate-index-32of47.json")
OUTPUT = Path("artifacts/experiments/sequential-three-case-review-v7-20260722/manifest.json")
SELECTED = ["t-16", "t-17", "s-r0-1"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(manifest: dict[str, object], portfolio: dict[str, object], index: dict[str, object],
             portfolio_path: Path = PORTFOLIO) -> None:
    if manifest.get("run_id") != "sequential-three-case-review-v7-20260722":
        raise ValueError("unexpected run ID")
    if manifest.get("method") != "sequential" or manifest.get("seconds_per_run") != 60:
        raise ValueError("method or cap changed")
    leaf_ids = [row["id"] for row in manifest.get("leaves", [])]
    if leaf_ids != SELECTED or manifest.get("expected_leaf_count") != 3:
        raise ValueError("exact three-case order changed")
    if index["status"] != "valid" or index["manifest"]["sha256"] != sha(ROOT / portfolio_path):
        raise ValueError("certificate index is stale")
    closed = set(index["closed_node_ids"])
    if closed != {row["id"] for row in portfolio["nodes"] if row["final_coverage_status"] != "open"}:
        raise ValueError("certificate index is incomplete")
    overlap = closed & set(leaf_ids)
    if overlap:
        raise ValueError(f"manifest overlaps durable certificates: {sorted(overlap)}")
    nodes = {row["id"]: row for row in portfolio["nodes"]}
    if any(nodes[node_id]["final_coverage_status"] != "open" for node_id in leaf_ids):
        raise ValueError("selected node is not open")
    active = portfolio["active_link_blocker"]
    if manifest.get("blocking_cnf") != active["path"]:
        raise ValueError("manifest uses a stale blocker")
    if manifest["input_sha256"].get(active["path"]) != active["sha256"] or sha(ROOT / active["path"]) != active["sha256"]:
        raise ValueError("active blocker hash mismatch")
    if manifest.get("frontier_definition_sha256") != portfolio["frontier_definition_sha256"]:
        raise ValueError("frontier definition hash mismatch")
    if manifest.get("frontier_source_sha256") != portfolio["frontier_source"]["sha256"]:
        raise ValueError("frontier source hash mismatch")
    if set(manifest.get("preserved_certified_nodes", [])) != closed:
        raise ValueError("preserved certificate set is incomplete")
    snapshot = manifest["portfolio_snapshot"]
    if snapshot["path"] != str(SNAPSHOT) or snapshot["sha256"] != sha(ROOT / SNAPSHOT):
        raise ValueError("portfolio snapshot binding mismatch")
    if manifest["certificate_index"]["sha256"] != sha(ROOT / INDEX):
        raise ValueError("certificate index hash mismatch")


def build(portfolio_path: Path = PORTFOLIO, write_snapshot: bool = True) -> dict[str, object]:
    portfolio = json.loads((ROOT / portfolio_path).read_text())
    index = json.loads((ROOT / INDEX).read_text())
    if portfolio["counts"] != {"total": 47, "closed": 32, "open": 15} or portfolio["frontier_revision"] != 3:
        raise ValueError("portfolio is not at the audited 32/47 seven-orbit checkpoint")
    if write_snapshot:
        (ROOT / SNAPSHOT).write_text(json.dumps(portfolio, indent=2, sort_keys=True) + "\n")
    nodes = {row["id"]: row for row in portfolio["nodes"]}
    leaves = []
    for priority, node_id in enumerate(SELECTED, 1):
        node = nodes[node_id]
        leaf = {key: node[key] for key in ("id", "kind", "root_index", "secondary_index", "tertiary_index", "inherited_result_sha256")}
        leaf.update({"priority": priority,
                     "priority_basis": "stale new-orbit leaf under active blocker" if node_id.startswith("t-") else "sole never-measured active-frontier node"})
        leaves.append(leaf)
    blocker, catalog = (Path(portfolio[key]["path"]) for key in ("active_link_blocker", "active_link_catalog"))
    inputs = [SNAPSHOT, INDEX, Path("scripts/build_three_case_review_tranche.py"),
              Path("scripts/run_sequential_frontier_sweep.py"), Path("scripts/run_cardinality_encoding_benchmark.py"),
              Path("checkers/audit_cardinality_encoding_cnf.py"), Path("checkers/replay_drat.py"),
              blocker, catalog, Path(portfolio["frontier_source"]["path"]), Path("toolchains/drat-trim/drat-trim")]
    value = {
        "schema_version": 3,
        "expected_leaf_count": 3,
        "run_id": "sequential-three-case-review-v7-20260722",
        "hypothesis": "The two stale orbit-discovery leaves close under the seven-orbit blocker and the sole never-measured leaf yields a decisive result at the existing cap.",
        "success_rule": "Count only reconstructed-CNF, independently replayed UNSAT receipts; any validated new orbit stops the tranche and forces catalogue/frontier rebuild.",
        "selection_basis": "Exactly t-16, t-17, and s-r0-1; disjoint from the complete 32-certificate index.",
        "method": "sequential", "seconds_per_run": 60, "cold_runs": True,
        "run_order": "t-16, t-17, s-r0-1", "maximum_solver_cpu_seconds": 180,
        "maximum_projected_proof_bytes": 5_000_000_000,
        "blocking_cnf": str(blocker), "catalog": str(catalog), "solver": "/usr/bin/cadical",
        "solver_environment_gate": "live host /usr/bin/cadical SHA-256 7b73df0a6d9cf3c751a1948300e5baff8e82c4d39bcd88f0c063b5f5cfb8b33e",
        "drat_trim": "toolchains/drat-trim/drat-trim",
        "frontier_summary": portfolio["frontier_source"]["path"],
        "frontier_source_sha256": portfolio["frontier_source"]["sha256"],
        "frontier_definition_sha256": portfolio["frontier_definition_sha256"],
        "portfolio_snapshot": {"path": str(SNAPSHOT), "sha256": sha(ROOT / SNAPSHOT)},
        "portfolio_manifest_sha256": sha(ROOT / SNAPSHOT),
        "certificate_index": {"path": str(INDEX), "sha256": sha(ROOT / INDEX)},
        "preserved_certified_nodes": sorted(index["closed_node_ids"]),
        "leaves": leaves,
        "input_sha256": {str(path): sha(ROOT / path) for path in inputs},
        "incident_policy": "The rejected original t-16 residual proof remains an incident only; valid structural evidence uses the external replacement receipt indexed in the certificate index.",
        "claim_limit": "This three-case frontier tranche cannot establish exhaustive link classification without 47/47 closure or another validated orbit and rebuilt audit chain.",
    }
    validate(value, portfolio, index, portfolio_path)
    return value


def main() -> None:
    value = build()
    output = ROOT / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"built exact three-case tranche: {OUTPUT}")


if __name__ == "__main__":
    main()
