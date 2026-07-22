#!/usr/bin/env python3
"""Profile only the nodes still open after the sequential frontier sweep."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile(manifest_path: Path, checkpoint_path: Path, portfolio_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    if checkpoint.get("manifest_sha256") != sha(manifest_path):
        raise ValueError("checkpoint is not bound to this sweep manifest")
    if manifest.get("portfolio_manifest_sha256") != sha(portfolio_path):
        raise ValueError("sweep manifest is not bound to this portfolio manifest")
    results = {row["leaf_id"]: row for row in checkpoint["results"]}
    nodes = {row["id"]: row for row in portfolio["nodes"]}
    survivors = []
    for leaf in manifest["leaves"]:
        result = results.get(leaf["id"])
        if result and result["status"] == "UNSAT_VERIFIED":
            continue
        source = ROOT / nodes[leaf["id"]]["source_path"] / "result.json"
        inherited = json.loads(source.read_text(encoding="utf-8"))
        partition = inherited.get("root_partition", {})
        secondary = partition.get("secondary", {})
        tertiary = partition.get("tertiary", {})
        survivors.append({
            "id": leaf["id"],
            "kind": leaf["kind"],
            "root_index": leaf["root_index"],
            "secondary_index": leaf["secondary_index"],
            "tertiary_index": leaf["tertiary_index"],
            "sequential_status": "NOT_RUN" if result is None else result["status"],
            "sequential_elapsed_seconds": None if result is None else result.get("solver_elapsed_seconds"),
            "variables": inherited.get("variables"),
            "clauses": inherited.get("clauses"),
            "root_orbit_size": partition.get("orbit_size"),
            "secondary_orbit_size": secondary.get("orbit_size"),
            "secondary_stabilizer_order": secondary.get("stabilizer_order"),
            "tertiary_orbit_size": tertiary.get("orbit_size"),
            "tertiary_stabilizer_order": tertiary.get("stabilizer_order"),
            "structural_class": f"{leaf['kind']}:r{leaf['root_index']}:s{secondary.get('orbit_size', 'na')}:t{tertiary.get('orbit_size', 'na')}",
        })
    classes: dict[str, list[str]] = {}
    for row in survivors:
        classes.setdefault(row["structural_class"], []).append(row["id"])
    return {
        "schema_version": 1,
        "manifest_sha256": sha(manifest_path),
        "checkpoint_sha256": sha(checkpoint_path),
        "portfolio_sha256": sha(portfolio_path),
        "survivor_count": len(survivors),
        "survivors": survivors,
        "classes": [{"class": key, "node_ids": value, "count": len(value)} for key, value in sorted(classes.items())],
        "allocation_rule": "Assign alternative encodings, cubing, PB/CP-SAT, or longer budgets by measured survivor class; do not uniformly raise the sequential timeout.",
        "claim_limit": "This is an allocation profile, not a mathematical certificate.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--portfolio", type=Path, default=Path("artifacts/portfolio/frontier-manifest-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = profile(args.manifest.resolve(), args.checkpoint.resolve(), args.portfolio.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"survivors": value["survivor_count"], "classes": len(value["classes"])}, sort_keys=True))


if __name__ == "__main__":
    main()
