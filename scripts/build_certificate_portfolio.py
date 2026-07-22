#!/usr/bin/env python3
"""Build the initial, hash-bound C(12,6,4) certificate-portfolio ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = Path("artifacts/pilot/link-campaign-summary.json")
BENCHMARK = Path("artifacts/experiments/cardinality-encoding-20-leaf-20260722/manifest.json")
POLICY = Path("docs/CERTIFICATE-PORTFOLIO-POLICY.json")
DEFAULT_OUTPUT = Path("artifacts/portfolio/frontier-manifest-v1.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def node_id(kind: str, row: dict) -> str:
    if kind == "secondary":
        return f"s-r{row['root_index']}-{row['secondary_index']}"
    return f"t-{row['tertiary_index']}"


def build() -> dict:
    summary = json.loads((ROOT / SUMMARY).read_text())
    benchmark = json.loads((ROOT / BENCHMARK).read_text())
    benchmark_ids = {row["id"] for row in benchmark["leaves"]}
    nodes = []
    for kind, key in (("secondary", "open_secondary_cases"), ("tertiary", "open_tertiary_cases")):
        for row in summary[key]:
            identity = {
                "id": node_id(kind, row),
                "kind": kind,
                "root_index": row["root_index"],
                "secondary_index": row["secondary_index"],
                "tertiary_index": row.get("tertiary_index"),
                "source_path": row["path"],
                "inherited_result_sha256": row["result_sha256"],
            }
            identity.update({
                "assigned_methods": ["sequential", "kmtotalizer"] if identity["id"] in benchmark_ids else [],
                "outcomes": [],
                "final_coverage_status": "open",
            })
            nodes.append(identity)
    nodes.sort(key=lambda row: row["id"])
    if len(nodes) != 47 or len({row["id"] for row in nodes}) != 47:
        raise ValueError("source summary must define exactly 47 uniquely identified frontier nodes")

    frontier_identity = [{key: row[key] for key in (
        "id", "kind", "root_index", "secondary_index", "tertiary_index",
        "source_path", "inherited_result_sha256",
    )} for row in nodes]
    manifest = {
        "schema_version": 1,
        "problem_id": "covering-c1264",
        "policy": {"path": str(POLICY), "sha256": sha256(ROOT / POLICY)},
        "frontier_source": {"path": str(SUMMARY), "sha256": sha256(ROOT / SUMMARY)},
        "first_measurement": {"path": str(BENCHMARK), "sha256": sha256(ROOT / BENCHMARK)},
        "frontier_definition_sha256": canonical_hash(frontier_identity),
        "counts": {"total": 47, "closed": 0, "open": 47},
        "global_uncertainty": "C(12,6,4) is 40 or 41",
        "resolution_status": "open",
        "success_criterion": "an independently validated 40-block cover, or 47/47 valid closures across the portfolio followed by independent global coverage validation",
        "active_resolution_routes": {
            "forced_matching_exact_degree_40_block_witness": {
                "kind": "constructive", "status": "active", "tranches": [],
                "success_certificate": "directly and independently verified 40-block cover"
            },
            "canonical_47_node_certified_exclusion": {
                "kind": "negative", "status": "active", "tranches": [],
                "success_certificate": "47/47 certified closures and independent global coverage validation"
            }
        },
        "method_registry": {
            "sequential": {"status": "active_first_measurement", "semantic_gate": "passed by fixed benchmark preflight"},
            "kmtotalizer": {"status": "active_first_measurement", "semantic_gate": "passed by fixed benchmark preflight"},
            "alternative_cardinality": {"status": "candidate", "semantic_gate": "required"},
            "alternative_cubing": {"status": "candidate", "semantic_gate": "required"},
            "pb_cp_sat": {"status": "candidate", "semantic_gate": "required"},
            "ilp": {"status": "candidate", "semantic_gate": "required"},
            "forced_matching_exact_degree_40_block_witness": {"status": "active", "semantic_gate": "direct witness validation required"}
        },
        "tranches": [],
        "nodes": nodes,
    }
    manifest["manifest_payload_sha256"] = canonical_hash(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n")
    print(output)


if __name__ == "__main__":
    main()
