#!/usr/bin/env python3
"""Independent child-by-child audit of fourth-parent aggregation receipts."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIFTH = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
V2 = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"
AGG = ROOT / "artifacts/classification/ordinary-c1153-v1/fourth-parent-aggregation-v2"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_bound(binding: dict[str, str]) -> dict:
    path = ROOT / binding["path"]
    if sha(path) != binding["sha256"]:
        raise ValueError(f"hash mismatch: {binding['path']}")
    return json.loads(path.read_text())


def independently_certified() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for path in sorted((FIFTH / "suffix-certification/batches").glob("batch-*/cases/*/receipt.json")):
        row = json.loads(path.read_text())
        if row["status"] != "CERTIFIED_UNSAT" or row["replay_exit_code"] != 0:
            raise ValueError(f"invalid replay receipt: {path}")
        leaf = row["leaf_id"]
        if leaf in result:
            raise ValueError(f"duplicate certified leaf {leaf}")
        result[leaf] = {
            "kind": "EXHAUSTIVE_BATCH_REPLAY",
            "receipt_path": str(path.relative_to(ROOT)),
            "receipt_sha256": sha(path),
            "cnf_sha256": row["exact_cnf_sha256"],
            "proof_sha256": row["proof_sha256"],
            "checker_sha256": row["checker_sha256"],
        }

    for audit_path in sorted((FIFTH / "segments").glob("segment-*/independent-audit.json")):
        audit = json.loads(audit_path.read_text())
        if audit["status"] != "VALID":
            raise ValueError(f"invalid segment audit {audit_path}")
        audit_hash = sha(audit_path)
        for replay in audit["results"]:
            if replay["status"] != "UNSAT_REPLAYED":
                continue
            leaf = replay["leaf_id"]
            if leaf in result:
                raise ValueError(f"overlapping replay receipt {leaf}")
            source_path = audit_path.parent / leaf / "result.json"
            source = json.loads(source_path.read_text())
            if (
                source["leaf_id"] != leaf
                or source["proof"]["sha256"] != replay["proof_sha256"]
                or source["status"] not in {
                    "UNSAT_VERIFIED_BY_RUNNER",
                    "PROVISIONAL_UNSAT_PROOF_RETAINED",
                }
            ):
                raise ValueError(f"sampled replay binding mismatch {leaf}")
            result[leaf] = {
                "kind": "SEGMENT_SAMPLED_EXTERNAL_REPLAY",
                "receipt_path": str(audit_path.relative_to(ROOT)),
                "receipt_sha256": audit_hash,
                "source_path": str(source_path.relative_to(ROOT)),
                "source_sha256": sha(source_path),
                "cnf_sha256": source["exact_cnf_sha256"],
                "proof_sha256": replay["proof_sha256"],
                "checker_sha256": audit["checker_sha256"],
            }

    audit_path = FIFTH / "independent-discriminator-audit.json"
    audit = json.loads(audit_path.read_text())
    if audit["status"] != "VALID":
        raise ValueError("invalid discriminator audit")
    audit_hash = sha(audit_path)
    for replay in audit["results"]:
        if replay["status"] != "UNSAT_REPLAYED":
            continue
        leaf = replay["id"]
        if leaf in result:
            raise ValueError(f"overlapping discriminator receipt {leaf}")
        source_path = FIFTH / "discriminator-5s" / leaf / "result.json"
        source = json.loads(source_path.read_text())
        if (
            source["leaf_id"] != leaf
            or source["status"] != "UNSAT_VERIFIED"
            or source["proof"]["sha256"] != replay["proof_sha256"]
        ):
            raise ValueError(f"discriminator replay binding mismatch {leaf}")
        result[leaf] = {
            "kind": "DISCRIMINATOR_EXTERNAL_REPLAY",
            "receipt_path": str(audit_path.relative_to(ROOT)),
            "receipt_sha256": audit_hash,
            "source_path": str(source_path.relative_to(ROOT)),
            "source_sha256": sha(source_path),
            "cnf_sha256": source["exact_cnf_sha256"],
            "proof_sha256": replay["proof_sha256"],
            "checker_sha256": audit["checker_sha256"],
        }
    return result


def main() -> None:
    summary_path = AGG / "summary.json"
    summary = json.loads(summary_path.read_text())
    fifth = load_bound(summary["bindings"]["fifth_manifest"])
    v2 = load_bound(summary["bindings"]["v2_manifest"])
    v2_audit = load_bound(summary["bindings"]["v2_independent_audit"])
    if (
        v2_audit["status"] != "VALID"
        or v2_audit["manifest_sha256"] != summary["bindings"]["v2_manifest"]["sha256"]
    ):
        raise ValueError("v2 partition audit is not bound VALID")

    certified = independently_certified()
    open_rows = {row["id"]: row for row in v2["cases"]}
    if set(certified) & set(open_rows):
        raise ValueError("certified/open membership overlap")

    expected_parent_ids = {row["id"] for row in fifth["parents"]}
    summary_parents = {row["parent_id"]: row for row in summary["parents"]}
    if len(summary_parents) != len(summary["parents"]) or set(summary_parents) != expected_parent_ids:
        raise ValueError("parent summary membership mismatch")

    global_status = Counter()
    closed = []
    open_parents = []
    all_children: set[str] = set()
    semantic_count = 0
    for parent in fifth["parents"]:
        parent_id = parent["id"]
        summary_row = summary_parents[parent_id]
        receipt_path = ROOT / summary_row["receipt"]["path"]
        if sha(receipt_path) != summary_row["receipt"]["sha256"]:
            raise ValueError(f"{parent_id}: parent receipt hash mismatch")
        receipt = json.loads(receipt_path.read_text())
        children = receipt["children"]
        expected_ids = [
            f"{parent_id}-fifth-{index:03d}"
            for index in range(parent["branch_count"])
        ]
        if [row["leaf_id"] for row in children] != expected_ids:
            raise ValueError(f"{parent_id}: explicit child list mismatch")
        if set(expected_ids) & all_children:
            raise ValueError(f"{parent_id}: duplicate global child")
        all_children.update(expected_ids)

        terminal_count = 0
        for index, child in enumerate(children):
            leaf = expected_ids[index]
            if child["fifth_index"] != index:
                raise ValueError(f"{leaf}: fifth index mismatch")
            if leaf in certified:
                source = certified[leaf]
                if (
                    not child["terminal"]
                    or child["terminal_status"] != "REPLAY_CERTIFIED_UNSAT"
                    or child["certification_kind"] != source["kind"]
                    or child["certification_receipt"]["path"] != source["receipt_path"]
                    or child["certification_receipt"]["sha256"] != source["receipt_sha256"]
                    or child["exact_cnf_sha256"] != source["cnf_sha256"]
                    or child["proof_sha256"] != source["proof_sha256"]
                    or child["checker_sha256"] != source["checker_sha256"]
                    or child["checker_result"] != "VERIFIED"
                ):
                    raise ValueError(f"{leaf}: certified child aggregation mismatch")
                if "source_path" in source and (
                    child["source_result"]["path"] != source["source_path"]
                    or child["source_result"]["sha256"] != source["source_sha256"]
                ):
                    raise ValueError(f"{leaf}: source result binding mismatch")
            elif leaf in open_rows:
                source = open_rows[leaf]
                semantic = source["semantic_contradiction_receipt"]
                if source["branch_count"] == 0:
                    if (
                        not child["terminal"]
                        or child["terminal_status"] != "AUDITED_SEMANTIC_COVERAGE_CONTRADICTION"
                        or child["semantic_receipt"] != semantic
                        or child["semantic_receipt_sha256"] != canonical_sha(semantic)
                        or child["checker_receipt"]["sha256"]
                        != summary["bindings"]["v2_independent_audit"]["sha256"]
                        or child["checker_receipt"]["checker_result"] != "VALID"
                    ):
                        raise ValueError(f"{leaf}: semantic terminal mismatch")
                    semantic_count += 1
                else:
                    expected_status = (
                        "OPEN_FIXED_CAP_TIMEOUT"
                        if source["open_status"] == "FIXED_CAP_TIMEOUT"
                        else "OPEN_NEVER_MEASURED"
                    )
                    if (
                        child["terminal"]
                        or child["terminal_status"] != expected_status
                        or child["deficit_branch_count"] != source["branch_count"]
                    ):
                        raise ValueError(f"{leaf}: nonterminal child mismatch")
            else:
                raise ValueError(f"{leaf}: no independently reconstructed source")
            global_status[child["terminal_status"]] += 1
            terminal_count += bool(child["terminal"])

        remaining = len(children) - terminal_count
        expected_parent_status = (
            "CLOSED_BY_EXHAUSTIVE_CHILD_AGGREGATION"
            if remaining == 0
            else "OPEN_CHILDREN_REMAIN"
        )
        if (
            receipt["child_count"] != len(children)
            or receipt["terminal_children"] != terminal_count
            or receipt["remaining_children"] != remaining
            or receipt["parent_status"] != expected_parent_status
            or summary_row["child_count"] != len(children)
            or summary_row["terminal_children"] != terminal_count
            or summary_row["remaining_children"] != remaining
            or summary_row["parent_status"] != expected_parent_status
        ):
            raise ValueError(f"{parent_id}: parent aggregation count/status mismatch")
        (closed if remaining == 0 else open_parents).append(parent_id)

    counts = {
        "fourth_parents_total": len(fifth["parents"]),
        "fourth_parents_closed": len(closed),
        "fourth_parents_open": len(open_parents),
        "fifth_children_total": len(all_children),
        "replay_certified_unsat_children": len(certified),
        "semantic_contradiction_children": semantic_count,
        "remaining_open_children": sum(
            row["remaining_children"] for row in summary["parents"]
        ),
    }
    if (
        len(all_children) != 43_319
        or counts != summary["counts"]
        or dict(sorted(global_status.items())) != summary["terminal_status_counts"]
    ):
        raise ValueError("global aggregation mismatch")

    report = {
        "schema_version": 1,
        "status": "VALID",
        "summary_sha256": sha(summary_path),
        "aggregation_checker_sha256": sha(Path(__file__)),
        "bindings": summary["bindings"],
        "counts": counts,
        "newly_closed_fourth_parent_count": len(closed),
        "newly_closed_fourth_parent_ids": sorted(closed),
        "remaining_fourth_parent_ids": sorted(open_parents),
        "terminal_status_counts": dict(sorted(global_status.items())),
        "checked_properties": [
            "all 43,319 fifth children enumerated exactly once",
            "each replay terminal bound to its immutable receipt, proof hash, exact CNF hash, and checker result",
            "each semantic terminal bound to its exact v2 receipt and VALID independent partition audit",
            "no parent closed from counts or provisional solver status",
            "every closed parent has zero explicitly listed nonterminal children",
        ],
        "claim_limit": (
            "This audit closes fourth-level parents inside the ordinary-cover classification. "
            "It does not by itself complete that classification or settle C(12,6,4)."
        ),
    }
    output = AGG / "independent-audit.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
