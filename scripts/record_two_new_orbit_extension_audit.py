#!/usr/bin/env python3
"""Bind the two fixed-link extension replays into one claim-limited receipt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/experiments/link-orbits-8-9-extension-300s-20260722"
UNITS = ("orbit-8-t-16", "orbit-9-t-17")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path: Path) -> dict[str, object]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size}


def main() -> None:
    manifest = json.loads((BASE / "manifest.json").read_text())
    checkpoint = json.loads((BASE / "checkpoint.json").read_text())
    expected = list(UNITS)
    if [unit["id"] for unit in manifest["ordered_units"]] != expected:
        raise ValueError("extension manifest is not the frozen two-unit tranche")
    if checkpoint["manifest_sha256"] != sha(BASE / "manifest.json") or checkpoint["completed"] != expected:
        raise ValueError("checkpoint/manifest disagreement")

    receipts = []
    for unit in UNITS:
        directory = BASE / unit
        result_path = directory / "result.json"
        validation_path = directory / "independent-validation.json"
        result = json.loads(result_path.read_text())
        validation = json.loads(validation_path.read_text())
        if result["status"] != "UNSAT_ONE_LINK":
            raise ValueError(f"{unit}: solver result is not UNSAT_ONE_LINK")
        if validation["status"] != "verified_unsat_fixed_link_extension" or validation["verdict"] != "s VERIFIED":
            raise ValueError(f"{unit}: external replay is not verified")
        for key in ("cnf", "link", "result", "proof", "orbit", "checker"):
            path = ROOT / validation[key]["path"]
            if sha(path) != validation[key]["sha256"]:
                raise ValueError(f"{unit}: {key} hash disagreement")
        receipts.append({
            "id": unit,
            "canonical_sha256": validation["orbit"]["canonical_sha256"],
            "result": record(result_path),
            "independent_validation": record(validation_path),
            "cnf": validation["cnf"],
            "external_replacement_proof": validation["proof"],
            "verdict": validation["verdict"],
        })

    output = {
        "schema_version": 1,
        "status": "verified_two_fixed_link_nonextensions",
        "manifest": record(BASE / "manifest.json"),
        "checkpoint": record(BASE / "checkpoint.json"),
        "receipts": receipts,
        "global_ledger": {"closed": 32, "total": 47, "changed_by_this_result": False},
        "claim_limit": (
            "Each certificate excludes extension of one independently validated link orbit to a 40-block cover. "
            "Neither certificate closes the stale t-16/t-17 frontier leaf, exhausts point-link orbits, or changes the 32/47 global ledger."
        ),
    }
    path = BASE / "extension-audit.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"], "receipts": len(receipts)}))


if __name__ == "__main__":
    main()
