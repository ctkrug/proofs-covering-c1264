#!/usr/bin/env python3
"""Freeze and partition the currently observed fifth-level timeout hard tail.

This does not solve any child.  For each exact fifth-level timeout, it makes a
complete first-present sixth-block partition under the stabilizer of the five
fixed blocks.  The output is a compact unit-recipe manifest.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
TARGET = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-sixth-discriminator"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit_sha(units: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, units)) + "\n").encode()).hexdigest()


def stabilizer(fixed: tuple[tuple[int, ...], ...]) -> list[dict[int, int]]:
    cells = []
    for signature in itertools.product((False, True), repeat=len(fixed)):
        cell = tuple(point for point in POINTS if tuple(point in block for block in fixed) == signature)
        if cell:
            cells.append(cell)
    actions = []
    for choices in itertools.product(*(tuple(itertools.permutations(cell)) for cell in cells)):
        action: dict[int, int] = {}
        for source, target in zip(cells, choices):
            action.update(zip(source, target))
        actions.append(action)
    if len(actions) != math.prod(math.factorial(len(cell)) for cell in cells):
        raise AssertionError("stabilizer enumeration mismatch")
    return actions


def inherited_absent(parent_cnf: Path) -> set[int]:
    result: set[int] = set()
    with parent_cnf.open() as handle:
        for line in handle:
            if not line or line[0] in "cp%0":
                continue
            words = line.split()
            if len(words) == 2 and words[1] == "0":
                value = int(words[0])
                if -462 <= value < 0:
                    result.add(-value)
    return result


def fifth_units(parent: dict[str, object], index: int) -> list[int]:
    orbits = parent["fifth_orbits"]
    return [
        *[-value for orbit in orbits[:index] for value in orbit["member_variables"]],
        orbits[index]["canonical_variable"],
    ]


def position(index: int, count: int) -> str:
    if index == 0:
        return "orbit_zero"
    if index == 1:
        return "orbit_one"
    ratio = index / (count - 1)
    if ratio < 0.25:
        return "early_prefix_after_one"
    if ratio < 0.50:
        return "first_quartile_or_later"
    if ratio < 0.75:
        return "midpoint_or_later"
    return "last_quartile"


def measured_rows() -> tuple[list[dict[str, object]], dict[str, object]]:
    discriminator_path = BASE / "discriminator-5s-summary.json"
    discriminator = json.loads(discriminator_path.read_text())
    rows = []
    for outcome in discriminator["outcomes"]:
        item = dict(outcome)
        item["source"] = {
            "kind": "discriminator",
            "path": str(discriminator_path.relative_to(ROOT)),
            "sha256": sha(discriminator_path),
        }
        rows.append(item)

    ledger_path = BASE / "suffix-scale-ledger.json"
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    listed_segments = [row["segment"] for row in ledger["segments"]]
    for segment in listed_segments:
        segment_dir = BASE / "segments" / f"segment-{segment:04d}"
        for result_path in sorted(segment_dir.glob("*/result.json")):
            item = json.loads(result_path.read_text())
            item["source"] = {
                "kind": "suffix_segment",
                "segment": segment,
                "path": str(result_path.relative_to(ROOT)),
                "sha256": sha(result_path),
            }
            rows.append(item)
    source = {
        "discriminator": {
            "path": str(discriminator_path.relative_to(ROOT)),
            "sha256": sha(discriminator_path),
        },
        "suffix_ledger_snapshot": {
            "path": str(ledger_path.relative_to(ROOT)),
            "sha256_at_freeze": hashlib.sha256(ledger_bytes).hexdigest(),
            "segments": listed_segments,
        },
    }
    return rows, source


def build() -> dict[str, object]:
    fifth_path = BASE / "manifest.json"
    fifth = json.loads(fifth_path.read_text())
    parent_by_id = {row["id"]: row for row in fifth["parents"]}
    rows, sources = measured_rows()
    timeouts = [row for row in rows if row["status"] == "FIXED_CAP_TIMEOUT"]
    if len({row["leaf_id"] for row in timeouts}) != len(timeouts):
        raise ValueError("duplicate timeout leaf in source snapshot")

    # Evidence for the rank/accumulated-negative-units hypothesis.
    evidence: dict[str, Counter[str]] = {}
    for row in rows:
        parent = parent_by_id[row["fourth_parent_id"]]
        label = position(row["fifth_index"], parent["branch_count"])
        evidence.setdefault(label, Counter())[row["status"]] += 1

    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    cases = []
    total_children = 0
    for timeout in sorted(timeouts, key=lambda row: row["leaf_id"]):
        parent = parent_by_id[timeout["fourth_parent_id"]]
        fifth_index = timeout["fifth_index"]
        fixed = tuple(tuple(block) for block in parent["fixed_blocks"])
        fifth_block = tuple(parent["fifth_orbits"][fifth_index]["canonical_block"])
        fixed_five = (*fixed, fifth_block)
        actions = stabilizer(fixed_five)
        parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
        if sha(parent_path) != parent["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{timeout['leaf_id']}: parent CNF hash mismatch")
        absent = inherited_absent(parent_path)
        absent.update(value for value in parent["inherited_fourth_units"] if value < 0 for value in [-value])
        inherited_fifth = fifth_units(parent, fifth_index)
        absent.update(-value for value in inherited_fifth if value < 0)
        unavailable = {BLOCKS[value - 1] for value in absent} | set(fixed_five)
        unseen = set(BLOCKS) - unavailable
        orbit_rows = []
        while unseen:
            seed = min(unseen)
            orbit = {tuple(sorted(action[point] for point in seed)) for action in actions}
            if not orbit <= unseen:
                raise ValueError(f"{timeout['leaf_id']}: sixth orbit overlaps unavailable domain")
            ordered = sorted(orbit)
            orbit_rows.append({
                "index": len(orbit_rows),
                "canonical_block": list(ordered[0]),
                "canonical_variable": positions[ordered[0]],
                "member_variables": [positions[block] for block in ordered],
                "size": len(orbit),
            })
            unseen -= orbit
        inherited_units = [*parent["inherited_fourth_units"], *inherited_fifth]
        cases.append({
            "id": timeout["leaf_id"],
            "source_result": timeout["source"],
            "top_parent": parent["top_parent"],
            "prior_fourth_status": parent["prior_status"],
            "fifth_index": fifth_index,
            "fifth_position": position(fifth_index, parent["branch_count"]),
            "fixed_blocks": [list(block) for block in fixed_five],
            "third_level_parent_cnf": parent["third_level_parent_cnf"],
            "inherited_units": inherited_units,
            "inherited_unit_sha256": unit_sha(inherited_units),
            "stabilizer_order": len(actions),
            "eligible_sixth_blocks": sum(orbit["size"] for orbit in orbit_rows),
            "branch_count": len(orbit_rows),
            "sixth_orbits": orbit_rows,
        })
        total_children += len(orbit_rows)

    manifest = {
        "schema_version": 1,
        "status": "BUILT_NOT_SOLVED_SNAPSHOT",
        "fifth_manifest": {"path": str(fifth_path.relative_to(ROOT)), "sha256": sha(fifth_path)},
        "source_snapshot": sources,
        "observed_outcome_counts": dict(Counter(row["status"] for row in rows)),
        "outcomes_by_fifth_position": {key: dict(value) for key, value in sorted(evidence.items())},
        "hypothesis": {
            "statement": "The fifth-level hard tail is mainly caused by insufficient accumulated first-present negative units: orbit-zero/orbit-one and the first suffix boundary retain broad residual choices, while later ranks collapse under propagation.",
            "decisive_prediction": "After complete sixth-block splitting, at least 75% of children in the latter half of each selected sixth partition should solve at the unchanged five-second proof cap, and timeouts should remain concentrated in the first quarter. Failure of either condition rejects this explanation.",
            "alternative": "Hardness is intrinsic to particular fixed-block incidence types and will persist across sixth-orbit rank rather than move to the earliest sixth prefix.",
        },
        "selection": "Every distinct FIXED_CAP_TIMEOUT in the immutable 96-case discriminator plus every completed suffix segment listed by the frozen suffix-ledger hash. No SAT/UNSAT leaf is included.",
        "case_count": len(cases),
        "total_sixth_children": total_children,
        "partition_rule": "Under the setwise stabilizer of all five fixed blocks, select the first present sixth-block orbit, force every earlier orbit absent, and map the selected block to the orbit's canonical representative.",
        "representation": "Reconstruct a sixth child from the bound third-level CNF, the recorded inherited fourth/fifth units, negative units for every member of earlier sixth orbits, and the current orbit canonical positive unit.",
        "exhaustiveness_reason": "Every ordinary cover has 20 distinct blocks. After five fixed blocks it has at least one additional available block. The five-block stabilizer partitions all available blocks, so the least occupied orbit is unique and yields exactly one child.",
        "claim_limit": "This is an audited candidate partition for the observed timeout snapshot, not a solver result, branch closure, or final residual manifest.",
        "cases": cases,
    }
    TARGET.mkdir(parents=True, exist_ok=False)
    output = TARGET / "manifest.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    report = build()
    print(json.dumps({key: report[key] for key in ("status", "case_count", "total_sixth_children", "observed_outcome_counts")}, indent=2, sort_keys=True))
