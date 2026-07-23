#!/usr/bin/env python3
"""Build immutable incremental target-child aggregation receipts."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SOURCE = BASE / "manifest.json"
DIRECT = BASE / "shallow-weighted-gate-v1"
DEEP = BASE / "multi-deficit-propagation-gate-v1/weighted-complete-aggregation-v1"
SCALE = BASE / "shallow-weighted-scale-v1"
CENTRAL_IMPORT = SCALE / "central-import-v1/segments"
OUT = SCALE / "target-child-aggregation-v1/checkpoints"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def write(path: Path, value: object) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"refusing incompatible aggregation artifact: {path}")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def load_terminals() -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    terminals: dict[str, dict[str, object]] = {}
    sources: list[dict[str, object]] = []

    direct_summary_path = DIRECT / "summary.json"
    direct_audit_path = DIRECT / "independent-audit.json"
    direct_summary = json.loads(direct_summary_path.read_text())
    direct_audit = json.loads(direct_audit_path.read_text())
    if direct_audit["status"] != "VALID" or direct_audit["independently_checked_weighted_formulas"] != 36:
        raise ValueError("36-formula direct weighted audit is not valid")
    if direct_audit["summary_sha256"] != sha(direct_summary_path):
        raise ValueError("direct weighted summary binding failed")
    for row in direct_summary["outcomes"]:
        if row["weighted_certificate"] is None:
            raise ValueError("direct weighted outcome is not terminal")
        terminals[row["formula_id"]] = {
            "source_kind": "DIRECT_SHALLOW_WEIGHTED_GATE",
            "source_summary": ref(direct_summary_path),
            "source_audit": ref(direct_audit_path),
            "source_row_sha256": canonical_sha(row),
        }
    sources.append({"kind": "DIRECT_SHALLOW_WEIGHTED_GATE", "audit": ref(direct_audit_path)})

    deep_summary_path = DEEP / "summary.json"
    deep_audit_path = DEEP / "independent-audit.json"
    deep_summary = json.loads(deep_summary_path.read_text())
    deep_audit = json.loads(deep_audit_path.read_text())
    if deep_audit["status"] != "VALID" or deep_audit["formulas_independently_aggregated_closed"] != 12:
        raise ValueError("12-formula depth-two aggregation audit is not valid")
    if deep_audit["summary_sha256"] != sha(deep_summary_path):
        raise ValueError("depth-two aggregation summary binding failed")
    for row in deep_summary["formulas"]:
        formula_id = row["formula_id"]
        if formula_id in terminals:
            raise ValueError("duplicate direct/depth-two terminal formula")
        terminals[formula_id] = {
            "source_kind": "DEPTH_TWO_WEIGHTED_AGGREGATION",
            "formula_receipt": row["receipt"],
            "source_audit": ref(deep_audit_path),
        }
    sources.append({"kind": "DEPTH_TWO_WEIGHTED_AGGREGATION", "audit": ref(deep_audit_path)})

    for folder in sorted((SCALE / "segments").glob("shallow-weighted-scale-*")):
        audit_path = folder / "independent-audit.json"
        summary_path = folder / "summary.json"
        archive_path = folder / "outcomes.jsonl.gz"
        central_import_path = CENTRAL_IMPORT / f"{folder.name}.json"
        if not (
            audit_path.is_file()
            and summary_path.is_file()
            and archive_path.is_file()
            and central_import_path.is_file()
        ):
            continue
        central_import = json.loads(central_import_path.read_text())
        if (
            central_import["status"] != "VALID_CENTRAL_IMPORT"
            or central_import["segment_id"] != folder.name
            or central_import["bindings"]["summary"]["sha256"] != sha(summary_path)
            or central_import["bindings"]["independent_audit"]["sha256"] != sha(audit_path)
            or central_import["bindings"]["outcomes"]["sha256"] != sha(archive_path)
        ):
            raise ValueError(f"{folder.name}: central import binding failed")
        audit = json.loads(audit_path.read_text())
        summary = json.loads(summary_path.read_text())
        if audit["status"] not in {"VALID", "VALID_GATE_FAILED"}:
            raise ValueError(f"{folder.name}: invalid segment audit")
        if audit["summary_sha256"] != sha(summary_path):
            raise ValueError(f"{folder.name}: segment summary binding failed")
        outcomes = [
            json.loads(line)
            for line in gzip.decompress(archive_path.read_bytes()).splitlines()
        ]
        terminal_count = 0
        for row in outcomes:
            if row["certificate"] is None:
                continue
            formula_id = row["formula_id"]
            if formula_id in terminals:
                raise ValueError(f"duplicate terminal formula: {formula_id}")
            terminals[formula_id] = {
                "source_kind": "SHALLOW_WEIGHTED_SCALE",
                "segment_id": folder.name,
                "source_archive": ref(archive_path),
                "source_summary": ref(summary_path),
                "source_audit": ref(audit_path),
                "source_row_sha256": canonical_sha(row),
            }
            terminal_count += 1
        if terminal_count != audit["independently_checked_weighted_formulas"]:
            raise ValueError(f"{folder.name}: terminal count differs from audit")
        sources.append(
            {
                "kind": "SHALLOW_WEIGHTED_SCALE",
                "segment_id": folder.name,
                "terminal_formulas": terminal_count,
                "open_formulas": audit["open_no_certificate_count"],
                "audit": ref(audit_path),
                "central_import": ref(central_import_path),
            }
        )
    return terminals, sources


def main() -> None:
    source = json.loads(SOURCE.read_text())
    terminals, sources = load_terminals()
    checkpoint_id = canonical_sha(sources)[:20]
    folder = OUT / checkpoint_id
    rows = []
    for case in source["target_cases"]:
        expected = [
            f"{case['id']}-second-{index:03d}"
            for index in range(case["second_partition_children"])
        ]
        if not all(formula_id in terminals for formula_id in expected):
            continue
        receipt = {
            "schema_version": 1,
            "target_child_id": case["id"],
            "fifth_case_id": case["fifth_case_id"],
            "second_live_manifest": ref(SOURCE),
            "expected_formula_count": len(expected),
            "terminal_formulas": [
                {"formula_id": formula_id, **terminals[formula_id]}
                for formula_id in expected
            ],
            "status": "CLOSED_BY_EXHAUSTIVE_SECOND_FORMULA_AGGREGATION",
            "claim_limit": (
                "This closes only the exact first-deficit target child. The containing "
                "fifth leaf and all higher ancestors require separate complete aggregation."
            ),
        }
        receipt_path = folder / "target-children" / f"{case['id']}.json"
        write(receipt_path, receipt)
        rows.append(
            {
                "target_child_id": case["id"],
                "fifth_case_id": case["fifth_case_id"],
                "formula_count": len(expected),
                "receipt": ref(receipt_path),
            }
        )
    summary = {
        "schema_version": 1,
        "status": "BUILT_PENDING_INDEPENDENT_AUDIT",
        "checkpoint_id": checkpoint_id,
        "second_live_manifest": ref(SOURCE),
        "terminal_source_fingerprint": canonical_sha(sources),
        "terminal_sources": sources,
        "terminal_formula_count": len(terminals),
        "target_child_universe": len(source["target_cases"]),
        "target_children_closed": len(rows),
        "target_children_remaining": len(source["target_cases"]) - len(rows),
        "closed_target_children": rows,
        "ancestor_effect": {
            "fifth_leaves_closed": 0,
            "fourth_parents_closed": 0,
            "ordinary_classification_closed": False,
            "global_extension_ledger_change": 0,
        },
    }
    write(folder / "summary.json", summary)
    print(json.dumps({key: summary[key] for key in (
        "checkpoint_id", "terminal_formula_count", "target_children_closed",
        "target_children_remaining",
    )}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
