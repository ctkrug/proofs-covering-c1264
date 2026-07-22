#!/usr/bin/env python3
"""Test whether fourth-split hardness is confined to the earliest orbit prefix."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from run_ordinary_c1153_fourth_discriminator import PARALLELISM, ROOT, SECONDS, run_one


BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fourth-split"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path = BASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    jobs = []
    selections = []
    for parent in manifest["parents"]:
        indices = (1, len(parent["branches"]) // 4)
        for label, index in zip(("second_orbit", "first_quartile"), indices):
            branch = parent["branches"][index]
            jobs.append((parent, branch))
            selections.append({"parent": parent["id"], "label": label, "index": index, "leaf_id": branch["id"]})
    protocol = {
        "schema_version": 1,
        "status": "FROZEN",
        "manifest_sha256": sha(manifest_path),
        "selection": selections,
        "seconds_cap": SECONDS,
        "parallelism": PARALLELISM,
        "hypothesis": "The 60-second parent hardness is concentrated in a short prefix of the ordered fourth-block orbits; midpoint branches are easy because accumulated canonical negatives prune the residual space.",
        "decision_rule": "If at least 11/13 first-quartile cases replay UNSAT, treat the suffix as cheap proof work; if at least 9/13 second-orbit cases time out, split the early prefix one level deeper instead of raising caps.",
    }
    protocol_path = BASE / "boundary-10s-protocol.json"
    protocol_path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    outcomes = []
    with ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
        futures = [pool.submit(run_one, parent, branch) for parent, branch in jobs]
        for future in as_completed(futures):
            outcomes.append(future.result())
    outcomes.sort(key=lambda row: row["leaf_id"])
    label_by_id = {row["leaf_id"]: row["label"] for row in selections}
    counts_by_label = {}
    for label in ("second_orbit", "first_quartile"):
        rows = [row for row in outcomes if label_by_id[row["leaf_id"]] == label]
        counts_by_label[label] = {status: sum(row["status"] == status for row in rows) for status in sorted({row["status"] for row in rows})}
    summary = {
        "schema_version": 1,
        "status": "COMPLETE",
        "protocol": {"path": str(protocol_path.relative_to(ROOT)), "sha256": sha(protocol_path)},
        "counts_by_label": counts_by_label,
        "outcomes": outcomes,
        "claim_limit": "Each verified result closes only its exact branch; this discriminator does not close a timeout parent.",
    }
    target = BASE / "boundary-10s-summary.json"
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
