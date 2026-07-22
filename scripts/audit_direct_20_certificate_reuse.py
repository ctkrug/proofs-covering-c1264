#!/usr/bin/env python3
"""Inventory which replayed nine-orbit nonextensions transfer to direct-20 cases."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "artifacts/prior-art/c1153-direct-20/manifest.json"
OUTPUT = ROOT / "artifacts/prior-art/c1153-direct-20/certificate-reuse-audit.json"

EVIDENCE = {
    "8588c1d6bef8da17488984c28e222594e088ef1435d8737fafc28d01cd8f5148": "artifacts/pilot/link-residual-first-300s/external-validation.json",
    "681764d1b0bf68ceff7809a7146d91a21a7504528ba71bbf73940daefa1c54a1": "artifacts/pilot/link-residual-second-orbit-300s/external-validation.json",
    "c31bde7d138db2072f1309f834814aa2e27722a9b1bf21e08e758b1acca93349": "artifacts/pilot/link-residual-third-orbit-300s/external-validation.json",
    "67d803aa141d828b4f2911c4a9f8199b1f26f4141a96a0e3a31b78b773de3468": "artifacts/pilot/link-residual-fourth-orbit-300s/external-validation.json",
    "b470049c5444b5f9bdd253d6e096e42e52e42c3512e545b43a4ad8f9346bb49c": "artifacts/discoveries/link-orbit-s-r1-3/residual-extension/external-validation.json",
    "31fb7b6b50ebbab8a549bad171c3e42c20448c88a1ec1c0f95a167188f974374": "artifacts/experiments/link-orbit-t-16-extension-300s-20260722/independent-validation.json",
    "c01d7d4a45ca96b3a442a87d5df422c45f6d3ce5a83ca450c3ee7c4e647837ca": "artifacts/experiments/link-orbit-t-17-extension-300s-20260722/independent-validation.json",
    "7291235f9679362212e69d3e7eb50dbcfc445bb1da66a14bd0d01135a56a7894": "artifacts/experiments/link-orbits-8-9-extension-300s-20260722/orbit-8-t-16/independent-validation.json",
    "a2b4fb1c04cc3944b697840bb50d5cd55d89348f539bf48d6c8cb8a1a5e953d1": "artifacts/experiments/link-orbits-8-9-extension-300s-20260722/orbit-9-t-17/independent-validation.json",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for case in manifest["cases"]:
        canonical = case["canonical_sha256"]
        if canonical not in EVIDENCE:
            continue
        validation_path = ROOT / EVIDENCE[canonical]
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        if validation.get("verdict") != "s VERIFIED" or validation.get("status") not in {
            "verified", "verified_unsat_fixed_link_extension"
        }:
            raise ValueError(f"unverified evidence for {canonical}")
        cnf = validation["cnf"]
        proof = validation["proof"]
        if sha(ROOT / cnf["path"]) != cnf["sha256"] or sha(ROOT / proof["path"]) != proof["sha256"]:
            raise ValueError(f"evidence hash mismatch for {canonical}")
        exact = cnf["sha256"] == case["cnf"]["sha256"]
        rows.append({
            "class_index": case["class_index"],
            "canonical_sha256": canonical,
            "validation": {"path": EVIDENCE[canonical], "sha256": sha(validation_path)},
            "replayed_cnf": cnf,
            "replayed_proof": proof,
            "direct_20_cnf": case["cnf"],
            "transfer_status": (
                "exact_cnf_hash_reuse_ready" if exact else
                "class_mapped_but_requires_cnf_relabel_equivalence_or_regeneration"
            ),
        })
    if len(rows) != 9:
        raise ValueError("expected exactly nine replayed campaign classes")
    payload = {
        "schema_version": 1,
        "status": "valid_reuse_inventory",
        "direct_20_manifest_sha256": sha(MANIFEST),
        "mapped_replayed_classes": len(rows),
        "exact_cnf_hash_reuse_ready": sum(row["transfer_status"] == "exact_cnf_hash_reuse_ready" for row in rows),
        "isomorphic_reuse_pending": sum(row["transfer_status"].startswith("class_mapped") for row in rows),
        "rows": rows,
        "claim_limit": (
            "Class membership does not make a DRAT proof replay on a differently numbered CNF. Exact-hash "
            "reuse is ready for one class; the other eight require a checked CNF/proof relabeling or regeneration."
        ),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"mapped": len(rows), "exact": payload["exact_cnf_hash_reuse_ready"], "pending": payload["isomorphic_reuse_pending"], "sha256": sha(OUTPUT)}))


if __name__ == "__main__":
    main()
