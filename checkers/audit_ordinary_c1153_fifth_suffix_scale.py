#!/usr/bin/env python3
"""Independent membership, exclusion, and segment audit for fifth suffix scale."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
FIFTH_PATH = BASE / "manifest.json"
ROUTE_PATH = BASE / "suffix-scale-manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    fifth = json.loads(FIFTH_PATH.read_text())
    route = json.loads(ROUTE_PATH.read_text())
    if route["fifth_manifest"]["sha256"] != sha(FIFTH_PATH):
        raise ValueError("fifth manifest binding mismatch")
    discriminator_path = ROOT / route["discriminator_summary"]["path"]
    if route["discriminator_summary"]["sha256"] != sha(discriminator_path):
        raise ValueError("discriminator binding mismatch")
    discriminator = json.loads(discriminator_path.read_text())
    measured = {row["leaf_id"] for row in discriminator["outcomes"]}
    universe = []
    parent_counts = {}
    leaf_to_parent = {}
    for parent in fifth["parents"]:
        ids = []
        for index in range(parent["branch_count"] // 4, parent["branch_count"]):
            leaf_id = f"{parent['id']}-fifth-{index:03d}"
            ids.append(leaf_id)
            leaf_to_parent[leaf_id] = parent["id"]
        universe.extend(ids)
        parent_counts[parent["id"]] = len(ids)
    universe_set = set(universe)
    if len(universe) != len(universe_set) or len(universe_set) != 32645:
        raise ValueError("suffix universe membership/uniqueness mismatch")
    excluded = universe_set & measured
    if len(excluded) != 48 or excluded != set(route["excluded_measured_leaf_ids"]):
        raise ValueError("measured suffix exclusion mismatch")
    pending = universe_set - excluded
    if len(pending) != 32597 or route["parent_suffix_counts"] != parent_counts or len(parent_counts) != 384:
        raise ValueError("pending or parent coverage mismatch")
    segment_ids = []
    seen = set()
    for expected_number, segment in enumerate(route["segments"]):
        if segment["segment"] != expected_number or segment["count"] != len(segment["leaf_ids"]):
            raise ValueError("segment numbering/count mismatch")
        if len(segment["leaf_ids"]) != len(set(segment["leaf_ids"])):
            raise ValueError(f"segment {expected_number}: duplicate leaf")
        if seen & set(segment["leaf_ids"]):
            raise ValueError(f"segment {expected_number}: cross-segment duplicate")
        digest = hashlib.sha256(("\n".join(segment["leaf_ids"]) + "\n").encode()).hexdigest()
        if digest != segment["selection_sha256"]:
            raise ValueError(f"segment {expected_number}: selection digest mismatch")
        seen.update(segment["leaf_ids"])
        segment_ids.extend(segment["leaf_ids"])
    if seen != pending or len(segment_ids) != 32597 or len(route["segments"]) != 128:
        raise ValueError("segment union does not equal pending suffix")
    first_path = BASE / "segments/segment-0000/manifest.json"
    first = json.loads(first_path.read_text())
    if first["route_manifest"]["sha256"] != sha(ROUTE_PATH) or first["leaf_ids"] != route["segments"][0]["leaf_ids"] or first["selected"] != 256:
        raise ValueError("segment-0 binding mismatch")
    storage = route["storage_plan"]
    if storage["projected_pending_proof_bytes"] > storage["storage_limit_bytes"] or storage["free_bytes_at_freeze"] - storage["projected_pending_proof_bytes"] < storage["minimum_free_reserve_bytes"]:
        raise ValueError("storage policy fails")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "fifth_manifest_sha256": sha(FIFTH_PATH),
        "route_manifest_sha256": sha(ROUTE_PATH),
        "suffix_universe": len(universe_set),
        "parents_covered": len(parent_counts),
        "excluded_measured": len(excluded),
        "pending_unique": len(pending),
        "segments": len(route["segments"]),
        "segment_0_selected": first["selected"],
        "duplicate_cases": 0,
        "omitted_pending_cases": 0,
        "storage_plan_status": "WITHIN_POLICY",
        "projected_pending_proof_bytes": storage["projected_pending_proof_bytes"],
        "free_bytes_at_freeze": storage["free_bytes_at_freeze"],
        "claim_limit": "Selection/storage audit only; no solver result or parent closure is implied.",
    }
    target = BASE / "suffix-scale-independent-audit.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
