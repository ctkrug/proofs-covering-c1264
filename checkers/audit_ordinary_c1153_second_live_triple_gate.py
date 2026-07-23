#!/usr/bin/env python3
"""Independent audit of the second-live-triple structural gate."""

from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path


POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
TRIPLES = tuple(itertools.combinations(POINTS, 3))
POSITIONS = {block: index for index, block in enumerate(BLOCKS, 1)}
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checkers"))
from audit_ordinary_c1153_fourth_inventory import reconstruct_hierarchy  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe_digest(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + "\n").encode()).hexdigest()


def clause_digest(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + (" " if values else "") + "0\n").encode()).hexdigest()


def read_units(raw: bytes) -> tuple[set[int], set[int]]:
    positive: set[int] = set()
    negative: set[int] = set()
    with io.StringIO(raw.decode("ascii")) as source:
        for line in source:
            if not line or line[0] in "cp%0":
                continue
            words = line.split()
            if len(words) == 2 and words[1] == "0":
                value = int(words[0])
                if 0 < value <= len(BLOCKS):
                    positive.add(value)
                elif -len(BLOCKS) <= value < 0:
                    negative.add(-value)
    if positive & negative:
        raise ValueError("parent CNF contains conflicting primary units")
    return positive, negative


def membership_cells(
    fixed: tuple[frozenset[int], ...],
    distinguished: tuple[frozenset[int], ...],
) -> tuple[frozenset[int], ...]:
    buckets: dict[tuple[bool, ...], set[int]] = {}
    for point in POINTS:
        key = tuple(point in value for value in (*fixed, *distinguished))
        buckets.setdefault(key, set()).add(point)
    return tuple(frozenset(buckets[key]) for key in sorted(buckets))


def orbit_variables(variables: set[int], cells: tuple[frozenset[int], ...]) -> list[list[int]]:
    groups: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for variable in variables:
        block = frozenset(BLOCKS[variable - 1])
        groups[tuple(len(block & cell) for cell in cells)].append(variable)
    return sorted((sorted(group) for group in groups.values()), key=lambda group: group[0])


def explicit_map(source: int, target: int, cells: tuple[frozenset[int], ...]) -> dict[int, int]:
    source_block = set(BLOCKS[source - 1])
    target_block = set(BLOCKS[target - 1])
    mapping: dict[int, int] = {}
    for cell in cells:
        source_in = sorted(source_block & cell)
        target_in = sorted(target_block & cell)
        source_out = sorted(set(cell) - source_block)
        target_out = sorted(set(cell) - target_block)
        if len(source_in) != len(target_in):
            raise ValueError("signature collision is not an orbit")
        mapping.update(zip(source_in, target_in))
        mapping.update(zip(source_out, target_out))
    if set(mapping) != set(POINTS) or set(mapping.values()) != set(POINTS):
        raise ValueError("explicit cell map is not a permutation")
    return mapping


def verify_orbits(
    variables: set[int],
    cells: tuple[frozenset[int], ...],
    fixed: tuple[frozenset[int], ...],
    distinguished: tuple[frozenset[int], ...],
) -> list[list[int]]:
    groups = orbit_variables(variables, cells)
    for group in groups:
        source = group[0]
        for target in group:
            mapping = explicit_map(source, target, cells)
            image = tuple(sorted(mapping[point] for point in BLOCKS[source - 1]))
            if image != BLOCKS[target - 1]:
                raise ValueError("explicit orbit witness misses target")
            if any(frozenset(mapping[point] for point in value) != value for value in (*fixed, *distinguished)):
                raise ValueError("explicit orbit witness does not preserve residual domain")
    return groups


def child_recipe(case: dict[str, object], index: int) -> list[int]:
    return [
        *[-value for orbit in case["covering_block_orbits"][:index] for value in orbit["member_variables"]],
        case["covering_block_orbits"][index]["canonical_variable"],
    ]


