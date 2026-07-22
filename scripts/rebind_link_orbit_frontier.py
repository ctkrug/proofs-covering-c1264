#!/usr/bin/env python3
"""Rebind the durable 47-node ledger to a stronger audited link blocker."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_certificate_portfolio import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("artifacts/portfolio/frontier-manifest-v1.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clauses(path: Path) -> set[tuple[int, ...]]:
    result: set[tuple[int, ...]] = set()
    for line in path.read_text(encoding="ascii").splitlines():
        if not line or line[0] in "cp":
            continue
        row = tuple(map(int, line.split()))
        if not row or row[-1] != 0:
            raise ValueError(f"malformed blocker clause in {path}")
        result.add(row[:-1])
    return result


def record(path: Path) -> dict[str, object]:
    absolute = ROOT / path
    return {"path": str(path), "sha256": sha(absolute), "bytes": absolute.stat().st_size}


def rebind(manifest_path: Path, catalog_path: Path, audit_path: Path) -> dict[str, object]:
    manifest = json.loads((ROOT / manifest_path).read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / catalog_path).read_text(encoding="utf-8"))
    audit = json.loads((ROOT / audit_path).read_text(encoding="utf-8"))
    blocker_path = Path(catalog["blocking_cnf"]["path"])
    predecessor_path = Path(manifest["active_link_blocker"]["path"])
    old, new = clauses(ROOT / predecessor_path), clauses(ROOT / blocker_path)
    if not old < new:
        raise ValueError("replacement blocker is not a strict clause superset")
    if audit.get("status") != "valid":
        raise ValueError("catalogue audit is not valid")
    if audit.get("catalog_sha256") != sha(ROOT / catalog_path):
        raise ValueError("catalogue hash disagrees with independent audit")
    if audit.get("blocking_cnf_sha256") != sha(ROOT / blocker_path):
        raise ValueError("blocker hash disagrees with independent audit")
    if manifest["counts"]["total"] != 47 or manifest["counts"]["closed"] + manifest["counts"]["open"] != 47:
        raise ValueError("invalid canonical frontier counts")

    history = manifest.setdefault("blocker_history", [])
    previous = {
        "frontier_revision": manifest.get("frontier_revision", 1),
        "active_link_catalog": manifest.get("active_link_catalog"),
        "active_link_catalog_audit": manifest.get("active_link_catalog_audit"),
        "active_link_blocker": manifest.get("active_link_blocker"),
        "predecessor_link_blocker": manifest.get("predecessor_link_blocker"),
        "blocker_monotonicity": manifest.get("blocker_monotonicity"),
        "frontier_rebuild": manifest.get("frontier_rebuild"),
    }
    if not history or history[-1].get("active_link_blocker") != previous["active_link_blocker"]:
        history.append(previous)

    manifest["frontier_revision"] = int(manifest.get("frontier_revision", 1)) + 1
    manifest["active_link_catalog"] = record(catalog_path)
    manifest["active_link_catalog_audit"] = record(audit_path)
    manifest["active_link_blocker"] = record(blocker_path)
    manifest["predecessor_link_blocker"] = record(predecessor_path)
    manifest["blocker_monotonicity"] = {
        "status": "strict_superset_verified",
        "predecessor_clauses": len(old),
        "active_clauses": len(new),
        "added_clauses": len(new - old),
        "consequence": "Every certified UNSAT result under the predecessor blocker remains UNSAT under this stronger blocker; result and replay receipts are immutable.",
    }
    manifest["frontier_rebuild"] = {
        "status": "rebuilt_pending_independent_audit",
        "structural_partition": "unchanged 47-node canonical partition",
        "secondary_nodes": sum(row["kind"] == "secondary" for row in manifest["nodes"]),
        "tertiary_nodes": sum(row["kind"] == "tertiary" for row in manifest["nodes"]),
        "discovery_leaves": ["t-16", "t-17"],
        "discovery_leaf_status": "open; new link orbits validated locally and added to the active blocker",
    }
    for node in manifest["nodes"]:
        node["active_blocker_sha256"] = manifest["active_link_blocker"]["sha256"]
    manifest.pop("dynamic_assignment", None)
    manifest.pop("manifest_payload_sha256", None)
    manifest["manifest_payload_sha256"] = canonical_hash(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--catalog-audit", type=Path, required=True)
    args = parser.parse_args()
    value = rebind(args.manifest, args.catalog, args.catalog_audit)
    output = ROOT / args.manifest
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(f"rebound {len(value['nodes'])} nodes to revision {value['frontier_revision']}")


if __name__ == "__main__":
    main()
