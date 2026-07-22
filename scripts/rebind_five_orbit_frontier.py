#!/usr/bin/env python3
"""Rebind the single 47-node portfolio ledger to the audited five-orbit blocker."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_certificate_portfolio import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("artifacts/portfolio/frontier-manifest-v1.json")
CATALOG = Path("artifacts/discoveries/link-orbit-catalog-5.json")
CATALOG_AUDIT = Path("artifacts/discoveries/link-orbit-catalog-5-audit.json")
OLD_BLOCKER = Path("artifacts/pilot/link-orbit-catalog-4-blocking.cnf")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blocker_clauses(path: Path) -> set[tuple[int, ...]]:
    rows: set[tuple[int, ...]] = set()
    for line in path.read_text(encoding="ascii").splitlines():
        if not line or line[0] in "cp":
            continue
        values = tuple(map(int, line.split()))
        if not values or values[-1] != 0:
            raise ValueError(f"malformed blocker clause in {path}")
        rows.add(values[:-1])
    return rows


def record(path: Path) -> dict[str, object]:
    absolute = ROOT / path
    return {"path": str(path), "sha256": sha(absolute), "bytes": absolute.stat().st_size}


def rebind(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads((ROOT / manifest_path).read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / CATALOG).read_text(encoding="utf-8"))
    audit = json.loads((ROOT / CATALOG_AUDIT).read_text(encoding="utf-8"))
    new_blocker = Path(catalog["blocking_cnf"]["path"])
    old_clauses = blocker_clauses(ROOT / OLD_BLOCKER)
    new_clauses = blocker_clauses(ROOT / new_blocker)
    if len(old_clauses) != 1616 or len(new_clauses) != 1776:
        raise ValueError("unexpected blocker cardinality")
    if not old_clauses < new_clauses:
        raise ValueError("five-orbit blocker is not a strict superset of the four-orbit blocker")
    if audit.get("status") != "valid" or audit.get("blocking_cnf_sha256") != sha(ROOT / new_blocker):
        raise ValueError("five-orbit catalogue audit disagreement")
    if manifest["counts"]["total"] != 47 or (
        manifest["counts"]["closed"] + manifest["counts"]["open"] != 47
    ):
        raise ValueError("invalid canonical frontier counts")

    manifest["frontier_revision"] = 2
    manifest["active_link_catalog"] = record(CATALOG)
    manifest["active_link_catalog_audit"] = record(CATALOG_AUDIT)
    manifest["active_link_blocker"] = record(new_blocker)
    manifest["predecessor_link_blocker"] = record(OLD_BLOCKER)
    manifest["blocker_monotonicity"] = {
        "status": "strict_superset_verified",
        "predecessor_clauses": len(old_clauses),
        "active_clauses": len(new_clauses),
        "added_clauses": len(new_clauses - old_clauses),
        "consequence": "Every certified UNSAT result under the weaker predecessor blocker remains UNSAT under the active stronger blocker; no proof is counted twice.",
    }
    manifest["frontier_rebuild"] = {
        "status": "rebuilt_pending_independent_audit",
        "structural_partition": "unchanged 47-node canonical partition",
        "secondary_nodes": sum(row["kind"] == "secondary" for row in manifest["nodes"]),
        "tertiary_nodes": sum(row["kind"] == "tertiary" for row in manifest["nodes"]),
        "discovery_leaf": "s-r1-3",
        "discovery_leaf_status": "open; resume with active five-orbit blocker",
    }
    # The benchmark checkpoint is intentionally mutable across segments. Replace the
    # tranche's stale pointer with the ten immutable result receipts it actually ingested.
    for tranche in manifest.get("tranches", []):
        if tranche.get("id") == "cardinality-encoding-20-leaf-20260722-segment-01":
            if "source_results" in tranche:
                continue
            historical = tranche.pop("source_checkpoint")
            sources = []
            for node in manifest["nodes"]:
                for outcome in node["outcomes"]:
                    if outcome.get("run_id") == "cardinality-encoding-20-leaf-20260722":
                        sources.append(outcome["result_receipt"])
            if len(sources) != tranche["completed_solver_runs"]:
                raise ValueError("segment-01 immutable result receipt count disagreement")
            tranche["source_results"] = sorted(sources, key=lambda row: row["path"])
            tranche["superseded_mutable_checkpoint"] = {
                "path": historical["path"],
                "historical_sha256": historical["sha256"],
                "reason": "checkpoint advances in place after each frozen benchmark segment",
            }
    for node in manifest["nodes"]:
        node["active_blocker_sha256"] = manifest["active_link_blocker"]["sha256"]
    manifest.pop("manifest_payload_sha256", None)
    manifest["manifest_payload_sha256"] = canonical_hash(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    value = rebind(args.manifest)
    output = ROOT / args.manifest
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(f"rebound {len(value['nodes'])} nodes to {value['active_link_blocker']['sha256']}")


if __name__ == "__main__":
    main()
