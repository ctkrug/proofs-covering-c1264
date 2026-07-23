#!/usr/bin/env python3
"""Independently audit one incremental shallow target-child aggregation."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
OUT = BASE / "shallow-weighted-scale-v1/target-child-aggregation-v1/checkpoints"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def check_ref(value: dict[str, str]) -> Path:
    path = ROOT / value["path"]
    if not path.is_file() or sha(path) != value["sha256"]:
        raise ValueError(f"bad aggregation binding: {value}")
    return path


def write(path: Path, value: object) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("refusing incompatible aggregation audit")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def source_rows(summary: dict[str, object]) -> dict[str, dict[str, object]]:
    terminals: dict[str, dict[str, object]] = {}
    for source in summary["terminal_sources"]:
        audit_path = check_ref(source["audit"])
        audit = json.loads(audit_path.read_text())
        if audit["status"] not in {"VALID", "VALID_GATE_FAILED"}:
            raise ValueError("terminal source audit is not valid")
        if source["kind"] == "DIRECT_SHALLOW_WEIGHTED_GATE":
            summary_path = audit_path.parent / "summary.json"
            for row in json.loads(summary_path.read_text())["outcomes"]:
                if row["weighted_certificate"] is not None:
                    terminals[row["formula_id"]] = {
                        "source_kind": source["kind"],
                        "row_sha256": canonical_sha(row),
                    }
        elif source["kind"] == "DEPTH_TWO_WEIGHTED_AGGREGATION":
            source_summary = audit_path.parent / "summary.json"
            for row in json.loads(source_summary.read_text())["formulas"]:
                check_ref(row["receipt"])
                terminals[row["formula_id"]] = {"source_kind": source["kind"]}
        else:
            central_import_path = check_ref(source["central_import"])
            central_import = json.loads(central_import_path.read_text())
            if central_import["status"] != "VALID_CENTRAL_IMPORT":
                raise ValueError("scale source lacks a valid central import")
            segment = audit_path.parent
            archive = segment / "outcomes.jsonl.gz"
            if (
                central_import["bindings"]["independent_audit"]["sha256"] != sha(audit_path)
                or central_import["bindings"]["outcomes"]["sha256"] != sha(archive)
            ):
                raise ValueError("central import does not bind the aggregation source")
            outcomes = [
                json.loads(line)
                for line in gzip.decompress(archive.read_bytes()).splitlines()
            ]
            for row in outcomes:
                if row["certificate"] is not None:
                    if row["formula_id"] in terminals:
                        raise ValueError("duplicate terminal formula across sources")
                    terminals[row["formula_id"]] = {
                        "source_kind": source["kind"],
                        "row_sha256": canonical_sha(row),
                    }
    return terminals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args()
    folder = OUT / args.checkpoint
    summary_path = folder / "summary.json"
    summary = json.loads(summary_path.read_text())
    source = json.loads(check_ref(summary["second_live_manifest"]).read_text())
    terminals = source_rows(summary)
    if len(terminals) != summary["terminal_formula_count"]:
        raise ValueError("terminal formula count mismatch")

    expected_closed: dict[str, list[str]] = {}
    for case in source["target_cases"]:
        expected = [
            f"{case['id']}-second-{index:03d}"
            for index in range(case["second_partition_children"])
        ]
        if all(formula_id in terminals for formula_id in expected):
            expected_closed[case["id"]] = expected
    if set(expected_closed) != {
        row["target_child_id"] for row in summary["closed_target_children"]
    }:
        raise ValueError("closed target-child set is not exact")

    seen: set[str] = set()
    for row in summary["closed_target_children"]:
        receipt_path = check_ref(row["receipt"])
        receipt = json.loads(receipt_path.read_text())
        target = row["target_child_id"]
        ids = [item["formula_id"] for item in receipt["terminal_formulas"]]
        if (
            receipt["target_child_id"] != target
            or ids != expected_closed[target]
            or len(ids) != receipt["expected_formula_count"]
            or receipt["status"] != "CLOSED_BY_EXHAUSTIVE_SECOND_FORMULA_AGGREGATION"
        ):
            raise ValueError(f"{target}: aggregation receipt is not exact")
        for item in receipt["terminal_formulas"]:
            formula_id = item["formula_id"]
            if formula_id in seen:
                raise ValueError("formula reused across target-child receipts")
            seen.add(formula_id)
            if item["source_kind"] != terminals[formula_id]["source_kind"]:
                raise ValueError(f"{formula_id}: terminal source kind mismatch")
            if "source_row_sha256" in item and item["source_row_sha256"] != terminals[formula_id]["row_sha256"]:
                raise ValueError(f"{formula_id}: source outcome row mismatch")
            for key in ("source_archive", "source_summary", "source_audit", "formula_receipt"):
                if key in item:
                    check_ref(item[key])
    report = {
        "schema_version": 1,
        "status": "VALID",
        "checkpoint_id": args.checkpoint,
        "summary_sha256": sha(summary_path),
        "terminal_formulas_available": len(terminals),
        "target_children_independently_aggregated_closed": len(expected_closed),
        "terminal_formula_memberships_checked": len(seen),
        "target_children_remaining": len(source["target_cases"]) - len(expected_closed),
        "ancestor_effect": summary["ancestor_effect"],
        "claim_limit": (
            "Only the listed target children close. Fifth leaves and higher ancestors "
            "remain unchanged absent their own complete aggregation audits."
        ),
    }
    if any(summary["ancestor_effect"].values()):
        raise ValueError("unsupported ancestor effect asserted")
    write(folder / "independent-audit.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
