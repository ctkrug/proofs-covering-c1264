#!/usr/bin/env python3
"""Record the measured nine-orbit hard-tail discriminator without extrapolation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = Path("artifacts/sequential-frontier-sweep/sequential-hard-tail-discriminator-v9-20260722")
MANIFEST = Path("artifacts/portfolio/frontier-manifest-v1.json")
OUTPUT = Path("artifacts/classification/exhaustive-link-v1/post-hard-tail-discriminator-analysis.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    checkpoint = json.loads((ROOT / BASE / "checkpoint.json").read_text())
    audit = json.loads((ROOT / BASE / "independent-tranche-audit.json").read_text())
    manifest = json.loads((ROOT / MANIFEST).read_text())
    expected = ["s-r0-1", "s-r1-15", "t-10"]
    if [row["leaf_id"] for row in checkpoint["results"]] != expected:
        raise ValueError("frozen discriminator order changed")
    if audit["counts"] != {"total": 3, "unsat_independently_replayed": 1, "fixed_cap_timeouts": 2}:
        raise ValueError("independent audit count disagreement")
    if manifest["counts"] != {"total": 47, "closed": 33, "open": 14}:
        raise ValueError("ledger was not audited at 33/47")
    nodes = {row["id"]: row for row in manifest["nodes"]}
    timeout_nodes = []
    blocked_orbit_nodes = []
    for node in manifest["nodes"]:
        if node["final_coverage_status"] != "open":
            continue
        statuses = {row.get("status") for row in node["outcomes"]}
        if "provisional_sat" in statuses:
            blocked_orbit_nodes.append(node["id"])
        elif "unknown" in statuses:
            timeout_nodes.append(node["id"])
        else:
            raise ValueError(f"unclassified open node: {node['id']}")
    if len(timeout_nodes) != 11 or sorted(blocked_orbit_nodes) != ["s-r1-3", "t-16", "t-17"]:
        raise ValueError("remaining-node classification disagreement")
    value = {
        "schema_version": 1,
        "status": "valid-measured-discriminator",
        "checkpoint": {"path": str(BASE / "checkpoint.json"), "sha256": sha(ROOT / BASE / "checkpoint.json")},
        "independent_audit": {"path": str(BASE / "independent-tranche-audit.json"), "sha256": sha(ROOT / BASE / "independent-tranche-audit.json")},
        "portfolio": {"path": str(MANIFEST), "sha256": sha(ROOT / MANIFEST)},
        "outcomes": {"s-r0-1": "fixed-cap-timeout", "s-r1-15": "fixed-cap-timeout", "t-10": "replay-verified-unsat"},
        "global_ledger": "33/47",
        "remaining": {
            "fixed_cap_timeouts": sorted(timeout_nodes),
            "fixed_cap_timeout_count": len(timeout_nodes),
            "timeout_by_kind": dict(sorted(Counter(nodes[node]["kind"] for node in timeout_nodes).items())),
            "catalogued_orbit_discovery_leaves": sorted(blocked_orbit_nodes),
        },
        "inference": "The nine-orbit blocker resolved the sampled tertiary case but not either sampled secondary case at 60 seconds.",
        "next_discriminator": "Compare t-10 against the remaining tertiary timeout at the non-cardinality-core and blocker-clause level before assigning more compute; do not infer that all tertiary cases are easy from one closure.",
        "route_switch": "Any SAT link triggers catalogue validation/rebuild; a compact tertiary-specific invariant outranks more solver runs; otherwise test one matched tertiary/secondary pair with a specifically justified cube or branching change.",
        "claim_limit": "One of three sampled hard-tail nodes closed. This does not classify all timeout nodes or exhaust point-link orbits.",
    }
    (ROOT / OUTPUT).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ledger": value["global_ledger"], "timeouts": len(timeout_nodes)}))


if __name__ == "__main__":
    main()
