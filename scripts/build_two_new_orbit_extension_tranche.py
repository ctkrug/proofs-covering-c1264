#!/usr/bin/env python3
"""Freeze the direct residual-extension tests for the eighth and ninth link orbits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("artifacts/experiments/link-orbits-8-9-extension-300s-20260722/manifest.json")
CATALOG = Path("artifacts/discoveries/link-orbit-catalog-9.json")
CATALOG_AUDIT = Path("artifacts/discoveries/link-orbit-catalog-9-audit.json")
BATCH_AUDIT = Path("artifacts/classification/exhaustive-link-v1/three-case-review-new-orbits-independent-audit.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    catalog = json.loads((ROOT / CATALOG).read_text())
    audit = json.loads((ROOT / CATALOG_AUDIT).read_text())
    batch = json.loads((ROOT / BATCH_AUDIT).read_text())
    if catalog["orbit_count"] != 9 or audit.get("status") != "valid":
        raise ValueError("nine-orbit catalog is not independently audited")
    candidates = {row["canonical_sha256"]: row for row in batch["candidates"]}
    selected = [
        ("orbit-8-t-16", "7291235f9679362212e69d3e7eb50dbcfc445bb1da66a14bd0d01135a56a7894"),
        ("orbit-9-t-17", "a2b4fb1c04cc3944b697840bb50d5cd55d89348f539bf48d6c8cb8a1a5e953d1"),
    ]
    units = []
    for unit_id, canonical in selected:
        candidate = candidates[canonical]
        witness = Path(candidate["witness"]["path"])
        if sha(ROOT / witness) != candidate["witness"]["sha256"]:
            raise ValueError("candidate witness hash mismatch")
        units.append({
            "id": unit_id,
            "canonical_sha256": canonical,
            "witness": candidate["witness"],
            "seconds_cap": 300,
            "output": f"artifacts/experiments/link-orbits-8-9-extension-300s-20260722/{unit_id}",
        })
    inputs = [CATALOG, CATALOG_AUDIT, BATCH_AUDIT, Path("scripts/run_link_residual_pilot.py"),
              Path("scripts/run_two_new_orbit_extension_tranche.py"), Path("checkers/audit_link_residual_cnf.py")]
    return {
        "schema_version": 1,
        "run_id": "link-orbits-8-9-extension-300s-20260722",
        "ordered_units": units,
        "method": "fixed-link residual sequential-counter CNF with CaDiCaL proof logging",
        "seconds_per_unit": 300,
        "maximum_units": 2,
        "catalog": {"path": str(CATALOG), "sha256": sha(ROOT / CATALOG)},
        "catalog_audit": {"path": str(CATALOG_AUDIT), "sha256": sha(ROOT / CATALOG_AUDIT)},
        "candidate_audit": {"path": str(BATCH_AUDIT), "sha256": sha(ROOT / BATCH_AUDIT)},
        "input_sha256": {str(path): sha(ROOT / path) for path in inputs},
        "decision_rule": "SAT triggers immediate independent direct 40-cover verification. UNSAT remains provisional until fresh CNF reconstruction and external DRAT replay. UNKNOWN is inconclusive.",
        "claim_limit": "Tests extension of exactly two validated point-link representatives; it does not exhaust all point links.",
    }


def main() -> None:
    value = build()
    output = ROOT / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"built {len(value['ordered_units'])}-orbit extension tranche")


if __name__ == "__main__":
    main()
