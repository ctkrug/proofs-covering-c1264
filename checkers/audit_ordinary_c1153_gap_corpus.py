#!/usr/bin/env python3
"""Independent source, membership, and residual-domain audit for gap-trim corpus."""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "checkers")]

from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from audit_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402
from audit_ordinary_c1153_shallow_weighted_scale import all_open_jobs  # noqa: E402


BASE = Path(
    "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/"
    "second-live-triple-gate-v1/shallow-weighted-scale-v1"
)
TARGET = ROOT / BASE.parent / "gap-trim-v1"
MANIFEST = TARGET / "manifest.json"
CORPUS = TARGET / "corpus.jsonl.gz"
AUDIT = TARGET / "corpus-independent-audit.json"
BLOCKS = tuple(itertools.combinations(range(1, 12), 5))
BLOCK_TRIPLES = tuple(frozenset(itertools.combinations(block, 3)) for block in BLOCKS)


def compact(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def object_sha(value: object) -> str:
    return sha_bytes(compact(value))


def git_bytes(commit: str, path: Path) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def independent_domain_sha(domain: dict[str, object]) -> str:
    return object_sha(
        {
            "fixed": list(domain["fixed"]),
            "forbidden": list(domain["forbidden"]),
            "available": list(domain["available"]),
            "uncovered": [list(row) for row in domain["uncovered"]],
            "remaining_slots": int(domain["remaining_slots"]),
        }
    )


def component_hashes(domain: dict[str, object]) -> dict[str, object]:
    return {
        "fixed_sha256": object_sha(domain["fixed"]),
        "forbidden_sha256": object_sha(domain["forbidden"]),
        "available_sha256": object_sha(domain["available"]),
        "uncovered_sha256": object_sha(domain["uncovered"]),
        "unit_recipe_sha256": object_sha(domain["units"]),
        "remaining_slots": domain["remaining_slots"],
    }


def audit() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    compressed = CORPUS.read_bytes()
    if sha_bytes(compressed) != manifest["corpus"]["sha256"]:
        raise ValueError("corpus archive hash mismatch")
    raw = gzip.decompress(compressed)
    if sha_bytes(raw) != manifest["corpus"]["uncompressed_sha256"]:
        raise ValueError("corpus payload hash mismatch")
    gaps = [json.loads(line) for line in raw.splitlines()]
    if len(gaps) != manifest["audited_gap_count"]:
        raise ValueError("corpus count mismatch")
    if len({row["case_id"] for row in gaps}) != len(gaps):
        raise ValueError("duplicate gap case ID")
    if len({row["exact_residual_domain_sha256"] for row in gaps}) != manifest[
        "unique_exact_residual_domain_count"
    ]:
        raise ValueError("unique exact-domain count mismatch")

    source_by_segment = {
        row["segment"]: row for row in manifest["source_receipts"]
    }
    if len(source_by_segment) != manifest["audited_segment_count"]:
        raise ValueError("duplicate source segment receipt")
    source_open: dict[str, dict[str, object]] = {}
    for number, receipt in source_by_segment.items():
        folder = BASE / "segments" / f"shallow-weighted-scale-{number:03d}"
        audit_raw = git_bytes(receipt["commit"], folder / "independent-audit.json")
        summary_raw = git_bytes(receipt["commit"], folder / "summary.json")
        audit_row = json.loads(audit_raw)
        summary = json.loads(summary_raw)
        if (
            sha_bytes(audit_raw) != receipt["audit_sha256"]
            or sha_bytes(summary_raw) != receipt["summary_sha256"]
            or audit_row["summary_sha256"] != sha_bytes(summary_raw)
            or audit_row["status"] not in {"VALID", "VALID_GATE_FAILED"}
        ):
            raise ValueError(f"segment {number}: source audit binding mismatch")
        archive_path = Path(summary["outcome_archive"]["path"])
        archive_raw = git_bytes(receipt["commit"], archive_path)
        if (
            sha_bytes(archive_raw) != receipt["archive_sha256"]
            or sha_bytes(archive_raw) != summary["outcome_archive"]["sha256"]
        ):
            raise ValueError(f"segment {number}: source archive binding mismatch")
        outcomes_raw = gzip.decompress(archive_raw)
        if sha_bytes(outcomes_raw) != summary["outcome_archive"]["uncompressed_sha256"]:
            raise ValueError(f"segment {number}: source archive payload mismatch")
        outcomes = [json.loads(line) for line in outcomes_raw.splitlines()]
        opened = [
            row for row in outcomes if row["status"] == "OPEN_NO_CERTIFICATE"
        ]
        if (
            len(opened) != audit_row["open_no_certificate_count"]
            or any(row["certificate"] is not None for row in opened)
        ):
            raise ValueError(f"segment {number}: source open set mismatch")
        for row in opened:
            if row["case_id"] in source_open:
                raise ValueError(f"duplicate source gap {row['case_id']}")
            source_open[row["case_id"]] = row

    jobs = {row["case_id"]: row for row in all_open_jobs()}
    source_manifest = json.loads(
        (
            ROOT
            / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/"
            "second-live-triple-gate-v1/manifest.json"
        ).read_text()
    )
    cases = {row["id"]: row for row in source_manifest["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    for gap in gaps:
        case_id = gap["case_id"]
        source = source_open.get(case_id)
        if source is None or source["domain"] != gap["domain"]:
            raise ValueError(f"{case_id}: missing or changed audited OPEN source")
        job = jobs[case_id]
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        domain = residual_domain(job, case, parents[parent_id])
        if component_hashes(domain) != gap["domain"]:
            raise ValueError(f"{case_id}: independently reconstructed components differ")
        if independent_domain_sha(domain) != gap["exact_residual_domain_sha256"]:
            raise ValueError(f"{case_id}: exact residual-domain hash differs")
        if gap["source_segment"] not in source_by_segment:
            raise ValueError(f"{case_id}: unbound source segment")
        if gap["features"]["remaining_slots"] != domain["remaining_slots"]:
            raise ValueError(f"{case_id}: structural slot feature differs")
        if gap["features"]["uncovered_triple_count"] != len(domain["uncovered"]):
            raise ValueError(f"{case_id}: uncovered count feature differs")
        if gap["features"]["available_block_count"] != len(domain["available"]):
            raise ValueError(f"{case_id}: available count feature differs")

    expected_sample = manifest["sample_case_ids"]
    if (
        len(expected_sample) != manifest["sample_size"]
        or len(set(expected_sample)) != len(expected_sample)
        or any(case_id not in {row["case_id"] for row in gaps} for case_id in expected_sample)
        or object_sha(expected_sample) != manifest["sample_case_ids_sha256"]
    ):
        raise ValueError("frozen sample membership mismatch")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": sha_bytes(MANIFEST.read_bytes()),
        "corpus_sha256": sha_bytes(compressed),
        "audited_source_segment_count": len(source_by_segment),
        "audited_gap_count": len(gaps),
        "unique_exact_residual_domain_count": len(
            {row["exact_residual_domain_sha256"] for row in gaps}
        ),
        "sample_size": len(expected_sample),
        "source_open_outcomes_reconciled": len(source_open),
        "domain_reconstruction_mismatches": 0,
        "claim_limit": "Corpus/source/domain audit only; no gap is closed.",
    }
    AUDIT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
