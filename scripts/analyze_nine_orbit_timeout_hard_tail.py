#!/usr/bin/env python3
"""Compare the twelve genuine timeout leaves after the nine-orbit rebuild."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("artifacts/portfolio/frontier-manifest-v1.json")
OUTPUT = Path("artifacts/classification/exhaustive-link-v1/nine-orbit-timeout-hard-tail-analysis.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    manifest = json.loads((ROOT / MANIFEST).read_text())
    active = manifest["active_link_blocker"]
    rows = []
    for node in manifest["nodes"]:
        if node["final_coverage_status"] != "open":
            continue
        outcomes = [row for row in node["outcomes"] if row.get("status") == "unknown"]
        if any(row.get("status") == "provisional_sat" for row in node["outcomes"]):
            continue
        sequential = [row for row in outcomes if row.get("method") == "sequential"]
        if not sequential:
            raise ValueError(f"timeout leaf lacks sequential measurement: {node['id']}")
        outcome = sequential[-1]
        result_path = Path(outcome["result_receipt"]["path"])
        build_path = result_path.with_name("build.json")
        result = json.loads((ROOT / result_path).read_text())
        build_record = json.loads((ROOT / build_path).read_text())
        if result["status"] != "UNKNOWN" or result["seconds_cap"] != 60:
            raise ValueError(f"not a fixed-cap timeout: {node['id']}")
        rows.append({
            "id": node["id"],
            "kind": node["kind"],
            "root_index": node["root_index"],
            "secondary_index": node["secondary_index"],
            "tertiary_index": node["tertiary_index"],
            "runtime_seconds": outcome["runtime_seconds"],
            "sequential_variables": build_record["variables"],
            "sequential_clauses": build_record["clauses"],
            "tail_clause_count": build_record["tail_clause_count"],
            "earlier_primary_units": build_record["root"]["earlier_primary_units"],
            "earlier_secondary_units": build_record["root"]["earlier_secondary_units"],
            "earlier_tertiary_units": build_record["root"]["earlier_tertiary_units"],
            "non_cardinality_core_sha256": build_record["non_cardinality_core_sha256"],
            "blocker_sha256_at_measurement": build_record["blocker_sha256"],
            "blocker_clauses_at_measurement": build_record["root"]["blocker_clause_count"],
            "active_blocker_sha256": active["sha256"],
            "active_blocker_clauses": 3776,
            "additional_active_blocker_clauses": 3776 - build_record["root"]["blocker_clause_count"],
            "kmtotalizer_also_timed_out": any(row.get("method") == "kmtotalizer" for row in outcomes),
            "result": {"path": str(result_path), "sha256": sha(ROOT / result_path)},
            "build": {"path": str(build_path), "sha256": sha(ROOT / build_path)},
        })
    rows.sort(key=lambda row: row["id"])
    if len(rows) != 12:
        raise ValueError(f"expected twelve genuine timeout leaves, found {len(rows)}")
    selected = ["s-r0-1", "s-r1-15", "t-10"]
    if not set(selected) <= {row["id"] for row in rows}:
        raise ValueError("discriminator representatives are not all in the hard tail")
    return {
        "schema_version": 1,
        "status": "valid-structural-comparison",
        "manifest": {"path": str(MANIFEST), "sha256": sha(ROOT / MANIFEST)},
        "global_ledger": "32/47",
        "hard_tail_size": 12,
        "summary": {
            "by_kind": dict(sorted(Counter(row["kind"] for row in rows).items())),
            "by_root": dict(sorted(Counter(str(row["root_index"]) for row in rows).items())),
            "measurement_blocker_clause_counts": dict(sorted(Counter(str(row["blocker_clauses_at_measurement"]) for row in rows).items())),
            "measured_under_active_nine_orbit_blocker": sum(row["blocker_sha256_at_measurement"] == active["sha256"] for row in rows),
            "paired_kmtotalizer_timeouts": sum(row["kmtotalizer_also_timed_out"] for row in rows),
            "distinct_non_cardinality_cores": len({row["non_cardinality_core_sha256"] for row in rows}),
        },
        "nodes": rows,
        "selected_discriminator": {
            "status": "predeclared_not_launched",
            "ordered_nodes": selected,
            "method": "sequential",
            "seconds_per_run": 60,
            "active_blocker_sha256": active["sha256"],
            "purpose": "Stratified same-method test of blocker sensitivity: root-0 secondary measured under seven orbits, root-1 secondary measured under seven orbits, and tertiary measured under four orbits.",
            "interpretation": {
                "two_or_more_closures": "The stronger blocker is the useful discriminator; target remaining cases by blocker delta and structural class.",
                "zero_closures": "Solver-search hardness persists across classes; move to a bounded structural cubing discriminator rather than raising all caps.",
                "new_orbit": "Stop immediately, validate the witness, and rebuild the catalog/frontier again.",
            },
            "launch_gate": "Hold until the newly discovered eighth and ninth orbits receive direct fixed-link residual extension tests; either SAT extension would supersede frontier work.",
        },
        "allocation": {
            "kmtotalizer": "demoted; four paired hard-tail timeouts and no unique certified coverage",
            "constructive": "parked absent a concrete nonlocal move; direct residual extension checks for the two new orbits are validation, not generic local search",
        },
        "claim_limit": "Structural comparison and experiment selection only; it creates no new closure and does not establish exhaustive link classification.",
    }


def main() -> None:
    value = build()
    output = ROOT / OUTPUT
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"hard_tail_size": value["hard_tail_size"], "summary": value["summary"],
                      "selected": value["selected_discriminator"]["ordered_nodes"]}, sort_keys=True))


if __name__ == "__main__":
    main()
