#!/usr/bin/env python3
"""Audit whether the frozen shallow residual has an existing terminal mapping."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2/second-live-triple-gate-v1"
SCALE = BASE / "shallow-weighted-scale-v1"
CHECKPOINT = SCALE / "target-child-aggregation-v1/checkpoints/6dacf26a6c3a8595b90b"
PARTIAL_AUDIT = CHECKPOINT / "independent-audit.json"
RESIDUAL = CHECKPOINT / "formula-universe-residual.jsonl.gz"
FINAL = SCALE / "final-gap-portfolio-v2"
DIRECT = BASE / "shallow-weighted-gate-v1"
DEEP = BASE / "multi-deficit-propagation-gate-v1/weighted-complete-aggregation-v1"
CENTRAL = SCALE / "central-import-v1/segments"
OUTPUT = CHECKPOINT / "residual-existing-terminal-scan-independent-audit.json"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402
from run_ordinary_c1153_ilp_forced_gate import residual_domain  # noqa: E402
from run_ordinary_c1153_shallow_weighted_scale import all_jobs  # noqa: E402


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def object_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def domain_binding(domain: dict[str, object]) -> str:
    return object_sha(domain)


def summarized_domain(domain: dict[str, object]) -> dict[str, object]:
    return {
        "fixed_sha256": object_sha(domain["fixed"]),
        "forbidden_sha256": object_sha(domain["forbidden"]),
        "available_sha256": object_sha(domain["available"]),
        "uncovered_sha256": object_sha(domain["uncovered"]),
        "unit_recipe_sha256": object_sha(domain["units"]),
        "remaining_slots": domain["remaining_slots"],
    }


def add_terminal(
    terminals: dict[str, tuple[str, str]],
    formula_id: str,
    source_kind: str,
    binding: str,
) -> None:
    if formula_id in terminals:
        raise ValueError(f"duplicate existing terminal formula: {formula_id}")
    terminals[formula_id] = (source_kind, binding)


def write_immutable(path: Path, value: object) -> None:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("refusing incompatible residual scan audit")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


def main() -> None:
    partial = json.loads(PARTIAL_AUDIT.read_text())
    if (
        partial["status"] != "VALID_PARTIAL_BOUNDARY"
        or partial["residual_formula_count"] != 3_884
        or partial["formula_universe_count"] != 173_880
        or partial["terminal_formulas_in_universe"] != 169_996
        or partial["higher_promotion_allowed"]
        or sha(RESIDUAL) != partial["residual_formula_index"]["sha256"]
    ):
        raise ValueError("partial boundary is not the expected fail-closed receipt")
    with gzip.open(RESIDUAL, "rt") as stream:
        residual_rows = [json.loads(line) for line in stream]
    residual_ids = {row["formula_id"] for row in residual_rows}
    if len(residual_rows) != 3_884 or len(residual_ids) != 3_884:
        raise ValueError("residual membership is not exactly 3,884 unique formulas")

    terminals: dict[str, tuple[str, str]] = {}
    all_scale_domains: dict[str, str] = {}
    scale_segment_by_formula: dict[str, str] = {}
    main_terminal_count = 0
    for folder in sorted((SCALE / "segments").glob("shallow-weighted-scale-*")):
        audit_path = folder / "independent-audit.json"
        archive_path = folder / "outcomes.jsonl.gz"
        central_path = CENTRAL / f"{folder.name}.json"
        audit = json.loads(audit_path.read_text())
        central = json.loads(central_path.read_text())
        if (
            audit["status"] not in {"VALID", "VALID_GATE_FAILED"}
            or central["status"] != "VALID_CENTRAL_IMPORT"
            or central["bindings"]["independent_audit"]["sha256"] != sha(audit_path)
            or central["bindings"]["outcomes"]["sha256"] != sha(archive_path)
        ):
            raise ValueError(f"{folder.name}: audited source binding failed")
        checked = 0
        with gzip.open(archive_path, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                formula_id = row["formula_id"]
                binding = domain_binding(row["domain"])
                if formula_id in all_scale_domains:
                    raise ValueError("duplicate formula across scale archives")
                all_scale_domains[formula_id] = binding
                scale_segment_by_formula[formula_id] = folder.name
                if row["certificate"] is not None:
                    add_terminal(terminals, formula_id, "SHALLOW_WEIGHTED_SCALE", binding)
                    checked += 1
                    main_terminal_count += 1
        if checked != audit["independently_checked_weighted_formulas"]:
            raise ValueError(f"{folder.name}: terminal count differs from audit")

    final_audit_path = FINAL / "independent-audit.json"
    final_index_path = FINAL / "terminal-formula-index.jsonl.gz"
    final_audit = json.loads(final_audit_path.read_text())
    if (
        final_audit["status"] != "VALID"
        or final_audit["terminal_count"] != 9_337
        or final_audit["terminal_index_sha256"] != sha(final_index_path)
    ):
        raise ValueError("final gap terminal index is not independently valid")
    final_ids: set[str] = set()
    with gzip.open(final_index_path, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            formula_id = row["formula_id"]
            if row["status"] != "CLOSED" or formula_id not in all_scale_domains:
                raise ValueError("final gap terminal lacks an exact scale-domain binding")
            add_terminal(
                terminals, formula_id, "FINAL_GAP_PORTFOLIO",
                all_scale_domains[formula_id],
            )
            final_ids.add(formula_id)
    if len(final_ids) != 9_337:
        raise ValueError("final gap terminal membership count mismatch")

    direct_summary_path = DIRECT / "summary.json"
    direct_audit_path = DIRECT / "independent-audit.json"
    direct_summary = json.loads(direct_summary_path.read_text())
    direct_audit = json.loads(direct_audit_path.read_text())
    if (
        direct_audit["status"] != "VALID"
        or direct_audit["independently_checked_weighted_formulas"] != 36
        or direct_audit["summary_sha256"] != sha(direct_summary_path)
    ):
        raise ValueError("direct terminal source is not independently valid")
    for row in direct_summary["outcomes"]:
        if row["weighted_certificate"] is None:
            raise ValueError("direct source contains a nonterminal outcome")
        add_terminal(
            terminals, row["formula_id"], "DIRECT_SHALLOW_WEIGHTED_GATE",
            domain_binding(row["domain"]),
        )

    deep_summary_path = DEEP / "summary.json"
    deep_audit_path = DEEP / "independent-audit.json"
    deep_summary = json.loads(deep_summary_path.read_text())
    deep_audit = json.loads(deep_audit_path.read_text())
    if (
        deep_audit["status"] != "VALID"
        or deep_audit["formulas_independently_aggregated_closed"] != 12
        or deep_audit["summary_sha256"] != sha(deep_summary_path)
    ):
        raise ValueError("depth-two terminal source is not independently valid")
    deep_ids = {row["formula_id"] for row in deep_summary["formulas"]}
    jobs = {row["formula_id"]: row for row in all_jobs() if row["formula_id"] in deep_ids}
    source = json.loads((BASE / "manifest.json").read_text())
    cases = {row["id"]: row for row in source["target_cases"]}
    _, parents, _, _ = reconstruct_hierarchy()
    for formula_id in sorted(deep_ids):
        job = jobs[formula_id]
        case = cases[job["target_child_id"]]
        parent_id = Path(case["third_level_parent_cnf"]["path"]).parent.name
        exact = residual_domain(job, case, parents[parent_id])
        add_terminal(
            terminals, formula_id, "DEPTH_TWO_WEIGHTED_AGGREGATION",
            domain_binding(summarized_domain(exact)),
        )

    if (
        main_terminal_count != 160_611
        or len(terminals) != 169_996
        or set(terminals) & residual_ids
    ):
        raise ValueError("existing terminal formula-ID universe differs from boundary")
    residual_bindings = {
        formula_id: all_scale_domains[formula_id]
        for formula_id in residual_ids
    }
    terminal_binding_sources: dict[str, list[str]] = {}
    for formula_id, (_, binding) in terminals.items():
        terminal_binding_sources.setdefault(binding, []).append(formula_id)
    transferable = {
        formula_id: terminal_binding_sources[binding]
        for formula_id, binding in residual_bindings.items()
        if binding in terminal_binding_sources
    }

    all_segment_ids = {
        path.parent.name
        for path in (SCALE / "segments").glob("shallow-weighted-scale-*/independent-audit.json")
    }
    final_segments = {scale_segment_by_formula[formula_id] for formula_id in final_ids}
    absent_corpus_segments = sorted(all_segment_ids - final_segments)
    residual_segments = sorted({
        scale_segment_by_formula[formula_id]
        for formula_id in residual_ids
    })
    if (
        len(all_segment_ids) != 85
        or len(final_segments) != 47
        or len(absent_corpus_segments) != 38
        or len(residual_segments) != 37
        or "shallow-weighted-scale-050" not in absent_corpus_segments
        or "shallow-weighted-scale-050" in residual_segments
    ):
        raise ValueError("38-absent/37-residual segment reconciliation failed")

    exact_id_matches = len(set(terminals) & residual_ids)
    exact_domain_matches = len(transferable)
    unmatched = len(residual_ids) - exact_id_matches - exact_domain_matches
    report = {
        "schema_version": 1,
        "artifact_type": "ORDINARY_C1153_RESIDUAL_EXISTING_TERMINAL_SCAN_AUDIT",
        "status": "VALID_NO_EXISTING_TERMINAL_TRANSFER",
        "checkpoint_partial_audit": {
            "path": str(PARTIAL_AUDIT.relative_to(ROOT)),
            "sha256": sha(PARTIAL_AUDIT),
        },
        "residual_index": {
            "path": str(RESIDUAL.relative_to(ROOT)),
            "sha256": sha(RESIDUAL),
            "membership_sha256": object_sha(sorted(residual_ids)),
        },
        "counts": {
            "formula_universe": 173_880,
            "existing_terminal_formulas_scanned": len(terminals),
            "residual_formulas_scanned": len(residual_ids),
            "exact_formula_id_matches": exact_id_matches,
            "exact_domain_transferable_matches": exact_domain_matches,
            "genuinely_without_existing_terminal": unmatched,
            "targets_remaining": partial["target_children_remaining"],
        },
        "terminal_source_counts": {
            "shallow_weighted_scale": main_terminal_count,
            "final_gap_portfolio": len(final_ids),
            "direct_shallow_weighted_gate": 36,
            "depth_two_weighted_aggregation": len(deep_ids),
        },
        "segment_reconciliation": {
            "scale_segments_total": len(all_segment_ids),
            "final_gap_corpus_present_segments": len(final_segments),
            "final_gap_corpus_absent_segments": len(absent_corpus_segments),
            "final_gap_corpus_absent_segment_ids": absent_corpus_segments,
            "residual_bearing_segments": len(residual_segments),
            "residual_bearing_segment_ids": residual_segments,
            "absent_but_no_gap_segment_id": "shallow-weighted-scale-050",
        },
        "transfer_receipts_emitted": 0,
        "hierarchy_stage_status": "BLOCKED_INCOMPLETE",
        "higher_aggregation_resumed": False,
        "higher_promotion_allowed": False,
        "claim_limit": (
            "This is a read-only scan of existing independently audited terminal "
            "sources. No exact-ID or exact-domain transfer exists for the 3,884 "
            "residual formulas. It creates no new contradiction, closes no target "
            "child or ancestor, and authorizes no hierarchy or theorem promotion."
        ),
        "checker_sha256": sha(Path(__file__)),
    }
    if exact_id_matches or exact_domain_matches or unmatched != 3_884:
        raise ValueError("unexpected existing residual terminal mapping")
    write_immutable(OUTPUT, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
