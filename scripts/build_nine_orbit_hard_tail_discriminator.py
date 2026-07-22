#!/usr/bin/env python3
"""Freeze the exact three-case nine-orbit hard-tail discriminator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = Path("artifacts/portfolio/frontier-manifest-v1.json")
SNAPSHOT = Path("artifacts/portfolio/frontier-manifest-32of47-nine-orbit-hard-tail-snapshot.json")
INDEX = Path("artifacts/classification/exhaustive-link-v1/certificate-index-32of47.json")
ANALYSIS = Path("artifacts/classification/exhaustive-link-v1/nine-orbit-timeout-hard-tail-analysis.json")
OUTPUT = Path("artifacts/experiments/sequential-hard-tail-discriminator-v9-20260722/manifest.json")
DESIGN = Path("artifacts/experiments/sequential-hard-tail-discriminator-v9-20260722/lab-efficiency-design.json")
SELECTED = ["s-r0-1", "s-r1-15", "t-10"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(value: dict[str, object], portfolio: dict[str, object], index: dict[str, object],
             portfolio_path: Path = PORTFOLIO) -> None:
    if value["run_id"] != "sequential-hard-tail-discriminator-v9-20260722":
        raise ValueError("unexpected run ID")
    if value["method"] != "sequential" or value["seconds_per_run"] != 60:
        raise ValueError("method or cap changed")
    if [row["id"] for row in value["leaves"]] != SELECTED:
        raise ValueError("exact three-case order changed")
    if portfolio["counts"] != {"total": 47, "closed": 32, "open": 15} or portfolio["frontier_revision"] != 4:
        raise ValueError("not the audited 32/47 nine-orbit checkpoint")
    if index["manifest"]["sha256"] != sha(ROOT / portfolio_path):
        raise ValueError("certificate index is stale")
    closed = set(index["closed_node_ids"])
    if closed & set(SELECTED):
        raise ValueError("selected discriminator overlaps durable certificates")
    nodes = {row["id"]: row for row in portfolio["nodes"]}
    if any(nodes[node_id]["final_coverage_status"] != "open" for node_id in SELECTED):
        raise ValueError("selected discriminator contains a non-open node")
    active = portfolio["active_link_blocker"]
    if value["blocking_cnf"] != active["path"] or value["input_sha256"][active["path"]] != active["sha256"]:
        raise ValueError("active blocker binding mismatch")
    if sha(ROOT / active["path"]) != active["sha256"]:
        raise ValueError("active blocker bytes changed")
    if value["frontier_definition_sha256"] != portfolio["frontier_definition_sha256"]:
        raise ValueError("frontier definition mismatch")
    if value["portfolio_snapshot"]["sha256"] != sha(ROOT / SNAPSHOT):
        raise ValueError("portfolio snapshot mismatch")
    if value["certificate_index"]["sha256"] != sha(ROOT / INDEX):
        raise ValueError("certificate index mismatch")
    if set(value["preserved_certified_nodes"]) != closed:
        raise ValueError("preserved certificate set is incomplete")


def build() -> dict[str, object]:
    portfolio = json.loads((ROOT / PORTFOLIO).read_text())
    index = json.loads((ROOT / INDEX).read_text())
    analysis = json.loads((ROOT / ANALYSIS).read_text())
    if portfolio["counts"] != {"total": 47, "closed": 32, "open": 15} or portfolio["frontier_revision"] != 4:
        raise ValueError("the frozen discriminator can only be built from its audited 32/47 checkpoint")
    if analysis["hard_tail_size"] != 12 or analysis["global_ledger"] != "32/47":
        raise ValueError("hard-tail analysis is stale")
    (ROOT / SNAPSHOT).write_text(json.dumps(portfolio, indent=2, sort_keys=True) + "\n")
    nodes = {row["id"]: row for row in portfolio["nodes"]}
    basis = {
        "s-r0-1": "root-0 secondary; shortest earlier-prefix representative",
        "s-r1-15": "root-1 secondary; opposite-root representative",
        "t-10": "tertiary representative of the distinct hard-tail class",
    }
    leaves = []
    for priority, node_id in enumerate(SELECTED, 1):
        node = nodes[node_id]
        leaves.append({key: node[key] for key in (
            "id", "kind", "root_index", "secondary_index", "tertiary_index", "inherited_result_sha256"
        )} | {"priority": priority, "priority_basis": basis[node_id]})
    blocker = Path(portfolio["active_link_blocker"]["path"])
    catalog = Path(portfolio["active_link_catalog"]["path"])
    inputs = [SNAPSHOT, INDEX, ANALYSIS, Path("scripts/build_nine_orbit_hard_tail_discriminator.py"),
              Path("scripts/run_sequential_frontier_sweep.py"), Path("scripts/run_cardinality_encoding_benchmark.py"),
              Path("checkers/audit_cardinality_encoding_cnf.py"), Path("checkers/replay_drat.py"), blocker, catalog,
              Path(portfolio["frontier_source"]["path"]), Path("toolchains/drat-trim/drat-trim")]
    value = {
        "schema_version": 3,
        "run_id": "sequential-hard-tail-discriminator-v9-20260722",
        "expected_leaf_count": 3,
        "hypothesis": "The strengthened nine-orbit blocker separates at least one structural hard-tail class at the unchanged short cap.",
        "success_rule": "A reconstructed-CNF, externally replayed UNSAT is net-new closure; a directly validated SAT link triggers immediate catalogue rebuild; timeout is class evidence only.",
        "selection_basis": "One root-0 secondary, one root-1 secondary, and one tertiary timeout; exactly the predeclared structural discriminator.",
        "method": "sequential", "seconds_per_run": 60, "cold_runs": True,
        "run_order": ", ".join(SELECTED), "maximum_solver_cpu_seconds": 180,
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
        "hard_tail_analysis": {"path": str(ANALYSIS), "sha256": sha(ROOT / ANALYSIS)},
        "preserved_certified_nodes": sorted(index["closed_node_ids"]),
        "leaves": leaves,
        "input_sha256": {str(path): sha(ROOT / path) for path in inputs},
        "claim_limit": "Three-case hard-tail discrimination only; no exhaustive-classification or exact-value claim.",
    }
    validate(value, portfolio, index)
    return value


def main() -> None:
    value = build()
    output = ROOT / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    design = {
        "naive_cost": "A generic pass over all 12 hard-tail nodes would spend up to 720 solver-seconds before review.",
        "opportunities_considered": ["uniform timeout increase", "generic alternative encoding", "three-class sequential discriminator"],
        "chosen_reductions": "Exactly three structurally distinct representatives at the unchanged 60-second cap.",
        "expected_throughput_gain": "Measures blocker sensitivity and class behavior using 25% of a full hard-tail sweep.",
        "soundness_basis": "Hash-bound nine-orbit blocker/frontier and complete 32-certificate disjointness gate; independent audit required for every decisive result.",
        "remains_uncompressed": "Nine-node hard tail and catalogue exhaustion remain after this discriminator.",
    }
    (ROOT / DESIGN).write_text(json.dumps(design, indent=2, sort_keys=True) + "\n")
    print(f"built exact hard-tail discriminator: {OUTPUT}")


if __name__ == "__main__":
    main()
