#!/usr/bin/env python3
"""Independently audit the active link-catalogue binding and 47-node ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checkers"))
from verify_certificate_portfolio import expected_nodes, verify  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clauses(path: Path) -> set[tuple[int, ...]]:
    result = set()
    for line in path.read_text(encoding="ascii").splitlines():
        if not line or line[0] in "cp":
            continue
        row = tuple(map(int, line.split()))
        if not row or row[-1] != 0:
            raise ValueError("malformed blocker clause")
        result.add(row[:-1])
    return result


def audit(manifest_path: Path) -> dict[str, object]:
    verify(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads((ROOT / manifest["frontier_source"]["path"]).read_text(encoding="utf-8"))
    expected = expected_nodes(summary)
    if len(expected) != 47:
        raise ValueError("canonical frontier is not 47 nodes")
    catalog_path = ROOT / manifest["active_link_catalog"]["path"]
    catalog_audit_path = ROOT / manifest["active_link_catalog_audit"]["path"]
    blocker_path = ROOT / manifest["active_link_blocker"]["path"]
    predecessor_path = ROOT / manifest["predecessor_link_blocker"]["path"]
    for key, path in (
        ("active_link_catalog", catalog_path),
        ("active_link_catalog_audit", catalog_audit_path),
        ("active_link_blocker", blocker_path),
        ("predecessor_link_blocker", predecessor_path),
    ):
        if manifest[key]["sha256"] != sha(path):
            raise ValueError(f"{key} hash mismatch")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_audit = json.loads(catalog_audit_path.read_text(encoding="utf-8"))
    if catalog_audit.get("status") != "valid":
        raise ValueError("catalogue audit is not valid")
    if catalog_audit["catalog_sha256"] != sha(catalog_path):
        raise ValueError("catalogue audit hash mismatch")
    if catalog_audit["blocking_cnf_sha256"] != sha(blocker_path):
        raise ValueError("blocker audit hash mismatch")
    if catalog["orbit_count"] != catalog_audit["orbit_count"]:
        raise ValueError("orbit count mismatch")
    if catalog["blocked_link_images"] != catalog_audit["blocked_link_images"]:
        raise ValueError("blocked-image count mismatch")
    old, new = clauses(predecessor_path), clauses(blocker_path)
    if not old < new:
        raise ValueError("active blocker is not a strict superset")
    monotonicity = manifest["blocker_monotonicity"]
    if monotonicity["predecessor_clauses"] != len(old) or monotonicity["active_clauses"] != len(new):
        raise ValueError("monotonicity receipt count mismatch")
    if monotonicity["added_clauses"] != len(new - old):
        raise ValueError("monotonicity receipt delta mismatch")
    if any(row["active_blocker_sha256"] != sha(blocker_path) for row in manifest["nodes"]):
        raise ValueError("node blocker binding mismatch")
    closed = sum(row["final_coverage_status"] != "open" for row in manifest["nodes"])
    return {
        "schema_version": 1,
        "status": "valid",
        "manifest_sha256": sha(manifest_path),
        "frontier_revision": manifest["frontier_revision"],
        "frontier_nodes": 47,
        "secondary_nodes": sum(row["kind"] == "secondary" for row in expected.values()),
        "tertiary_nodes": sum(row["kind"] == "tertiary" for row in expected.values()),
        "closed": closed,
        "open": 47 - closed,
        "catalog_orbits": catalog["orbit_count"],
        "blocked_link_images": len(new),
        "predecessor_blocker_clauses": len(old),
        "active_blocker_clauses": len(new),
        "monotone_preservation": "verified",
        "global_coverage_status": f"open; {closed}/47 certified closures",
        "claim_limit": "Audits canonical frontier identity, active blocker binding, monotone certificate transfer, and ledger accounting; it does not prove 47/47 closure.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", type=Path, default=Path("artifacts/portfolio/frontier-manifest-v1.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    value = audit(manifest_path)
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
