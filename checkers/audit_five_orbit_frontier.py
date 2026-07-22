#!/usr/bin/env python3
"""Independently audit the five-orbit binding of the canonical 47-node frontier."""

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
        assert row[-1] == 0
        result.add(row[:-1])
    return result


def audit(manifest_path: Path) -> dict[str, object]:
    verify(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["frontier_revision"] == 2
    summary_path = ROOT / manifest["frontier_source"]["path"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected = expected_nodes(summary)
    assert len(expected) == 47
    assert sum(row["kind"] == "secondary" for row in expected.values()) == 14
    assert sum(row["kind"] == "tertiary" for row in expected.values()) == 33

    catalog_path = ROOT / manifest["active_link_catalog"]["path"]
    audit_path = ROOT / manifest["active_link_catalog_audit"]["path"]
    blocker_path = ROOT / manifest["active_link_blocker"]["path"]
    old_path = ROOT / manifest["predecessor_link_blocker"]["path"]
    for binding, path in (("active_link_catalog", catalog_path),
                          ("active_link_catalog_audit", audit_path),
                          ("active_link_blocker", blocker_path),
                          ("predecessor_link_blocker", old_path)):
        assert manifest[binding]["sha256"] == sha(path)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert catalog["orbit_count"] == catalog_audit["orbit_count"] == 5
    assert catalog["blocked_link_images"] == catalog_audit["blocked_link_images"] == 1776
    assert catalog_audit["status"] == "valid"
    old, new = clauses(old_path), clauses(blocker_path)
    assert len(old) == 1616 and len(new) == 1776 and old < new
    assert manifest["blocker_monotonicity"]["added_clauses"] == 160
    assert all(row["active_blocker_sha256"] == sha(blocker_path) for row in manifest["nodes"])
    closed = sum(row["final_coverage_status"] != "open" for row in manifest["nodes"])
    assert manifest["counts"] == {"total": 47, "closed": closed, "open": 47 - closed}
    return {
        "schema_version": 1,
        "status": "valid",
        "manifest_sha256": sha(manifest_path),
        "frontier_nodes": 47,
        "secondary_nodes": 14,
        "tertiary_nodes": 33,
        "closed": closed,
        "open": 47 - closed,
        "catalog_orbits": 5,
        "blocked_link_images": 1776,
        "predecessor_blocker_clauses": 1616,
        "active_blocker_clauses": 1776,
        "monotone_preservation": "verified",
        "global_coverage_status": f"open; {closed}/47 certified closures",
        "claim_limit": "This audits the canonical frontier identity, five-orbit binding, and manifest accounting. It does not prove 47/47 global closure.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", type=Path,
                        default=Path("artifacts/portfolio/frontier-manifest-v1.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    result = audit(path)
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
