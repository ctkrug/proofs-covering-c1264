#!/usr/bin/env python3
"""Freeze the current link-classification and residual campaign state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_validated_unsat(directory: Path) -> dict[str, object]:
    result = load(directory / "result.json")
    audit = load(directory / "cnf-audit.json")
    validation = load(directory / "external-validation.json")
    if result["status"] not in {"UNSAT_PROVISIONAL", "UNSAT_ONE_LINK"}:
        raise ValueError(f"not an UNSAT result: {directory}")
    if audit["status"] != "valid" or validation["status"] != "verified":
        raise ValueError(f"missing validation: {directory}")
    if audit["cnf_sha256"] != result["cnf"]["sha256"] or validation["cnf"]["sha256"] != result["cnf"]["sha256"]:
        raise ValueError(f"CNF binding mismatch: {directory}")
    return {
        "path": str(directory.relative_to(ROOT)),
        "result_sha256": sha(directory / "result.json"),
        "cnf_sha256": result["cnf"]["sha256"],
        "audit_sha256": sha(directory / "cnf-audit.json"),
        "validation_sha256": sha(directory / "external-validation.json"),
        "proof_sha256": validation["proof"]["sha256"],
    }


def chosen_secondary(root_index: int, secondary_index: int) -> Path:
    base = ROOT / "artifacts" / "pilot"
    if root_index == 0:
        suffix = "60s" if secondary_index <= 6 else "10s"
        return base / f"link-orbit-root0-secondary-{secondary_index}-{suffix}"
    if secondary_index in {4, 8}:
        return base / f"link-orbit-root1-secondary-{secondary_index}-catalog4-60s"
    suffix = "60s" if secondary_index in {0, 1, 2, 3, 5, 6, 7, 9, 15} else "10s"
    return base / f"link-orbit-root1-secondary-{secondary_index}-{suffix}"


def build() -> dict[str, object]:
    pilot = ROOT / "artifacts" / "pilot"
    catalog_path = pilot / "link-orbit-catalog-4.json"
    catalog_audit_path = pilot / "link-orbit-catalog-4.audit.json"
    catalog = load(catalog_path)
    catalog_audit = load(catalog_audit_path)
    if catalog_audit["status"] != "valid" or catalog_audit["catalog_sha256"] != sha(catalog_path):
        raise ValueError("catalog audit mismatch")

    secondary: dict[str, object] = {}
    validated_secondary = []
    open_secondary = []
    for root_index, total in ((0, 39), (1, 68)):
        statuses = {"validated_unsat": 0, "open_unknown": 0}
        for secondary_index in range(total):
            directory = chosen_secondary(root_index, secondary_index)
            result = load(directory / "result.json")
            if result["status"] == "UNSAT_PROVISIONAL":
                validated_secondary.append(require_validated_unsat(directory))
                statuses["validated_unsat"] += 1
            elif result["status"] == "UNKNOWN":
                if not (root_index == 0 and secondary_index == 0):
                    open_secondary.append({
                        "root_index": root_index,
                        "secondary_index": secondary_index,
                        "path": str(directory.relative_to(ROOT)),
                        "result_sha256": sha(directory / "result.json"),
                    })
                statuses["open_unknown"] += 1
            else:
                raise ValueError(f"unexpected selected secondary status: {directory}")
        secondary[str(root_index)] = {"total": total, **statuses}

    primary_directories = [
        pilot / "link-orbit-third-root-2-60s",
        *(pilot / f"link-orbit-second-root-{index}-60s" for index in (3, 4, 5)),
    ]
    validated_primary = [require_validated_unsat(path) for path in primary_directories]
    residual_directories = [
        pilot / "link-residual-first-300s",
        pilot / "link-residual-second-orbit-300s",
        pilot / "link-residual-third-orbit-300s",
        pilot / "link-residual-fourth-orbit-300s",
    ]
    validated_residuals = [require_validated_unsat(path) for path in residual_directories]
    validated_tertiary = []
    open_tertiary = []
    for tertiary_index in range(122):
        path10 = pilot / f"link-orbit-root0-secondary-0-tertiary-{tertiary_index}-10s"
        path2 = pilot / f"link-orbit-root0-secondary-0-tertiary-{tertiary_index}-2s"
        directory = path10 if (path10 / "result.json").exists() else path2
        result = load(directory / "result.json")
        if result["status"] == "UNSAT_PROVISIONAL":
            validated_tertiary.append(require_validated_unsat(directory))
        elif result["status"] == "UNKNOWN":
            open_tertiary.append({
                "root_index": 0,
                "secondary_index": 0,
                "tertiary_index": tertiary_index,
                "path": str(directory.relative_to(ROOT)),
                "result_sha256": sha(directory / "result.json"),
            })
        else:
            raise ValueError(f"unexpected tertiary status: {directory}")
    proof_receipts = (
        len(validated_secondary) + len(validated_primary) + len(validated_residuals)
        + len(validated_tertiary)
    )
    return {
        "schema_version": 1,
        "status": "checkpointed-open-tail",
        "catalog": {
            "path": str(catalog_path.relative_to(ROOT)),
            "sha256": sha(catalog_path),
            "audit_sha256": sha(catalog_audit_path),
            "distinct_link_orbits": catalog["orbit_count"],
            "blocked_link_images": catalog["blocked_link_images"],
            "orbit_sizes": [row["orbit_size"] for row in catalog["orbits"]],
        },
        "secondary_roots": secondary,
        "validated_secondary_exclusions": validated_secondary,
        "validated_primary_exclusions": validated_primary,
        "validated_link_residual_exclusions": validated_residuals,
        "tertiary_root_0_secondary_0": {
            "partition_manifest": "artifacts/pilot/link-root0-secondary0-tertiary-partition.json",
            "partition_manifest_sha256": sha(pilot / "link-root0-secondary0-tertiary-partition.json"),
            "partition_audit_sha256": sha(pilot / "link-root0-secondary0-tertiary-partition.audit.json"),
            "total": 122,
            "validated_unsat": len(validated_tertiary),
            "open_unknown": len(open_tertiary),
        },
        "validated_tertiary_exclusions": validated_tertiary,
        "validated_external_proof_receipts": proof_receipts,
        "open_secondary_cases": open_secondary,
        "open_secondary_count": len(open_secondary),
        "open_tertiary_cases": open_tertiary,
        "open_tertiary_count": len(open_tertiary),
        "open_frontier_count": len(open_secondary) + len(open_tertiary),
        "direct_cube_sample": {"sampled": 128, "closed_provisional": 10, "closure_fraction": 0.078125},
        "claim_limit": (
            "Four exact-degree link orbits are cataloged and all four fail replay-validated residual "
            "extension checks. Fourteen secondary cases and 33 tertiary leaves remain open, so link enumeration is "
            "not complete and no value of C(12,6,4) is claimed."
        ),
        "next_gate": (
            "Continue canonical augmentation only on the 47 open frontier nodes. Every SAT result must "
            "be canonicalized against the full catalog; every UNSAT leaf needs reconstruction plus "
            "external proof replay."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = build()
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "status": value["status"],
        "distinct_link_orbits": value["catalog"]["distinct_link_orbits"],
        "validated_external_proof_receipts": value["validated_external_proof_receipts"],
        "open_secondary_count": value["open_secondary_count"],
        "sha256": sha(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
