#!/usr/bin/env python3
"""Independently validate the C(12,6,4) portfolio ledger and closure claims."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("artifacts/portfolio/frontier-manifest-v1.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def expected_nodes(summary: dict) -> dict[str, dict]:
    expected = {}
    for row in summary["open_secondary_cases"]:
        ident = f"s-r{row['root_index']}-{row['secondary_index']}"
        expected[ident] = {"kind": "secondary", "root_index": row["root_index"],
            "secondary_index": row["secondary_index"], "tertiary_index": None,
            "source_path": row["path"], "inherited_result_sha256": row["result_sha256"]}
    for row in summary["open_tertiary_cases"]:
        ident = f"t-{row['tertiary_index']}"
        expected[ident] = {"kind": "tertiary", "root_index": row["root_index"],
            "secondary_index": row["secondary_index"], "tertiary_index": row["tertiary_index"],
            "source_path": row["path"], "inherited_result_sha256": row["result_sha256"]}
    return expected


def verify(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    assert manifest["global_uncertainty"] == "C(12,6,4) is 40 or 41"
    assert manifest["resolution_status"] in {"open", "settled_40", "settled_41"}
    routes = manifest["active_resolution_routes"]
    assert routes["forced_matching_exact_degree_40_block_witness"]["status"] in {"active", "held", "complete"}
    assert routes["canonical_47_node_certified_exclusion"]["status"] in {"active", "held", "complete"}
    for binding in ("policy", "frontier_source", "first_measurement"):
        path = ROOT / manifest[binding]["path"]
        assert digest(path) == manifest[binding]["sha256"], f"{binding} hash mismatch"
    if "dynamic_assignment" in manifest:
        assignment_path = ROOT / manifest["dynamic_assignment"]["path"]
        assert digest(assignment_path) == manifest["dynamic_assignment"]["sha256"], "dynamic assignment hash mismatch"
        assignment = json.loads(assignment_path.read_text())
        assert assignment["active_blocker_sha256"] == manifest["active_link_blocker"]["sha256"]
        assert assignment["open_nodes"] == manifest["counts"]["open"]
    summary = json.loads((ROOT / manifest["frontier_source"]["path"]).read_text())
    expected = expected_nodes(summary)
    assert len(expected) == 47 and summary["open_frontier_count"] == 47
    nodes = manifest["nodes"]
    assert len(nodes) == 47 and len({row["id"] for row in nodes}) == 47
    assert set(expected) == {row["id"] for row in nodes}
    for row in nodes:
        if manifest.get("frontier_revision", 1) >= 2:
            assert row.get("active_blocker_sha256") == manifest["active_link_blocker"]["sha256"]
        for key, value in expected[row["id"]].items():
            assert row[key] == value, f"{row['id']} {key} disagrees with frontier source"
        assert isinstance(row["assigned_methods"], list)
        assert isinstance(row["outcomes"], list)
        assert row["final_coverage_status"] in {"open", "closed_unsat", "closed_sat"}
        for outcome in row["outcomes"]:
            assert outcome.get("method") in row["assigned_methods"]
            assert isinstance(outcome.get("runtime_seconds"), (int, float))
            assert isinstance(outcome.get("cpu_seconds"), (int, float))
            assert outcome.get("cnf_encoding_revision")
            if outcome.get("status") == "unsat_certified":
                for key in ("cnf_sha256", "proof_sha256", "replay_receipt", "independent_audit_receipt"):
                    assert outcome.get(key), f"certified UNSAT outcome missing {key}"
            elif outcome.get("status") == "sat_validated":
                assert outcome.get("direct_cover_receipt") and outcome.get("canonicalization_receipt")
            else:
                assert outcome.get("status") in {"unknown", "provisional_unsat", "provisional_sat", "error"}
            for receipt_key in (
                "result_receipt", "replay_receipt", "independent_audit_receipt",
                "post_tranche_independent_replay_receipt",
            ):
                receipt = outcome.get(receipt_key)
                if receipt:
                    assert digest(ROOT / receipt["path"]) == receipt["sha256"], f"{receipt_key} hash mismatch"
        if row["final_coverage_status"] == "closed_unsat":
            assert any(x.get("status") == "unsat_certified" for x in row["outcomes"])
        if row["final_coverage_status"] == "closed_sat":
            assert any(x.get("status") == "sat_validated" for x in row["outcomes"])

    closed = sum(row["final_coverage_status"] != "open" for row in nodes)
    assert manifest["counts"] == {"total": 47, "closed": closed, "open": 47 - closed}
    cumulative = []
    for tranche in manifest["tranches"]:
        if "source_results" in tranche:
            assert len(tranche["source_results"]) == tranche["completed_solver_runs"]
            for source in tranche["source_results"]:
                assert digest(ROOT / source["path"]) == source["sha256"], "tranche result hash mismatch"
        else:
            source = tranche["source_checkpoint"]
            assert digest(ROOT / source["path"]) == source["sha256"], "tranche checkpoint hash mismatch"
        tranche_closed = int(tranche["cumulative_closed_out_of_47"].split("/", 1)[0])
        assert tranche["cumulative_closed_out_of_47"].endswith("/47") and tranche_closed <= closed
        cumulative.append(tranche_closed)
    assert cumulative == sorted(cumulative) and (not cumulative or cumulative[-1] == closed)
    identity = [{key: row[key] for key in ("id", "kind", "root_index", "secondary_index",
        "tertiary_index", "source_path", "inherited_result_sha256")} for row in nodes]
    assert canonical_hash(identity) == manifest["frontier_definition_sha256"]
    payload = dict(manifest)
    recorded = payload.pop("manifest_payload_sha256")
    assert canonical_hash(payload) == recorded, "manifest payload hash mismatch"

    benchmark = json.loads((ROOT / manifest["first_measurement"]["path"]).read_text())
    benchmark_ids = {row["id"] for row in benchmark["leaves"]}
    assert len(benchmark_ids) == 20 and benchmark_ids <= set(expected)
    for row in nodes:
        if row["id"] in benchmark_ids:
            assert row["assigned_methods"][:2] == ["sequential", "kmtotalizer"]
    print(f"PASS: {closed}/47 certified closures; frontier, bindings, and payload hash verified")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    verify(path)


if __name__ == "__main__":
    main()
