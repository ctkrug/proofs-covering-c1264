#!/usr/bin/env python3
"""Proof-produce the empirically easy suffix of every fourth-block partition."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from run_ordinary_c1153_fourth_discriminator import PARALLELISM, ROOT, run_one


BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fourth-split"
SECONDS = 3
CAMPAIGN = "suffix-proof-scale-3s"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path = BASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    measured = {path.parent.name for path in (BASE / "discriminator-10s").glob("*/result.json")}
    jobs = []
    for parent in manifest["parents"]:
        start = len(parent["branches"]) // 2
        jobs.extend((parent, branch) for branch in parent["branches"][start:] if branch["id"] not in measured)
    protocol = {
        "schema_version": 1,
        "status": "FROZEN",
        "manifest_sha256": sha(manifest_path),
        "selection": "Every previously unmeasured branch at or after its parent's midpoint orbit; no early-prefix case and no measured case is included.",
        "leaf_ids": [branch["id"] for _, branch in jobs],
        "seconds_cap": SECONDS,
        "parallelism": PARALLELISM,
        "evidence": "All 13 midpoint branches closed in at most 1.25 seconds with independently replayed proofs; second-orbit branches all timed out at 10 seconds.",
        "stop_rule": "Timeouts remain open and are not automatically rerun. Any SAT cover requires independent isomorphism audit before further classification claims.",
    }
    protocol_path = BASE / "suffix-proof-scale-3s-protocol.json"
    protocol_path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    outcomes = []
    with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
        futures = [pool.submit(run_one, parent, branch, SECONDS, CAMPAIGN) for parent, branch in jobs]
        for future in as_completed(futures):
            outcomes.append(future.result())
    outcomes.sort(key=lambda row: row["leaf_id"])
    summary = {
        "schema_version": 1,
        "status": "COMPLETE",
        "protocol": {"path": str(protocol_path.relative_to(ROOT)), "sha256": sha(protocol_path)},
        "counts": {status: sum(row["status"] == status for row in outcomes) for status in sorted({row["status"] for row in outcomes})},
        "outcomes": outcomes,
        "claim_limit": "Verified results close exact suffix branches only; each parent still requires every prefix branch.",
    }
    target = BASE / "suffix-proof-scale-3s-summary.json"
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
