#!/usr/bin/env python3
"""Independent full-segment audit of the future-only weighted backend v2."""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SCALE = BASE / "shallow-weighted-scale-v1"
REFERENCE = SCALE / "segments/shallow-weighted-scale-002/outcomes.jsonl.gz"
TARGET = SCALE / "performance-engineering-v1/optimized-workers-4"
OUTPUT = TARGET / "independent-audit.json"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from audit_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402
from run_ordinary_c1153_shallow_weighted_scale import (  # noqa: E402
    BLOCK_TRIPLES,
    object_sha,
    open_jobs,
    sha_bytes,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def domain_hashes(domain: dict[str, object]) -> dict[str, object]:
    return {
        "fixed_sha256": object_sha(domain["fixed"]),
        "forbidden_sha256": object_sha(domain["forbidden"]),
        "available_sha256": object_sha(domain["available"]),
        "uncovered_sha256": object_sha(domain["uncovered"]),
        "unit_recipe_sha256": object_sha(domain["units"]),
        "remaining_slots": domain["remaining_slots"],
    }


def audit() -> dict[str, object]:
    references = [
        json.loads(line)
        for line in gzip.decompress(REFERENCE.read_bytes()).splitlines()
    ]
    expected = open_jobs()[4096:6144]
    if [row["case_id"] for row in references] != [row["case_id"] for row in expected]:
        raise ValueError("immutable reference membership mismatch")
    chunks = sorted((TARGET / "chunks").glob("chunk-*.jsonl.gz"))
    if len(chunks) != 4:
        raise ValueError("optimized four-worker output must contain exactly four chunks")
    outcomes = [
        json.loads(line)
        for path in chunks
        for line in gzip.decompress(path.read_bytes()).splitlines()
    ]
    if [row["case_id"] for row in outcomes] != [row["case_id"] for row in expected]:
        raise ValueError("optimized output omitted, duplicated, or reordered formulas")
    source_cases = {
        row["id"]: row for row in json.loads((BASE / "manifest.json").read_text())["target_cases"]
    }
    _, parents, _, _ = reconstruct_hierarchy()
    terminal = 0
    matrices = set()
    for job, reference, result in zip(expected, references, outcomes):
        case = source_cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        parent_raw = parents[parent_id]
        if sha_bytes(parent_raw) != result["parent_cnf_sha256"]:
            raise ValueError(f"{job['case_id']}: parent reconstruction mismatch")
        domain = residual_domain(job, case, parent_raw)
        if domain_hashes(domain) != result["domain"] or result["domain"] != reference["domain"]:
            raise ValueError(f"{job['case_id']}: residual-domain disagreement")
        matrix_hash = object_sha(
            {
                "available": domain["available"],
                "uncovered": domain["uncovered"],
                "remaining_slots": domain["remaining_slots"],
            }
        )
        if matrix_hash != result["residual_matrix_identity_sha256"]:
            raise ValueError(f"{job['case_id']}: matrix-identity mismatch")
        matrices.add(matrix_hash)
        certificate = result["certificate"]
        reference_terminal = reference["certificate"] is not None
        if (certificate is not None) != reference_terminal or result["terminal"] != reference_terminal:
            raise ValueError(f"{job['case_id']}: terminal/nonterminal verdict mismatch")
        if certificate is None:
            continue
        weights: dict[tuple[int, ...], int] = {}
        uncovered = {tuple(row) for row in domain["uncovered"]}
        for row in certificate["weights"]:
            triple, numerator = tuple(row[:3]), row[3]
            if (
                triple not in uncovered
                or triple in weights
                or not isinstance(numerator, int)
                or numerator <= 0
            ):
                raise ValueError(f"{job['case_id']}: invalid certificate weight")
            weights[triple] = numerator
        total = sum(weights.values())
        denominator = certificate["denominator"]
        if (
            total != certificate["total_numerator"]
            or total <= domain["remaining_slots"] * denominator
        ):
            raise ValueError(f"{job['case_id']}: insufficient weighted bound")
        maximum = max(
            (
                sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
                for value in domain["available"]
            ),
            default=0,
        )
        if (
            maximum != certificate["maximum_eligible_block_load"]
            or maximum > denominator
        ):
            raise ValueError(f"{job['case_id']}: eligible-block overload")
        terminal += 1
    if terminal != 2043 or len(matrices) != 2048:
        raise ValueError("full benchmark terminal or matrix count mismatch")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "purpose": "Independent performance-equivalence audit only; no theorem ledger effect.",
        "reference_archive_sha256": sha(REFERENCE),
        "chunk_sha256": {path.name: sha(path) for path in chunks},
        "selected": len(outcomes),
        "formula_membership_and_order_agreement": len(outcomes),
        "independently_reconstructed_domain_agreement": len(outcomes),
        "terminal_nonterminal_verdict_agreement": len(outcomes),
        "independently_checked_exact_certificates": terminal,
        "open_reference_gaps": len(outcomes) - terminal,
        "unique_exact_residual_matrices": len(matrices),
        "missing_duplicate_or_extra_formulas": 0,
        "claim_limit": "Backend equivalence only. No campaign result was generated or promoted.",
    }
    raw = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text() != raw:
        raise ValueError("refusing incompatible independent audit")
    OUTPUT.write_text(raw)
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    audit()