def independent_strata(cases: list[dict[str, object]]) -> dict[str, tuple[str, str, int]]:
    result: dict[str, tuple[str, str, int]] = {}
    for root in sorted({case["top_parent"] for case in cases}):
        rows = [case for case in cases if case["top_parent"] == root and case["branch_count"] > 0]
        branches = sorted(case["branch_count"] for case in rows)
        stabilizers = sorted(
            math.prod(math.factorial(size) for size in case["triple_stabilizer_cell_sizes"])
            for case in rows
        )
        for case in rows:
            branch_rank = sum(value < case["branch_count"] for value in branches)
            stabilizer = math.prod(math.factorial(size) for size in case["triple_stabilizer_cell_sizes"])
            stabilizer_rank = sum(value < stabilizer for value in stabilizers)
            quantile = ("q1", "q2", "q3", "q4")[min(3, 4 * branch_rank // len(branches))]
            tier = ("low", "mid", "high")[min(2, 3 * stabilizer_rank // len(stabilizers))]
            result[case["id"]] = (quantile, tier, stabilizer)
    return result


def reconstruct_residual(
    root: Path,
    case: dict[str, object],
    index: int,
    cache: dict[str, tuple[set[int], set[int]]],
    reconstructed_parents: dict[str, bytes],
) -> tuple[tuple[frozenset[int], ...], list[int], set[int], set[int], set[int]]:
    orbit = case["covering_block_orbits"][index]
    fixed_tuples = (*tuple(tuple(block) for block in case["fixed_blocks"]), BLOCKS[orbit["canonical_variable"] - 1])
    fixed = tuple(frozenset(block) for block in fixed_tuples)
    units = [*case["inherited_units"], *child_recipe(case, index)]
    path = root / case["third_level_parent_cnf"]["path"]
    key = str(path)
    if key not in cache:
        raw = path.read_bytes() if path.exists() else reconstructed_parents[path.parent.name]
        if hashlib.sha256(raw).hexdigest() != case["third_level_parent_cnf"]["sha256"]:
            raise ValueError("parent CNF hash mismatch")
        cache[key] = read_units(raw)
    parent_positive, parent_negative = cache[key]
    inherited_positive = {value for value in units if value > 0}
    inherited_negative = {-value for value in units if value < 0}
    fixed_variables = {POSITIONS[tuple(sorted(block))] for block in fixed}
    if parent_negative & inherited_positive or inherited_negative & (parent_positive | inherited_positive):
        raise ValueError("conflicting exact residual units")
    if not (parent_positive | inherited_positive) <= fixed_variables:
        raise ValueError("positive primary unit is outside the six fixed blocks")
    forbidden = parent_negative | inherited_negative
    available = set(range(1, len(BLOCKS) + 1)) - forbidden - fixed_variables
    return fixed, units, available, parent_negative, inherited_negative


def audit(root: Path, manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text())
    if manifest["schema_version"] != 1:
        raise ValueError("unknown gate schema")
    for binding in manifest["bindings"].values():
        path = root / binding["path"]
        if digest(path) != binding["sha256"]:
            raise ValueError(f"binding mismatch: {binding['path']}")
    base = json.loads((root / manifest["bindings"]["first_deficit_manifest"]["path"]).read_text())
    base_audit = json.loads((root / manifest["bindings"]["first_deficit_audit"]["path"]).read_text())
    summary = json.loads((root / manifest["bindings"]["discriminator_summary"]["path"]).read_text())
    result_audit = json.loads((root / manifest["bindings"]["discriminator_audit"]["path"]).read_text())
    if base_audit["status"] != "VALID" or result_audit["status"] != "VALID":
        raise ValueError("source audit is not valid")
    certified = {
        row["leaf_id"] for row in summary["outcomes"]
        if row["status"] == "UNSAT_VERIFIED_BY_RUNNER"
    }
    if len(certified) != 10:
        raise ValueError("certified exclusion set changed")
    cases = [case for case in base["cases"] if case["branch_count"] > 0]
    _, reconstructed_parents, _, reconstruction_receipt = reconstruct_hierarchy()
    if manifest["parent_cnf_reconstruction"] != reconstruction_receipt["third_level"]:
        raise ValueError("parent-CNF reconstruction receipt mismatch")
    case_by_id = {case["id"]: case for case in cases}
    strata = independent_strata(cases)
    recorded_profile = {row["id"]: row for row in manifest["all_remaining_profile"]}
    recorded_targets = {row["id"]: row for row in manifest["target_cases"]}
    if len(recorded_profile) != len(manifest["all_remaining_profile"]):
        raise ValueError("duplicate profile child")
    if len(recorded_targets) != len(manifest["target_cases"]):
        raise ValueError("duplicate target child")

    expected_ids: set[str] = set()
    expected_target_ids: set[str] = set()
    parent_cache: dict[str, tuple[set[int], set[int]]] = {}
    generic_target_total = second_total = zero_count = 0
    stratum_totals: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for case in sorted(cases, key=lambda row: row["id"]):
        quantile, tier, stabilizer = strata[case["id"]]
        for index in range(case["branch_count"]):
            leaf_id = f"{case['id']}-deficit-{index:03d}"
            if leaf_id in certified:
                continue
            expected_ids.add(leaf_id)
            fixed, units, available, parent_negative, inherited_negative = reconstruct_residual(
                root, case, index, parent_cache, reconstructed_parents
            )
            first_triple = frozenset(case["chosen_uncovered_triple"])
            prefix_cells = membership_cells(fixed, (first_triple,))
            # Every exact primary availability orbit must be all-in or all-out.
            for full_group in orbit_variables(set(range(1, len(BLOCKS) + 1)), prefix_cells):
                intersection = set(full_group) & available
                if intersection and intersection != set(full_group):
                    raise ValueError(f"{leaf_id}: residual domain is not subgroup invariant")
            generic_groups = orbit_variables(available, prefix_cells)
            target = index == 0 or quantile in {"q3", "q4"}
            rank_band = "rank_zero" if index == 0 else "rank_one" if index == 1 else "later_rank"
            profile = recorded_profile.get(leaf_id)
            expected_profile = {
                "id": leaf_id,
                "fifth_case_id": case["id"],
                "first_eligible_orbit_rank": index,
                "rank_band": rank_band,
                "branch_count_quantile": quantile,
                "root_class": case["top_parent"],
                "stabilizer_tier": tier,
                "prefix_triple_stabilizer_order": stabilizer,
                "generic_seventh_children": len(generic_groups),
                "targeted": target,
            }
            if profile != expected_profile:
                raise ValueError(f"{leaf_id}: complete profile mismatch")
            stratum_key = (case["top_parent"], rank_band, quantile, tier)
            stratum_totals[stratum_key]["remaining_children"] += 1
            stratum_totals[stratum_key]["generic_seventh_children"] += len(generic_groups)
            stratum_totals[stratum_key]["targeted_children"] += int(target)
            if not target:
                continue
            expected_target_ids.add(leaf_id)
            row = recorded_targets.get(leaf_id)
            if row is None:
                raise ValueError(f"{leaf_id}: target omitted")
            if row["fixed_blocks"] != [sorted(block) for block in fixed]:
                raise ValueError(f"{leaf_id}: fixed prefix mismatch")
            if row["first_selected_triple"] != sorted(first_triple):
                raise ValueError(f"{leaf_id}: first selected triple mismatch")
            if row["inherited_units"] != units or row["inherited_unit_sha256"] != recipe_digest(units):
                raise ValueError(f"{leaf_id}: exact unit recipe mismatch")
            if (
                row["available_primary_block_count"] != len(available)
                or row["available_primary_variables_sha256"] != recipe_digest(sorted(available))
            ):
                raise ValueError(f"{leaf_id}: available-domain binding mismatch")
            candidates = []
            for triple_tuple in TRIPLES:
                triple = frozenset(triple_tuple)
                if any(triple <= block for block in fixed):
                    continue
                coverers = {
                    POSITIONS[tuple(sorted((*triple, *pair)))]
                    for pair in itertools.combinations(sorted(set(POINTS) - triple), 2)
                }
                eligible = coverers & available
                second_cells = membership_cells(fixed, (first_triple, triple))
                groups = orbit_variables(eligible, second_cells)
                candidates.append((len(groups), len(eligible), triple_tuple, groups, sorted(coverers), second_cells))
            count, eligible_count, triple_tuple, groups, all_coverers, second_cells = min(candidates, key=lambda item: item[:3])
            triple = frozenset(triple_tuple)
            # Independent explicit witnesses certify exact subgroup orbits.
            witnessed = verify_orbits(eligible := (set(all_coverers) & available), second_cells, fixed, (first_triple, triple))
            if witnessed != groups:
                raise ValueError(f"{leaf_id}: signature groups are not exact witnessed orbits")
            for full_group in orbit_variables(set(range(1, len(BLOCKS) + 1)), second_cells):
                intersection = set(full_group) & available
                if intersection and intersection != set(full_group):
                    raise ValueError(f"{leaf_id}: second-triple action changes exact residual domain")
            flattened = [value for group in groups for value in group]
            if len(flattened) != len(set(flattened)) or set(flattened) != eligible:
                raise ValueError(f"{leaf_id}: second partition is not exhaustive/disjoint")
            recorded_groups = [group["member_variables"] for group in row["second_covering_block_orbits"]]
            if (
                row["selected_second_uncovered_triple"] != list(triple_tuple)
                or row["eligible_second_covering_blocks"] != eligible_count
                or row["second_partition_children"] != count
                or recorded_groups != groups
                or row["residual_cell_sizes"] != [len(cell) for cell in prefix_cells]
                or row["second_triple_cell_sizes"] != [len(cell) for cell in second_cells]
            ):
                raise ValueError(f"{leaf_id}: deterministic second partition mismatch")
            receipt = row["semantic_contradiction_receipt"]
            if count == 0:
                forbidden = [
                    {
                        "variable": value,
                        "reasons": [
                            *(["PARENT_CNF_NEGATIVE_UNIT"] if value in parent_negative else []),
                            *(["INHERITED_NEGATIVE_UNIT"] if value in inherited_negative else []),
                        ],
                    }
                    for value in all_coverers
                ]
                if receipt != {
                    "selected_triple": list(triple_tuple),
                    "coverage_clause_variables": all_coverers,
                    "coverage_clause_sha256": clause_digest(all_coverers),
                    "forbidden_coverers": forbidden,
                    "residual_eligible_variables": [],
                    "empty_residual_clause_sha256": clause_digest([]),
                    "semantic_status": "EMPTY_RESIDUAL_COVERAGE_CLAUSE",
                }:
                    raise ValueError(f"{leaf_id}: zero-child contradiction receipt mismatch")
            elif receipt is not None:
                raise ValueError(f"{leaf_id}: unexpected contradiction receipt")
            generic_target_total += len(generic_groups)
            second_total += count
            zero_count += count == 0

    if set(recorded_profile) != expected_ids or len(expected_ids) != 19640:
        raise ValueError("complete remaining-child membership mismatch")
    if set(recorded_targets) != expected_target_ids:
        raise ValueError("exact target-union membership mismatch")
    expected_profile_by_stratum = []
    for key in sorted(stratum_totals):
        values = stratum_totals[key]
        expected_profile_by_stratum.append({
            "root_class": key[0],
            "rank_band": key[1],
            "branch_count_quantile": key[2],
            "stabilizer_tier": key[3],
            "remaining_children": values["remaining_children"],
            "generic_seventh_children": values["generic_seventh_children"],
            "targeted_children": values["targeted_children"],
        })
    if manifest["profile_by_stratum"] != expected_profile_by_stratum:
        raise ValueError("profile stratum aggregation mismatch")
    compression = 1 - second_total / generic_target_total
    if (
        manifest["target_child_count"] != len(expected_target_ids)
        or manifest["generic_seventh_children_target"] != generic_target_total
        or manifest["second_partition_children"] != second_total
        or manifest["zero_child_count"] != zero_count
        or abs(manifest["compression_fraction"] - compression) > 1e-15
        or manifest["scale_gate_passed"] != (compression >= 0.75 or zero_count / len(expected_target_ids) >= 0.10)
    ):
        raise ValueError("aggregate gate metric mismatch")
    return {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": digest(manifest_path),
        "remaining_child_count": len(expected_ids),
        "target_child_count": len(expected_target_ids),
        "generic_seventh_children_target": generic_target_total,
        "second_partition_children": second_total,
        "zero_child_count": zero_count,
        "compression_fraction": compression,
        "scale_gate_passed": manifest["scale_gate_passed"],
        "checked_properties": [
            "all 19,640 remaining first-deficit children profiled exactly once",
            "ten replay-certified discriminator children excluded",
            "target union equals rank-zero OR q3/q4 exactly",
            "exact parent-CNF and inherited-unit residual reconstruction",
            "every selected second triple remains uncovered",
            "every eligible covering block included exactly once",
            "explicit within-cell relabeling witnesses for every recorded orbit",
            "declared subgroup preserves the full exact residual block domain",
            "first-occupied branches exhaustive and SAT-model-disjoint",
            "zero-child empty coverage clauses with exact forbidden-unit reasons",
            "no signature-based CNF/proof reuse or unproved equivalence",
        ],
        "claim_limit": "Audited structural partition only; no solver or theorem closure is asserted.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = audit(root, args.manifest)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(payload)
    os.replace(temporary, args.output)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
