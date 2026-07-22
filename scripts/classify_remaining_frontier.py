#!/usr/bin/env python3
"""Classify every open seven-orbit frontier node after a frozen tranche."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/portfolio/frontier-manifest-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    output = args.output if args.output.is_absolute() else ROOT / args.output
    manifest = json.loads(manifest_path.read_text())
    classes = {"never_measured": [], "fixed_cap_timeout": [], "blocked_by_newly_discovered_orbit": []}
    discoveries = {"t-16", "t-17"}
    for node in manifest["nodes"]:
        if node["final_coverage_status"] != "open":
            continue
        statuses = [row.get("status") for row in node["outcomes"]]
        if node["id"] in discoveries and "provisional_sat" in statuses:
            category = "blocked_by_newly_discovered_orbit"
            reason = "the measured SAT witness became a catalogued orbit; this leaf needs remeasurement under the seven-orbit blocker"
        elif "unknown" in statuses:
            category = "fixed_cap_timeout"
            reason = "at least one sound fixed-cap run returned UNKNOWN and no certified closure exists"
        elif not statuses:
            category = "never_measured"
            reason = "no solver outcome is recorded"
        else:
            raise ValueError(f"open node {node['id']} has no allowed classification: {statuses}")
        classes[category].append({"id": node["id"], "kind": node["kind"], "reason": reason,
                                  "recorded_statuses": statuses})
    for rows in classes.values():
        rows.sort(key=lambda row: row["id"])
    if sum(map(len, classes.values())) != manifest["counts"]["open"]:
        raise ValueError("open classification does not partition the ledger")
    payload = {
        "schema_version": 1,
        "status": "valid",
        "claim_limit": "Operational classification of the open audited seven-orbit frontier; not an exhaustive-link theorem.",
        "manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "global_ledger": f"{manifest['counts']['closed']}/47",
        "open_total": manifest["counts"]["open"],
        "counts": {key: len(value) for key, value in classes.items()},
        "classes": classes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
