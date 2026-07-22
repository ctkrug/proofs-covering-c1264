#!/usr/bin/env python3
"""Independently validate a batch of SAT link witnesses against a prior catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_link_orbit import acted, all_actions, read_blocks, validate_link


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_receipt(path: Path) -> tuple[set[tuple[tuple[int, ...], ...]], dict[str, object]]:
    blocks = read_blocks(path)
    validate_link(blocks)
    images = {acted(blocks, action) for action in all_actions()}
    stabilizer = sum(acted(blocks, action) == blocks for action in all_actions())
    if len(images) * stabilizer != 3840:
        raise ValueError("orbit-stabilizer disagreement")
    canonical = min(images)
    canonical_text = "".join(" ".join(map(str, block)) + "\n" for block in canonical)
    return images, {
        "witness": {"path": str(path.relative_to(ROOT)), "sha256": sha(path)},
        "canonical_sha256": hashlib.sha256(canonical_text.encode()).hexdigest(),
        "orbit_size": len(images),
        "stabilizer_order": stabilizer,
    }


def audit(prior_catalog_path: Path, result_paths: list[Path]) -> dict[str, object]:
    prior = json.loads(prior_catalog_path.read_text(encoding="utf-8"))
    prior_images: set[tuple[tuple[int, ...], ...]] = set()
    for row in prior["orbits"]:
        source = ROOT / row["source"]["path"]
        if sha(source) != row["source"]["sha256"]:
            raise ValueError("prior catalog source hash mismatch")
        images, receipt = canonical_receipt(source)
        if receipt["canonical_sha256"] != row["canonical_sha256"]:
            raise ValueError("prior catalog canonical hash mismatch")
        prior_images.update(images)

    batch_images: set[tuple[tuple[int, ...], ...]] = set()
    receipts = []
    for result_path in result_paths:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "SAT_NEW_ORBIT":
            raise ValueError("candidate result is not SAT_NEW_ORBIT")
        witness = result_path.with_name("witness.txt")
        images, receipt = canonical_receipt(witness)
        recorded = result.get("validation", {})
        if receipt["witness"]["sha256"] != recorded.get("witness_sha256"):
            raise ValueError("runner witness hash disagreement")
        if receipt["canonical_sha256"] != recorded.get("canonical_sha256"):
            raise ValueError("runner canonical hash disagreement")
        if images & prior_images:
            raise ValueError("candidate duplicates the prior catalog")
        if images & batch_images:
            raise ValueError("candidate duplicates another batch member")
        receipt.update({
            "result": {"path": str(result_path.relative_to(ROOT)), "sha256": sha(result_path)},
            "status": "valid-new-link-orbit",
        })
        receipts.append(receipt)
        batch_images.update(images)

    return {
        "schema_version": 1,
        "status": "valid-distinct-new-link-orbits",
        "prior_catalog": {"path": str(prior_catalog_path.relative_to(ROOT)), "sha256": sha(prior_catalog_path)},
        "candidate_count": len(receipts),
        "candidates": receipts,
        "independence_basis": "Fresh direct link validation and full C2 wr S5 orbit enumeration, independent of the SAT encoding and runner validation.",
        "claim_limit": "Validates and distinguishes the supplied link orbits; it does not show that any extends to a 40-block cover or exhaust all link orbits.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-catalog", type=Path, required=True)
    parser.add_argument("--result", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prior = args.prior_catalog if args.prior_catalog.is_absolute() else ROOT / args.prior_catalog
    results = [path if path.is_absolute() else ROOT / path for path in args.result]
    output = args.output if args.output.is_absolute() else ROOT / args.output
    value = audit(prior, results)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
