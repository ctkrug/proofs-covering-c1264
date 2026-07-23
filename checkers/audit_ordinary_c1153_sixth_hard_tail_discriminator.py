#!/usr/bin/env python3
"""Independent cell-count audit of the proposed sixth-block discriminator."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
TARGET = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-sixth-discriminator-final/manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def parent_negative_units(path: Path) -> set[int]:
    result = set()
    with path.open() as handle:
        for line in handle:
            if not line or line[0] in "cp%0":
                continue
            words = line.split()
            if len(words) == 2 and words[1] == "0" and -462 <= int(words[0]) < 0:
                result.add(-int(words[0]))
    return result


def audit() -> dict[str, object]:
    manifest = json.loads(TARGET.read_text())
    predecessor_path = ROOT / manifest["predecessor"]["path"]
    if sha(predecessor_path) != manifest["predecessor"]["sha256"]:
        raise ValueError("predecessor manifest hash mismatch")
    predecessor = json.loads(predecessor_path.read_text())
    predecessor_by_id = {case["id"]: case for case in predecessor["cases"]}
    predecessor_ids = set(predecessor_by_id)
    if len(predecessor_ids) != manifest["predecessor"]["case_count"]:
        raise ValueError("predecessor case count mismatch")
    fifth_path = ROOT / manifest["fifth_manifest"]["path"]
    if sha(fifth_path) != manifest["fifth_manifest"]["sha256"]:
        raise ValueError("fifth manifest hash mismatch")
    fifth = json.loads(fifth_path.read_text())
    parent_by_id = {row["id"]: row for row in fifth["parents"]}
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    expected_timeout_ids = set()
    discriminator_path = ROOT / manifest["source_snapshot"]["discriminator"]["path"]
    if sha(discriminator_path) != manifest["source_snapshot"]["discriminator"]["sha256"]:
        raise ValueError("discriminator source hash mismatch")
    discriminator = json.loads(discriminator_path.read_text())
    expected_timeout_ids.update(
        row["leaf_id"] for row in discriminator["outcomes"] if row["status"] == "FIXED_CAP_TIMEOUT"
    )
    for segment in manifest["source_snapshot"]["suffix_ledger_snapshot"]["segments"]:
        segment_dir = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split/segments" / f"segment-{segment:04d}"
        result_paths = sorted(segment_dir.glob("*/result.json"))
        receipt = json.loads((segment_dir / "runner-receipt.json").read_text())
        if len(result_paths) != receipt["selected"] or receipt["completed"] != receipt["selected"]:
            raise ValueError(f"segment {segment}: source snapshot is not a complete segment")
        for result_path in result_paths:
            result = json.loads(result_path.read_text())
            if result["status"] == "FIXED_CAP_TIMEOUT":
                expected_timeout_ids.add(result["leaf_id"])
    seen = set()
    total = 0
    summaries = []
    for case in manifest["cases"]:
        if case["id"] in seen:
            raise ValueError("duplicate timeout case")
        seen.add(case["id"])
        source_path = ROOT / case["source_result"]["path"]
        if sha(source_path) != case["source_result"]["sha256"]:
            raise ValueError(f"{case['id']}: source result hash mismatch")
        source = json.loads(source_path.read_text())
        if case["source_result"]["kind"] == "discriminator":
            matches = [row for row in source["outcomes"] if row["leaf_id"] == case["id"]]
            if len(matches) != 1:
                raise ValueError(f"{case['id']}: missing discriminator outcome")
            source = matches[0]
        if source["leaf_id"] != case["id"] or source["status"] != "FIXED_CAP_TIMEOUT":
            raise ValueError(f"{case['id']}: source is not an exact timeout")
        parent = parent_by_id[source["fourth_parent_id"]]
        index = source["fifth_index"]
        expected_units = [
            *parent["inherited_fourth_units"],
            *[-value for orbit in parent["fifth_orbits"][:index] for value in orbit["member_variables"]],
            parent["fifth_orbits"][index]["canonical_variable"],
        ]
        if case["inherited_units"] != expected_units or unit_sha(expected_units) != case["inherited_unit_sha256"]:
            raise ValueError(f"{case['id']}: inherited unit mismatch")
        fixed = tuple(tuple(block) for block in case["fixed_blocks"])
        expected_fixed = (*tuple(tuple(block) for block in parent["fixed_blocks"]), tuple(parent["fifth_orbits"][index]["canonical_block"]))
        if fixed != expected_fixed:
            raise ValueError(f"{case['id']}: five-block binding mismatch")

        cnf_path = ROOT / case["third_level_parent_cnf"]["path"]
        if sha(cnf_path) != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{case['id']}: parent CNF mismatch")
        absent = parent_negative_units(cnf_path) | {-value for value in expected_units if value < 0}
        available = set(BLOCKS) - {BLOCKS[value - 1] for value in absent} - set(fixed)
        cells = {}
        for signature in itertools.product((False, True), repeat=5):
            cell = tuple(point for point in POINTS if tuple(point in block for block in fixed) == signature)
            if cell:
                cells[signature] = cell
        order = math.prod(math.factorial(len(cell)) for cell in cells.values())
        if order != case["stabilizer_order"]:
            raise ValueError(f"{case['id']}: stabilizer order mismatch")
        groups: dict[tuple[int, ...], set[tuple[int, ...]]] = defaultdict(set)
        for block in available:
            key = tuple(len(set(block) & set(cell)) for _, cell in sorted(cells.items()))
            groups[key].add(block)
        expected_orbits = sorted(groups.values(), key=min)
        if len(expected_orbits) != case["branch_count"] or sum(map(len, expected_orbits)) != case["eligible_sixth_blocks"]:
            raise ValueError(f"{case['id']}: sixth coverage mismatch")
        for recorded, orbit in zip(case["sixth_orbits"], expected_orbits):
            ordered = sorted(orbit)
            if recorded != {
                "index": recorded["index"],
                "canonical_block": list(ordered[0]),
                "canonical_variable": positions[ordered[0]],
                "member_variables": [positions[block] for block in ordered],
                "size": len(orbit),
            } or recorded["index"] != expected_orbits.index(orbit):
                raise ValueError(f"{case['id']}: sixth orbit mismatch")
        total += len(expected_orbits)
        summaries.append({"id": case["id"], "branches": len(expected_orbits), "available_blocks": len(available), "stabilizer_order": order})
    if len(seen) != manifest["case_count"] or total != manifest["total_sixth_children"]:
        raise ValueError("global sixth partition count mismatch")
    if seen != expected_timeout_ids:
        raise ValueError("timeout snapshot selection is incomplete or contains a foreign case")
    final_by_id = {case["id"]: case for case in manifest["cases"]}
    changed_predecessor_recipes = [
        case_id for case_id in sorted(predecessor_ids)
        if final_by_id.get(case_id) != predecessor_by_id[case_id]
    ]
    if changed_predecessor_recipes:
        raise ValueError("predecessor sixth recipes changed")
    added_ids = sorted(seen - predecessor_ids)
    decomposition = manifest["final_timeout_decomposition"]
    if not predecessor_ids <= seen:
        raise ValueError("predecessor timeout set is not retained")
    if (
        len(predecessor_ids) != decomposition["predecessor_cases"]
        or len(added_ids) != decomposition["added_cases"]
        or len(seen) != decomposition["final_cases"]
        or added_ids != decomposition["added_case_ids"]
        or unit_sha(added_ids) != decomposition["added_case_ids_sha256"]
    ):
        raise ValueError("34-leaf addition audit failed")
    return {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": sha(TARGET),
        "case_count": len(seen),
        "total_sixth_children": total,
        "duplicate_cases": 0,
        "omitted_timeout_cases": 0,
        "predecessor_cases_retained": len(predecessor_ids),
        "new_timeout_cases_audited": len(added_ids),
        "added_case_ids_sha256": unit_sha(added_ids),
        "predecessor_recipes_byte_equivalent": True,
        "changed_predecessor_recipes": [],
        "coverage": "For each bound timeout leaf, an independent five-cell membership-count grouping covers each available sixth block exactly once. The first-present rule makes the children exhaustive and disjoint.",
        "claim_limit": "Partition audit only; it neither solves a child nor certifies a fifth-level leaf.",
        "cases": summaries,
    }


if __name__ == "__main__":
    report = audit()
    output = TARGET.parent / "independent-audit.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "manifest_sha256", "case_count", "total_sixth_children")}, indent=2, sort_keys=True))
