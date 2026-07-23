#!/usr/bin/env python3
"""Aggregate certified fifth children and audited semantic contradictions."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIFTH = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
V2 = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"
OUT = ROOT / "artifacts/classification/ordinary-c1153-v1/fourth-parent-aggregation-v2"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def certified_entries() -> dict[str, dict[str, object]]:
    entries: dict[str, dict[str, object]] = {}
    batches = FIFTH / "suffix-certification/batches"
    for receipt_path in sorted(batches.glob("batch-*/cases/*/receipt.json")):
        receipt = json.loads(receipt_path.read_text())
        if receipt["status"] != "CERTIFIED_UNSAT" or receipt["replay_exit_code"] != 0:
            raise ValueError(f"invalid batch receipt {receipt_path}")
        leaf = receipt["leaf_id"]
        if leaf in entries:
            raise ValueError(f"duplicate certified leaf {leaf}")
        entries[leaf] = {
            "terminal": True,
            "terminal_status": "REPLAY_CERTIFIED_UNSAT",
            "certification_kind": "EXHAUSTIVE_BATCH_REPLAY",
            "certification_receipt": {
                "path": relative(receipt_path),
                "sha256": sha(receipt_path),
            },
            "exact_cnf_sha256": receipt["exact_cnf_sha256"],
            "proof_sha256": receipt["proof_sha256"],
            "checker_sha256": receipt["checker_sha256"],
            "checker_result": "VERIFIED",
        }

    for audit_path in sorted((FIFTH / "segments").glob("segment-*/independent-audit.json")):
        audit = json.loads(audit_path.read_text())
        audit_hash = sha(audit_path)
        for row in audit["results"]:
            if row["status"] != "UNSAT_REPLAYED":
                continue
            leaf = row["leaf_id"]
            if leaf in entries:
                raise ValueError(f"overlapping sampled/batch leaf {leaf}")
            result_path = audit_path.parent / leaf / "result.json"
            result = json.loads(result_path.read_text())
            if result["proof"]["sha256"] != row["proof_sha256"]:
                raise ValueError(f"{leaf}: sampled proof mismatch")
            entries[leaf] = {
                "terminal": True,
                "terminal_status": "REPLAY_CERTIFIED_UNSAT",
                "certification_kind": "SEGMENT_SAMPLED_EXTERNAL_REPLAY",
                "certification_receipt": {
                    "path": relative(audit_path),
                    "sha256": audit_hash,
                    "leaf_result_indexed_by": leaf,
                },
                "source_result": {
                    "path": relative(result_path),
                    "sha256": sha(result_path),
                },
                "exact_cnf_sha256": result["exact_cnf_sha256"],
                "proof_sha256": row["proof_sha256"],
                "checker_sha256": audit["checker_sha256"],
                "checker_result": "VERIFIED",
            }

    audit_path = FIFTH / "independent-discriminator-audit.json"
    audit = json.loads(audit_path.read_text())
    audit_hash = sha(audit_path)
    for row in audit["results"]:
        if row["status"] != "UNSAT_REPLAYED":
            continue
        leaf = row["id"]
        if leaf in entries:
            raise ValueError(f"overlapping discriminator leaf {leaf}")
        result_path = FIFTH / "discriminator-5s" / leaf / "result.json"
        result = json.loads(result_path.read_text())
        if result["status"] != "UNSAT_VERIFIED" or result["proof"]["sha256"] != row["proof_sha256"]:
            raise ValueError(f"{leaf}: discriminator receipt mismatch")
        entries[leaf] = {
            "terminal": True,
            "terminal_status": "REPLAY_CERTIFIED_UNSAT",
            "certification_kind": "DISCRIMINATOR_EXTERNAL_REPLAY",
            "certification_receipt": {
                "path": relative(audit_path),
                "sha256": audit_hash,
                "leaf_result_indexed_by": leaf,
            },
            "source_result": {
                "path": relative(result_path),
                "sha256": sha(result_path),
            },
            "exact_cnf_sha256": result["exact_cnf_sha256"],
            "proof_sha256": row["proof_sha256"],
            "checker_sha256": audit["checker_sha256"],
            "checker_result": "VERIFIED",
        }
    return entries


def main() -> None:
    fifth_path = FIFTH / "manifest.json"
    v2_path = V2 / "manifest.json"
    v2_audit_path = V2 / "independent-audit.json"
    fifth = json.loads(fifth_path.read_text())
    v2 = json.loads(v2_path.read_text())
    v2_audit = json.loads(v2_audit_path.read_text())
    fifth_hash = sha(fifth_path)
    v2_hash = sha(v2_path)
    v2_audit_hash = sha(v2_audit_path)
    if v2_audit["status"] != "VALID" or v2_audit["manifest_sha256"] != v2_hash:
        raise ValueError("v2 independent audit binding failed")

    certified = certified_entries()
    open_rows = {row["id"]: row for row in v2["cases"]}
    semantic: dict[str, dict[str, object]] = {}
    for leaf, row in open_rows.items():
        receipt = row["semantic_contradiction_receipt"]
        if row["branch_count"] == 0:
            if receipt is None:
                raise ValueError(f"{leaf}: zero child lacks semantic receipt")
            semantic[leaf] = {
                "terminal": True,
                "terminal_status": "AUDITED_SEMANTIC_COVERAGE_CONTRADICTION",
                "certification_kind": "EMPTY_RESIDUAL_COVERAGE_CLAUSE",
                "semantic_receipt_sha256": canonical_sha(receipt),
                "semantic_receipt": receipt,
                "manifest_binding": {"path": relative(v2_path), "sha256": v2_hash},
                "checker_receipt": {
                    "path": relative(v2_audit_path),
                    "sha256": v2_audit_hash,
                    "checker_result": "VALID",
                },
            }

    overlap = set(certified) & set(open_rows)
    if overlap:
        raise ValueError(f"certified/open overlap: {next(iter(overlap))}")
    receipts_dir = OUT / "parents"
    parent_summaries = []
    global_status = Counter()
    all_children: set[str] = set()
    for parent in fifth["parents"]:
        children = []
        for index in range(parent["branch_count"]):
            leaf = f"{parent['id']}-fifth-{index:03d}"
            if leaf in all_children:
                raise ValueError(f"duplicate fifth leaf {leaf}")
            all_children.add(leaf)
            if leaf in certified:
                terminal = certified[leaf]
            elif leaf in semantic:
                terminal = semantic[leaf]
            elif leaf in open_rows:
                row = open_rows[leaf]
                terminal = {
                    "terminal": False,
                    "terminal_status": (
                        "OPEN_FIXED_CAP_TIMEOUT"
                        if row["open_status"] == "FIXED_CAP_TIMEOUT"
                        else "OPEN_NEVER_MEASURED"
                    ),
                    "open_status": row["open_status"],
                    "deficit_branch_count": row["branch_count"],
                    "deficit_manifest_binding": {
                        "path": relative(v2_path),
                        "sha256": v2_hash,
                    },
                }
            else:
                raise ValueError(f"{leaf}: no exact terminal/open source")
            child = {"leaf_id": leaf, "fifth_index": index, **terminal}
            children.append(child)
            global_status[child["terminal_status"]] += 1

        complete = all(row["terminal"] for row in children)
        receipt = {
            "schema_version": 1,
            "parent_id": parent["id"],
            "top_parent": parent["top_parent"],
            "fifth_manifest_binding": {
                "path": relative(fifth_path),
                "sha256": fifth_hash,
            },
            "child_count": len(children),
            "children": children,
            "terminal_children": sum(row["terminal"] for row in children),
            "remaining_children": sum(not row["terminal"] for row in children),
            "parent_status": (
                "CLOSED_BY_EXHAUSTIVE_CHILD_AGGREGATION"
                if complete
                else "OPEN_CHILDREN_REMAIN"
            ),
            "aggregation_claim": (
                "Every fifth child has an immutable replay-certified UNSAT receipt or an "
                "independently audited empty-residual-coverage semantic contradiction."
                if complete
                else "This parent is not closed."
            ),
        }
        receipt_path = receipts_dir / f"{parent['id']}.json"
        atomic_json(receipt_path, receipt)
        parent_summaries.append({
            "parent_id": parent["id"],
            "child_count": len(children),
            "terminal_children": receipt["terminal_children"],
            "remaining_children": receipt["remaining_children"],
            "parent_status": receipt["parent_status"],
            "receipt": {"path": relative(receipt_path), "sha256": sha(receipt_path)},
        })

    if len(all_children) != 43_319:
        raise ValueError("global fifth child count mismatch")
    summary = {
        "schema_version": 1,
        "status": "BUILT_PENDING_INDEPENDENT_AUDIT",
        "bindings": {
            "fifth_manifest": {"path": relative(fifth_path), "sha256": fifth_hash},
            "v2_manifest": {"path": relative(v2_path), "sha256": v2_hash},
            "v2_independent_audit": {
                "path": relative(v2_audit_path),
                "sha256": v2_audit_hash,
            },
        },
        "counts": {
            "fourth_parents_total": len(parent_summaries),
            "fourth_parents_closed": sum(
                row["parent_status"] == "CLOSED_BY_EXHAUSTIVE_CHILD_AGGREGATION"
                for row in parent_summaries
            ),
            "fourth_parents_open": sum(
                row["parent_status"] == "OPEN_CHILDREN_REMAIN"
                for row in parent_summaries
            ),
            "fifth_children_total": len(all_children),
            "replay_certified_unsat_children": len(certified),
            "semantic_contradiction_children": len(semantic),
            "remaining_open_children": 0,
        },
        "terminal_status_counts": dict(sorted(global_status.items())),
        "parents": parent_summaries,
        "claim_limit": (
            "Only parents whose complete explicit child list is terminal are closed. "
            "Semantic contradictions are not labeled solver-UNSAT."
        ),
    }
    summary["counts"]["remaining_open_children"] = sum(
        row["remaining_children"] for row in parent_summaries
    )
    atomic_json(OUT / "summary.json", summary)
    print(json.dumps(summary["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
