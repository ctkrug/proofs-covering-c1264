#!/usr/bin/env python3
"""Freeze audited OPEN_NO_CERTIFICATE outcomes into one exact gap corpus."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "checkers")]

from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from audit_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402
from audit_ordinary_c1153_shallow_weighted_scale import all_open_jobs  # noqa: E402
from ordinary_c1153_gap_trim import (  # noqa: E402
    compact,
    domain_component_hashes,
    exact_domain_sha,
    object_sha,
    structural_features,
)


BASE = Path(
    "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/"
    "second-live-triple-gate-v1/shallow-weighted-scale-v1"
)
TARGET = Path(
    os.environ.get("C1264_GAP_TRIM_OUTPUT", ROOT / BASE.parent / "gap-trim-v1")
).resolve()
CORPUS = TARGET / "corpus.jsonl.gz"
MANIFEST = TARGET / "manifest.json"
SOURCES = (
    ("origin/main", 0, 2),
    ("origin/shallow-scale-cloud-003-030", 3, 30),
    ("origin/shallow-scale-local-031-057", 31, 57),
    ("origin/shallow-scale-local-058-084", 58, 84),
)


def git(*args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, check=True
    )
    return result.stdout if binary else result.stdout.decode().strip()


def git_bytes(ref: str, path: Path) -> bytes:
    return git("show", f"{ref}:{path}", binary=True)


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(ref: str, path: Path) -> tuple[dict[str, object], bytes]:
    raw = git_bytes(ref, path)
    return json.loads(raw), raw


def available_segments(ref: str, low: int, high: int) -> list[int]:
    paths = git("ls-tree", "-r", "--name-only", ref).splitlines()
    prefix = str(BASE / "segments/shallow-weighted-scale-")
    suffix = "/independent-audit.json"
    found = []
    for path in paths:
        if path.startswith(prefix) and path.endswith(suffix):
            number = int(path[len(prefix) : len(prefix) + 3])
            if low <= number <= high:
                found.append(number)
    return sorted(found)


def load_segment(ref: str, number: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    folder = BASE / "segments" / f"shallow-weighted-scale-{number:03d}"
    audit, audit_raw = read_json(ref, folder / "independent-audit.json")
    summary, summary_raw = read_json(ref, folder / "summary.json")
    if audit["status"] not in {"VALID", "VALID_GATE_FAILED"}:
        raise ValueError(f"{ref} segment {number}: nonterminal audit")
    if audit["summary_sha256"] != sha_bytes(summary_raw):
        raise ValueError(f"{ref} segment {number}: audit-summary binding mismatch")
    archive_path = Path(summary["outcome_archive"]["path"])
    archive_raw = git_bytes(ref, archive_path)
    if sha_bytes(archive_raw) != summary["outcome_archive"]["sha256"]:
        raise ValueError(f"{ref} segment {number}: archive hash mismatch")
    raw = gzip.decompress(archive_raw)
    if sha_bytes(raw) != summary["outcome_archive"]["uncompressed_sha256"]:
        raise ValueError(f"{ref} segment {number}: archive payload mismatch")
    rows = [json.loads(line) for line in raw.splitlines()]
    checked = audit["independently_checked_weighted_formulas"]
    opened = audit["open_no_certificate_count"]
    if len(rows) != audit["selected"] or checked + opened != len(rows):
        raise ValueError(f"{ref} segment {number}: audited counts mismatch")
    for row in rows:
        if row["certificate"] is None:
            if row["status"] != "OPEN_NO_CERTIFICATE":
                raise ValueError(f"{row['case_id']}: null certificate status mismatch")
        elif row["status"] != "WEIGHTED_OBSTRUCTION_PENDING_AUDIT":
            raise ValueError(f"{row['case_id']}: certificate status mismatch")
    source = {
        "ref": ref,
        "commit": git("rev-parse", ref),
        "segment": number,
        "audit_sha256": sha_bytes(audit_raw),
        "summary_sha256": sha_bytes(summary_raw),
        "archive_sha256": sha_bytes(archive_raw),
        "selected": len(rows),
        "certified": checked,
        "open": opened,
    }
    return rows, source


def quantile_positions(rows: list[dict[str, object]], count: int) -> list[int]:
    if count <= 0 or not rows:
        return []
    if count == 1:
        return [0]
    if len(rows) <= count:
        return list(range(len(rows)))
    return sorted({round(index * (len(rows) - 1) / (count - 1)) for index in range(count)})


def build(sample_size: int, feature_workers: int) -> dict[str, object]:
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
    gaps: list[dict[str, object]] = []
    source_receipts = []
    seen_segments: set[int] = set()
    for ref, low, high in SOURCES:
        for number in available_segments(ref, low, high):
            if number in seen_segments:
                raise ValueError(f"duplicate owned segment {number}")
            seen_segments.add(number)
            outcomes, source = load_segment(ref, number)
            source_receipts.append(source)
            for result in outcomes:
                if result["status"] != "OPEN_NO_CERTIFICATE":
                    continue
                case_id = result["case_id"]
                job = jobs[case_id]
                case = cases[job["target_child_id"]]
                parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
                domain = residual_domain(job, case, parents[parent_id])
                if domain_component_hashes(domain) != result["domain"]:
                    raise ValueError(f"{case_id}: exact residual reconstruction mismatch")
                gaps.append(
                    {
                        "case_id": case_id,
                        "source_segment": number,
                        "source_ref": ref,
                        "source_commit": source["commit"],
                        "source_archive_sha256": source["archive_sha256"],
                        "source_audit_sha256": source["audit_sha256"],
                        "domain": result["domain"],
                        "exact_residual_domain_sha256": exact_domain_sha(domain),
                        "root_class": job["root_class"],
                        "rank_band": job["rank_band"],
                        "branch_count_quantile": job["branch_count_quantile"],
                        "stabilizer_tier": job["stabilizer_tier"],
                        "target_child_id": job["target_child_id"],
                        "second_index": job["second_index"],
                        "_domain": domain,
                    }
                )
    feature_workers = max(1, feature_workers)
    domains = [row["_domain"] for row in gaps]
    if feature_workers == 1:
        features = list(map(structural_features, domains))
    else:
        with multiprocessing.get_context("fork").Pool(feature_workers) as pool:
            features = pool.map(
                structural_features,
                domains,
                chunksize=max(1, len(domains) // (feature_workers * 16)),
            )
    for row, feature in zip(gaps, features, strict=True):
        row["features"] = feature
        del row["_domain"]
    gaps.sort(key=lambda row: row["case_id"])
    if len({row["case_id"] for row in gaps}) != len(gaps):
        raise ValueError("duplicate gap case ID")

    exact_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in gaps:
        exact_groups[row["exact_residual_domain_sha256"]].append(row)
    representatives = [min(rows, key=lambda row: row["case_id"]) for rows in exact_groups.values()]
    representatives.sort(key=lambda row: row["case_id"])

    strata: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in representatives:
        key = "|".join(
            (
                row["root_class"],
                row["rank_band"],
                row["branch_count_quantile"],
                row["stabilizer_tier"],
                str(row["features"]["remaining_slots"]),
                str(row["features"]["min_eligible_coverers"]),
            )
        )
        strata[key].append(row)
    selected: list[dict[str, object]] = []
    ordered_strata = sorted(strata)
    base = sample_size // max(1, len(ordered_strata))
    remainder = sample_size % max(1, len(ordered_strata))
    for index, key in enumerate(ordered_strata):
        rows = sorted(strata[key], key=lambda row: row["case_id"])
        take = min(len(rows), base + (index < remainder))
        selected.extend(rows[position] for position in quantile_positions(rows, take))
    if len(selected) < min(sample_size, len(representatives)):
        chosen = {row["case_id"] for row in selected}
        for row in representatives:
            if row["case_id"] not in chosen:
                selected.append(row)
                chosen.add(row["case_id"])
                if len(selected) == min(sample_size, len(representatives)):
                    break
    selected = sorted(selected[:sample_size], key=lambda row: row["case_id"])

    raw = b"".join(compact(row) + b"\n" for row in gaps)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    TARGET.mkdir(parents=True, exist_ok=True)
    CORPUS.write_bytes(compressed)
    cluster_counts = {
        "root_class": Counter(row["root_class"] for row in gaps),
        "rank_band": Counter(row["rank_band"] for row in gaps),
        "branch_count_quantile": Counter(row["branch_count_quantile"] for row in gaps),
        "stabilizer_tier": Counter(row["stabilizer_tier"] for row in gaps),
        "remaining_slots": Counter(str(row["features"]["remaining_slots"]) for row in gaps),
        "uncovered_triples": Counter(str(row["features"]["uncovered_triple_count"]) for row in gaps),
        "available_blocks": Counter(str(row["features"]["available_block_count"]) for row in gaps),
        "isomorphism_sha256": Counter(row["features"]["isomorphism_sha256"] for row in gaps),
    }
    manifest = {
        "schema_version": 1,
        "status": "FROZEN_AUDITED_SOURCE_CORPUS",
        "source_receipts": source_receipts,
        "audited_segment_count": len(source_receipts),
        "audited_segment_ids": sorted(seen_segments),
        "audited_gap_count": len(gaps),
        "unique_exact_residual_domain_count": len(exact_groups),
        "exact_duplicate_alias_count": len(gaps) - len(exact_groups),
        "exact_isomorphism_signature_count": len(
            {row["features"]["isomorphism_sha256"] for row in gaps}
        ),
        "corpus": {
            "path": str(CORPUS),
            "sha256": sha_bytes(compressed),
            "uncompressed_sha256": sha_bytes(raw),
        },
        "cluster_counts": {
            key: dict(sorted(value.items())) for key, value in cluster_counts.items()
        },
        "sample_size": len(selected),
        "sample_case_ids": [row["case_id"] for row in selected],
        "sample_case_ids_sha256": object_sha([row["case_id"] for row in selected]),
        "selection_rule": (
            "One exact-domain representative; proportional deterministic quantile spacing "
            "over root/rank/branch-quantile/stabilizer/slot/min-coverer strata, then "
            "lexicographic fill to exactly 512 when available."
        ),
        "feature_workers": feature_workers,
        "feature_parallelism_rule": (
            "Deterministic ordered multiprocessing over independently reconstructed exact "
            "domains; feature output is merged in case order."
        ),
        "isomorphism_rule": (
            "SHA-256 of pynauty's exact canonical certificate for the colored incidence "
            "graph with point, fixed-block, available-block, and uncovered-triple color cells."
        ),
        "claim_limit": (
            "Only independently audited OPEN_NO_CERTIFICATE outcomes enter this corpus. "
            "A gap is not a contradiction until a separate eliminator certificate passes."
        ),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=512)
    parser.add_argument("--feature-workers", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(build(args.sample_size, args.feature_workers), indent=2, sort_keys=True))
