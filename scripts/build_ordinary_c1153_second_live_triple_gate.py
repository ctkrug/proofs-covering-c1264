#!/usr/bin/env python3
"""Build the bounded second-live-triple structural gate.

This script profiles every still-open first-deficit child, then constructs a
second uncovered-triple partition only for the predeclared hard union:
first-deficit rank zero OR parent split-size quantile q3/q4.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
TRIPLES = tuple(itertools.combinations(POINTS, 3))
POSITIONS = {block: index for index, block in enumerate(BLOCKS, 1)}
BLOCK_SETS = tuple(frozenset(block) for block in BLOCKS)
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"
MANIFEST = BASE / "manifest.json"
AUDIT = BASE / "independent-audit.json"
SUMMARY = BASE / "discriminator-v2/summary.json"
RESULT_AUDIT = BASE / "discriminator-v2/independent-audit.json"
TARGET = BASE / "second-live-triple-gate-v1"
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe_sha(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + "\n").encode()).hexdigest()


def clause_sha(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + (" " if values else "") + "0\n").encode()).hexdigest()


def parent_primary_units(raw: bytes) -> tuple[set[int], set[int]]:
    positive: set[int] = set()
    negative: set[int] = set()
    with io.StringIO(raw.decode("ascii")) as source:
        for line in source:
            if not line or line[0] in "cp%0":
                continue
            words = line.split()
            if len(words) != 2 or words[1] != "0":
                continue
            value = int(words[0])
            if 0 < value <= len(BLOCKS):
                positive.add(value)
            elif -len(BLOCKS) <= value < 0:
                negative.add(-value)
    if positive & negative:
        raise ValueError("parent CNF has conflicting primary units")
    return positive, negative


def cells(
    fixed: tuple[tuple[int, ...], ...],
    distinguished: tuple[tuple[int, ...], ...] = (),
) -> tuple[tuple[int, ...], ...]:
    buckets: dict[tuple[bool, ...], list[int]] = {}
    fixed_sets = tuple(frozenset(block) for block in fixed)
    distinguished_sets = tuple(frozenset(value) for value in distinguished)
    for point in POINTS:
        key = tuple(point in value for value in (*fixed_sets, *distinguished_sets))
        buckets.setdefault(key, []).append(point)
    return tuple(tuple(buckets[key]) for key in sorted(buckets))


def orbit_rows(variables: set[int], partition: tuple[tuple[int, ...], ...]) -> list[dict[str, object]]:
    groups: dict[tuple[int, ...], list[int]] = {}
    cell_sets = tuple(frozenset(cell) for cell in partition)
    for variable in variables:
        block = BLOCK_SETS[variable - 1]
        key = tuple(len(block & cell) for cell in cell_sets)
        groups.setdefault(key, []).append(variable)
    return [
        {
            "index": index,
            "canonical_variable": group[0],
            "member_variables": group,
            "size": len(group),
        }
        for index, group in enumerate(sorted((sorted(group) for group in groups.values()), key=lambda row: row[0]))
    ]


def child_units(case: dict[str, object], index: int) -> list[int]:
    return [
        *[-value for orbit in case["covering_block_orbits"][:index] for value in orbit["member_variables"]],
        case["covering_block_orbits"][index]["canonical_variable"],
    ]


def assign_strata(cases: list[dict[str, object]]) -> None:
    for root in sorted({case["top_parent"] for case in cases}):
        rows = [case for case in cases if case["top_parent"] == root and case["branch_count"] > 0]
        branch_values = sorted(case["branch_count"] for case in rows)
        stabilizer_values = sorted(
            math.prod(math.factorial(size) for size in case["triple_stabilizer_cell_sizes"])
            for case in rows
        )
        for case in rows:
            branch_rank = sum(value < case["branch_count"] for value in branch_values)
            stabilizer = math.prod(math.factorial(size) for size in case["triple_stabilizer_cell_sizes"])
            stabilizer_rank = sum(value < stabilizer for value in stabilizer_values)
            case["_branch_quantile"] = ("q1", "q2", "q3", "q4")[
                min(3, 4 * branch_rank // len(branch_values))
            ]
            case["_stabilizer_order"] = stabilizer
            case["_stabilizer_tier"] = ("low", "mid", "high")[
                min(2, 3 * stabilizer_rank // len(stabilizer_values))
            ]


def residual(
    case: dict[str, object],
    deficit_index: int,
    parent_cache: dict[str, tuple[set[int], set[int]]],
    reconstructed_parents: dict[str, bytes],
) -> tuple[tuple[tuple[int, ...], ...], list[int], set[int], set[int], set[int]]:
    first_orbit = case["covering_block_orbits"][deficit_index]
    fixed = (*tuple(tuple(block) for block in case["fixed_blocks"]), BLOCKS[first_orbit["canonical_variable"] - 1])
    units = [*case["inherited_units"], *child_units(case, deficit_index)]
    path = ROOT / case["third_level_parent_cnf"]["path"]
    key = str(path)
    if key not in parent_cache:
        raw = path.read_bytes() if path.exists() else reconstructed_parents[path.parent.name]
        if hashlib.sha256(raw).hexdigest() != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError(f"{case['id']}: parent CNF hash mismatch")
        parent_cache[key] = parent_primary_units(raw)
    parent_positive, parent_negative = parent_cache[key]
    inherited_positive = {value for value in units if value > 0}
    inherited_negative = {-value for value in units if value < 0}
    fixed_variables = {POSITIONS[block] for block in fixed}
    if parent_negative & inherited_positive or inherited_negative & (parent_positive | inherited_positive):
        raise ValueError(f"{case['id']}: contradictory residual units")
    if not (parent_positive | inherited_positive) <= fixed_variables:
        raise ValueError(f"{case['id']}: positive residual unit is not a fixed block")
    forbidden = parent_negative | inherited_negative
    available = set(range(1, len(BLOCKS) + 1)) - forbidden - fixed_variables
    return fixed, units, available, parent_negative, inherited_negative


def aggregate(rows: list[dict[str, object]], keys: tuple[str, ...]) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], dict[str, object]] = {}
    for row in rows:
        key = tuple(row[name] for name in keys)
        target = groups.setdefault(key, {name: value for name, value in zip(keys, key)})
        target["remaining_children"] = target.get("remaining_children", 0) + 1
        target["generic_seventh_children"] = target.get("generic_seventh_children", 0) + row["generic_seventh_children"]
        target["targeted_children"] = target.get("targeted_children", 0) + int(row["targeted"])
    return [groups[key] for key in sorted(groups)]


def build() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    audit = json.loads(AUDIT.read_text())
    summary = json.loads(SUMMARY.read_text())
    result_audit = json.loads(RESULT_AUDIT.read_text())
    if audit["status"] != "VALID" or audit["manifest_sha256"] != sha(MANIFEST):
        raise ValueError("first-deficit manifest audit gate failed")
    if result_audit["status"] != "VALID" or result_audit["summary_sha256"] != sha(SUMMARY):
        raise ValueError("discriminator result audit gate failed")
    cases = [case for case in manifest["cases"] if case["branch_count"] > 0]
    assign_strata(cases)
    _, reconstructed_parents, _, reconstruction_receipt = reconstruct_hierarchy()
    certified = {
        row["leaf_id"]
        for row in summary["outcomes"]
        if row["status"] == "UNSAT_VERIFIED_BY_RUNNER"
    }
    if len(certified) != 10:
        raise ValueError("expected exactly ten replay-certified discriminator children")

    parent_cache: dict[str, tuple[set[int], set[int]]] = {}
    profile: list[dict[str, object]] = []
    target_rows: list[tuple[dict[str, object], int, dict[str, object], tuple[tuple[int, ...], ...], list[int], set[int], set[int], set[int]]] = []
    for case in sorted(cases, key=lambda row: row["id"]):
        for deficit_index in range(case["branch_count"]):
            leaf_id = f"{case['id']}-deficit-{deficit_index:03d}"
            if leaf_id in certified:
                continue
            fixed, units, available, parent_negative, inherited_negative = residual(
                case, deficit_index, parent_cache, reconstructed_parents
            )
            first_triple = tuple(case["chosen_uncovered_triple"])
            prefix_cells = cells(fixed, (first_triple,))
            generic = orbit_rows(available, prefix_cells)
            targeted = deficit_index == 0 or case["_branch_quantile"] in {"q3", "q4"}
            row = {
                "id": leaf_id,
                "fifth_case_id": case["id"],
                "first_eligible_orbit_rank": deficit_index,
                "rank_band": "rank_zero" if deficit_index == 0 else "rank_one" if deficit_index == 1 else "later_rank",
                "branch_count_quantile": case["_branch_quantile"],
                "root_class": case["top_parent"],
                "stabilizer_tier": case["_stabilizer_tier"],
                "prefix_triple_stabilizer_order": case["_stabilizer_order"],
                "generic_seventh_children": len(generic),
                "targeted": targeted,
            }
            profile.append(row)
            if targeted:
                target_rows.append((case, deficit_index, row, fixed, units, available, parent_negative, inherited_negative))
    if len(profile) != 19640:
        raise ValueError(f"remaining first-deficit child count mismatch: {len(profile)}")

    target_cases = []
    zero_count = second_total = generic_target_total = 0
    for case, deficit_index, profile_row, fixed, units, available, parent_negative, inherited_negative in target_rows:
        first_triple = tuple(case["chosen_uncovered_triple"])
        already_covered = {
            triple for triple in TRIPLES
            if any(frozenset(triple) <= frozenset(block) for block in fixed)
        }
        candidates = []
        for triple in TRIPLES:
            if triple in already_covered:
                continue
            all_coverers = {
                POSITIONS[tuple(sorted((*triple, *pair)))]
                for pair in itertools.combinations(sorted(set(POINTS) - set(triple)), 2)
            }
            eligible = all_coverers & available
            groups = orbit_rows(eligible, cells(fixed, (first_triple, triple)))
            candidates.append((len(groups), len(eligible), triple, groups, sorted(all_coverers)))
        branch_count, eligible_count, triple, groups, all_coverers = min(candidates, key=lambda row: row[:3])
        contradiction = None
        if eligible_count == 0:
            contradiction = {
                "selected_triple": list(triple),
                "coverage_clause_variables": all_coverers,
                "coverage_clause_sha256": clause_sha(all_coverers),
                "forbidden_coverers": [
                    {
                        "variable": value,
                        "reasons": [
                            *(["PARENT_CNF_NEGATIVE_UNIT"] if value in parent_negative else []),
                            *(["INHERITED_NEGATIVE_UNIT"] if value in inherited_negative else []),
                        ],
                    }
                    for value in all_coverers
                ],
                "residual_eligible_variables": [],
                "empty_residual_clause_sha256": clause_sha([]),
                "semantic_status": "EMPTY_RESIDUAL_COVERAGE_CLAUSE",
            }
        target_cases.append({
            **profile_row,
            "fixed_blocks": [list(block) for block in fixed],
            "first_selected_triple": list(first_triple),
            "third_level_parent_cnf": case["third_level_parent_cnf"],
            "inherited_units": units,
            "inherited_unit_sha256": recipe_sha(units),
            "available_primary_block_count": len(available),
            "available_primary_variables_sha256": recipe_sha(sorted(available)),
            "selected_second_uncovered_triple": list(triple),
            "eligible_second_covering_blocks": eligible_count,
            "second_partition_children": branch_count,
            "second_covering_block_orbits": groups,
            "semantic_contradiction_receipt": contradiction,
            "residual_cell_sizes": [len(cell) for cell in cells(fixed, (first_triple,))],
            "second_triple_cell_sizes": [len(cell) for cell in cells(fixed, (first_triple, triple))],
        })
        zero_count += branch_count == 0
        second_total += branch_count
        generic_target_total += profile_row["generic_seventh_children"]

    compression = 1 - second_total / generic_target_total
    profile_keys = ("root_class", "rank_band", "branch_count_quantile", "stabilizer_tier")
    manifest_out = {
        "schema_version": 1,
        "status": "BUILT_NOT_SOLVED",
        "bindings": {
            "first_deficit_manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": sha(MANIFEST)},
            "first_deficit_audit": {"path": str(AUDIT.relative_to(ROOT)), "sha256": sha(AUDIT)},
            "discriminator_summary": {"path": str(SUMMARY.relative_to(ROOT)), "sha256": sha(SUMMARY)},
            "discriminator_audit": {"path": str(RESULT_AUDIT.relative_to(ROOT)), "sha256": sha(RESULT_AUDIT)},
        },
        "parent_cnf_reconstruction": reconstruction_receipt["third_level"],
        "remaining_child_count": len(profile),
        "certified_discriminator_children_excluded": len(certified),
        "target_rule": "first_eligible_orbit_rank == 0 OR branch_count_quantile in {q3,q4}",
        "target_justification": "This exact union contains every first-occupied rank-zero residual plus every residual whose audited first-deficit parent lies in the two largest split-size quantiles; it covers the measured 2/24 rank-zero and 0/12 q3/q4 failure strata without labelling unsampled cases solver-hard.",
        "target_child_count": len(target_cases),
        "generic_seventh_children_target": generic_target_total,
        "second_partition_children": second_total,
        "zero_child_count": zero_count,
        "compression_fraction": compression,
        "scale_gate_passed": compression >= 0.75 or (zero_count / len(target_cases) >= 0.10),
        "profile_dimensions": list(profile_keys),
        "profile_by_stratum": aggregate(profile, profile_keys),
        "all_remaining_profile": profile,
        "target_cases": target_cases,
        "partition_rule": "Fix the exact first-deficit child. Choose the lexicographically deterministic minimum (orbit-count, eligible-count, triple) among still-uncovered triples. Under the within-cell subgroup fixing all six ordered blocks and both selected triples setwise, branch on the first occupied eligible second-triple orbit.",
        "soundness_limit": "The declared within-cell subgroup may be smaller than the full residual automorphism group. This can reduce compression but remains exhaustive. Signatures index exact subgroup orbits only after explicit relabeling and domain-invariance audit; they never authorize proof or CNF reuse.",
        "representation": "Hash-bound third-level parent CNF plus inherited fourth/fifth/first-deficit unit recipe and compact second-first-occupied units; no duplicate full CNFs materialized.",
        "claim_limit": "Structural gate only. No solver work, child closure, parent closure, ordinary classification, or C(12,6,4) theorem claim follows from this manifest.",
    }
    TARGET.mkdir(parents=True, exist_ok=False)
    (TARGET / "manifest.json").write_text(json.dumps(manifest_out, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({
        "remaining_child_count": len(profile),
        "target_child_count": len(target_cases),
        "generic_seventh_children_target": generic_target_total,
        "second_partition_children": second_total,
        "zero_child_count": zero_count,
        "compression_fraction": compression,
        "scale_gate_passed": manifest_out["scale_gate_passed"],
    }, sort_keys=True))
    return manifest_out


if __name__ == "__main__":
    build()
