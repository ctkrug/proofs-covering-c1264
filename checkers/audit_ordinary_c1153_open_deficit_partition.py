#!/usr/bin/env python3
"""Independently audit the all-open fifth-level coverage-deficit partition."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from collections import Counter
from pathlib import Path


POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
TRIPLES = tuple(itertools.combinations(POINTS, 3))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe_digest(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + "\n").encode()).hexdigest()


def validate_available_binding(row: dict[str, object], available: set[int]) -> None:
    """Reject any recorded residual-domain binding that differs by one variable."""
    if (
        row["available_primary_block_count"] != len(available)
        or row["available_primary_variables_sha256"] != recipe_digest(sorted(available))
    ):
        raise ValueError(f"{row.get('id', '<case>')}: exact available-primary domain binding mismatch")


def clause_digest(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + (" " if values else "") + "0\n").encode()).hexdigest()


def parent_primary_units(path: Path) -> tuple[set[int], set[int]]:
    """Read positive and negative primary units directly from the bound DIMACS."""
    positive: set[int] = set()
    negative: set[int] = set()
    with path.open() as source:
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
        raise ValueError("cached parent CNF contains conflicting primary units")
    return positive, negative


def fifth_recipe(parent: dict[str, object], index: int) -> list[int]:
    return [
        *[-value for orbit in parent["fifth_orbits"][:index] for value in orbit["member_variables"]],
        parent["fifth_orbits"][index]["canonical_variable"],
    ]


def independent_measured(root: Path, base: Path, ledger: dict[str, object], discriminator: dict[str, object]) -> dict[str, str]:
    result = {row["leaf_id"]: row["status"] for row in discriminator["outcomes"]}
    for segment in ledger["segments"]:
        directory = base / "segments" / f"segment-{segment['segment']:04d}"
        receipt = json.loads((directory / "runner-receipt.json").read_text())
        rows = [json.loads(path.read_text()) for path in sorted(directory.glob("*/result.json"))]
        if len(rows) != receipt["selected"] or receipt["completed"] != receipt["selected"]:
            raise ValueError("incomplete source segment")
        for row in rows:
            if row["leaf_id"] in result:
                raise ValueError("overlapping measured sources")
            result[row["leaf_id"]] = row["status"]
    return result


def membership_cells(fixed: tuple[frozenset[int], ...], triple: frozenset[int] | None) -> tuple[frozenset[int], ...]:
    buckets: dict[tuple[object, ...], set[int]] = {}
    for point in POINTS:
        signature = tuple(point in block for block in fixed)
        key = (*signature, point in triple) if triple is not None else signature
        buckets.setdefault(key, set()).add(point)
    return tuple(frozenset(buckets[key]) for key in sorted(buckets))


def orbit_variables(variables: set[int], cells: tuple[frozenset[int], ...]) -> list[list[int]]:
    groups: dict[tuple[int, ...], list[int]] = {}
    for variable in variables:
        block = frozenset(BLOCKS[variable - 1])
        key = tuple(len(block & cell) for cell in cells)
        groups.setdefault(key, []).append(variable)
    return sorted((sorted(group) for group in groups.values()), key=lambda group: group[0])


def explicit_cell_map(
    source_variable: int,
    target_variable: int,
    cells: tuple[frozenset[int], ...],
) -> dict[int, int]:
    """Construct an explicit within-cell permutation taking source to target."""
    source = set(BLOCKS[source_variable - 1])
    target = set(BLOCKS[target_variable - 1])
    mapping: dict[int, int] = {}
    for cell in cells:
        source_in = sorted(source & cell)
        target_in = sorted(target & cell)
        source_out = sorted(set(cell) - source)
        target_out = sorted(set(cell) - target)
        if len(source_in) != len(target_in):
            raise ValueError("equal-signature mapping requested for unequal signatures")
        mapping.update(zip(source_in, target_in))
        mapping.update(zip(source_out, target_out))
    if set(mapping) != set(POINTS) or set(mapping.values()) != set(POINTS):
        raise ValueError("cell map is not a permutation")
    return mapping


def verify_exact_subgroup_orbits(
    variables: set[int],
    cells: tuple[frozenset[int], ...],
    fixed: tuple[frozenset[int], ...],
    triple: frozenset[int] | None,
) -> list[list[int]]:
    """Verify signatures are exactly orbits of the declared within-cell subgroup.

    The subgroup fixes each ordered prefix block setwise and, when supplied, the
    selected triple setwise.  This intentionally makes no quotient claim under
    any larger stabilizer that may permute equal-role prefix blocks.
    """
    expected = orbit_variables(variables, cells)
    for orbit in expected:
        canonical = orbit[0]
        for target in orbit:
            mapping = explicit_cell_map(canonical, target, cells)
            image = tuple(sorted(mapping[p] for p in BLOCKS[canonical - 1]))
            if image != BLOCKS[target - 1]:
                raise ValueError("explicit within-cell map misses orbit target")
            if any(frozenset(mapping[p] for p in block) != block for block in fixed):
                raise ValueError("cell map does not fix every prefix block setwise")
            if triple is not None and frozenset(mapping[p] for p in triple) != triple:
                raise ValueError("cell map does not fix the chosen triple setwise")
    return expected


def audit(root: Path, manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text())
    if manifest["schema_version"] != 2:
        raise ValueError("expected corrected exact-domain schema version 2")
    bindings = manifest["bindings"]
    for binding in bindings.values():
        path = root / binding["path"]
        if digest(path) != binding["sha256"]:
            raise ValueError(f"binding mismatch: {binding['path']}")
    fifth = json.loads((root / bindings["fifth_manifest"]["path"]).read_text())
    terminal = json.loads((root / bindings["terminal_aggregate"]["path"]).read_text())
    discriminator = json.loads((root / bindings["discriminator_summary"]["path"]).read_text())
    ledger = json.loads((root / bindings["suffix_ledger"]["path"]).read_text())
    base = root / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
    measured = independent_measured(root, base, ledger, discriminator)
    unsat = {"UNSAT_VERIFIED", "UNSAT_VERIFIED_BY_RUNNER", "PROVISIONAL_UNSAT_PROOF_RETAINED"}
    allowed_measured = unsat | {"FIXED_CAP_TIMEOUT"}
    foreign_statuses = sorted(set(measured.values()) - allowed_measured)
    if foreign_statuses:
        raise ValueError(f"unexpected measured status, including any SAT: {foreign_statuses}")
    expected: dict[str, str] = {}
    parents = {parent["id"]: parent for parent in fifth["parents"]}
    for parent in fifth["parents"]:
        for index in range(parent["branch_count"]):
            leaf_id = f"{parent['id']}-fifth-{index:03d}"
            if measured.get(leaf_id) in unsat:
                continue
            expected[leaf_id] = "FIXED_CAP_TIMEOUT" if measured.get(leaf_id) == "FIXED_CAP_TIMEOUT" else "NEVER_MEASURED"
    recorded = {row["id"]: row for row in manifest["cases"]}
    if len(recorded) != len(manifest["cases"]) or set(recorded) != set(expected):
        raise ValueError("all-open membership mismatch")
    if Counter(expected.values()) != {"FIXED_CAP_TIMEOUT": 82, "NEVER_MEASURED": 10626}:
        raise ValueError("open status decomposition mismatch")
    if terminal["counts"]["open_distinct"] != len(expected):
        raise ValueError("terminal open count mismatch")

    generic_total = deficit_total = zero_count = 0
    parent_unit_cache: dict[str, tuple[set[int], set[int]]] = {}
    positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    for leaf_id in sorted(expected):
        row = recorded[leaf_id]
        if row["open_status"] != expected[leaf_id]:
            raise ValueError(f"{leaf_id}: wrong open status")
        parent = parents[row["fourth_parent_id"]]
        index = row["fifth_index"]
        expected_fixed = [*parent["fixed_blocks"], parent["fifth_orbits"][index]["canonical_block"]]
        expected_units = [*parent["inherited_fourth_units"], *fifth_recipe(parent, index)]
        if row["fixed_blocks"] != expected_fixed or row["inherited_units"] != expected_units:
            raise ValueError(f"{leaf_id}: prefix recipe changed")
        if recipe_digest(expected_units) != row["inherited_unit_sha256"]:
            raise ValueError(f"{leaf_id}: unit digest mismatch")
        parent_path = root / row["third_level_parent_cnf"]["path"]
        if str(parent_path) not in parent_unit_cache:
            if digest(parent_path) != row["third_level_parent_cnf"]["sha256"]:
                raise ValueError(f"{leaf_id}: parent CNF mismatch")
            parent_unit_cache[str(parent_path)] = parent_primary_units(parent_path)

        fixed = tuple(frozenset(block) for block in expected_fixed)
        fixed_variables = {positions[tuple(block)] for block in expected_fixed}
        inherited_positive = {value for value in expected_units if value > 0}
        inherited_absent = {-value for value in expected_units if value < 0}
        parent_positive, parent_absent = parent_unit_cache[str(parent_path)]
        if parent_absent & inherited_positive:
            raise ValueError(f"{leaf_id}: parent-negative/inherited-positive conflict")
        if inherited_absent & (parent_positive | inherited_positive):
            raise ValueError(f"{leaf_id}: inherited-negative/positive conflict")
        if not parent_positive <= fixed_variables or inherited_positive - fixed_variables:
            raise ValueError(f"{leaf_id}: positive primary units do not equal a subset of the fixed prefix")
        absent = parent_absent | inherited_absent
        available = set(range(1, 463)) - absent - fixed_variables
        validate_available_binding(row, available)
        prefix_cells = membership_cells(fixed, None)
        # Invariance is checked over the full primary block domain: every
        # signature orbit must be wholly available or wholly unavailable.
        for full_orbit in orbit_variables(set(range(1, 463)), prefix_cells):
            intersection = set(full_orbit) & available
            if intersection and intersection != set(full_orbit):
                raise ValueError(f"{leaf_id}: available domain is not prefix-subgroup invariant")
        generic = verify_exact_subgroup_orbits(available, prefix_cells, fixed, None)
        triple_rows = []
        for triple_tuple in TRIPLES:
            triple = frozenset(triple_tuple)
            if any(triple <= block for block in fixed):
                continue
            # Independent coverer construction: extend T by every point pair.
            outside = sorted(set(POINTS) - triple)
            candidate_variables = {
                positions[tuple(sorted((*triple, *pair)))]
                for pair in itertools.combinations(outside, 2)
            }
            coverers = candidate_variables & available
            triple_cells = membership_cells(fixed, triple)
            groups = orbit_variables(coverers, triple_cells)
            triple_rows.append((len(groups), len(coverers), triple_tuple, groups))
        expected_count, expected_coverers, expected_triple, expected_groups = min(triple_rows, key=lambda item: item[:3])
        recorded_groups = [orbit["member_variables"] for orbit in row["covering_block_orbits"]]
        if (
            row["chosen_uncovered_triple"] != list(expected_triple)
            or row["eligible_covering_blocks"] != expected_coverers
            or row["branch_count"] != expected_count
            or recorded_groups != expected_groups
        ):
            raise ValueError(
                f"{leaf_id}: deterministic deficit partition mismatch "
                f"recorded={(row['chosen_uncovered_triple'], row['eligible_covering_blocks'], row['branch_count'])} "
                f"expected={(list(expected_triple), expected_coverers, expected_count)} "
                f"groups_equal={recorded_groups == expected_groups}"
            )
        expected_kind = "NO_ELIGIBLE_COVERER" if expected_coverers == 0 else "FIRST_OCCUPIED_COVERING_ORBIT"
        if row["deficit_kind"] != expected_kind:
            raise ValueError(f"{leaf_id}: deficit kind mismatch")
        triple_cells = membership_cells(fixed, frozenset(expected_triple))
        for full_orbit in orbit_variables(set(range(1, 463)), triple_cells):
            intersection = set(full_orbit) & available
            if intersection and intersection != set(full_orbit):
                raise ValueError(f"{leaf_id}: residual domain is not prefix-plus-triple invariant")
        if (
            row["prefix_stabilizer_cell_sizes"] != [len(cell) for cell in prefix_cells]
            or row["triple_stabilizer_cell_sizes"] != [len(cell) for cell in triple_cells]
        ):
            raise ValueError(f"{leaf_id}: stabilizer cell sizes mismatch")
        exact_groups = verify_exact_subgroup_orbits(
            {
                positions[tuple(sorted((*frozenset(expected_triple), *pair)))]
                for pair in itertools.combinations(sorted(set(POINTS) - set(expected_triple)), 2)
            }
            & available,
            triple_cells,
            fixed,
            frozenset(expected_triple),
        )
        if exact_groups != expected_groups:
            raise ValueError(f"{leaf_id}: signature classes are not exact declared-subgroup orbits")
        # The first occupied recorded orbit is unique because the classes are
        # exhaustive and pairwise disjoint.  Earlier-orbit negative units plus
        # a canonical positive unit therefore cover the completion space modulo
        # only the explicitly audited subgroup.
        flattened = [value for group in exact_groups for value in group]
        if len(flattened) != len(set(flattened)) or set(flattened) != {
            value for value in available if frozenset(expected_triple) <= frozenset(BLOCKS[value - 1])
        }:
            raise ValueError(f"{leaf_id}: first-occupied classes are not exhaustive/disjoint")
        receipt = row["semantic_contradiction_receipt"]
        if expected_count == 0:
            triple = frozenset(expected_triple)
            outside = sorted(set(POINTS) - triple)
            all_coverers = sorted(
                positions[tuple(sorted((*triple, *pair)))]
                for pair in itertools.combinations(outside, 2)
            )
            expected_forbidden = [
                {
                    "variable": value,
                    "reasons": [
                        *(
                            ["PARENT_CNF_NEGATIVE_UNIT"]
                            if value in parent_absent
                            else []
                        ),
                        *(
                            ["INHERITED_NEGATIVE_UNIT"]
                            if value in inherited_absent
                            else []
                        ),
                    ],
                }
                for value in all_coverers
            ]
            if (
                receipt["selected_triple"] != list(expected_triple)
                or receipt["coverage_clause_variables"] != all_coverers
                or receipt["coverage_clause_sha256"] != clause_digest(all_coverers)
                or receipt["forbidden_coverers"] != expected_forbidden
                or receipt["residual_eligible_variables"] != []
                or receipt["empty_residual_clause_sha256"] != clause_digest([])
                or any(value not in absent for value in all_coverers)
            ):
                raise ValueError(f"{leaf_id}: semantic contradiction receipt mismatch")
        elif receipt is not None:
            raise ValueError(f"{leaf_id}: unexpected semantic contradiction receipt")
        generic_total += len(generic)
        deficit_total += expected_count
        zero_count += expected_count == 0
    if (
        generic_total != manifest["generic_sixth_children"]
        or deficit_total != manifest["deficit_children"]
        or zero_count != manifest["zero_child_cases"]
    ):
        raise ValueError("aggregate branch count mismatch")
    return {
        "schema_version": 1,
        "status": "VALID",
        "manifest_sha256": digest(manifest_path),
        "case_count": len(recorded),
        "open_status_counts": dict(Counter(expected.values())),
        "generic_sixth_children": generic_total,
        "deficit_children": deficit_total,
        "zero_child_cases": zero_count,
        "reduction_fraction": 1 - deficit_total / generic_total,
        "checked_properties": [
            "exact 82-timeout plus 10,626-never-measured open membership",
            "all solver/replay UNSAT and SAT fifth leaves excluded",
            "cached parent CNF positive/negative primary units and inherited unit bindings",
            "deterministic live triple choice including empty eligible domains",
            "residual block domain invariant under the declared prefix-plus-triple subgroup",
            "signature cells are exact subgroup orbits via explicit within-cell relabelings",
            "first-occupied subgroup-orbit branches are exhaustive and disjoint",
            "zero-child coverage clauses and every parent/inherited forbidden-literal reason",
            "no CNF/proof equivalence or reuse inferred from a signature",
        ],
        "equivalence_limit": (
            "The audited subgroup fixes each ordered prefix block setwise. No equivalence, "
            "deduplication, CNF reuse, or proof reuse is claimed under a larger stabilizer "
            "that may permute prefix blocks, or from a signature alone."
        ),
        "claim_limit": (
            "Partition audit only. A zero-child receipt is a directly checked semantic "
            "coverage contradiction, not a solver-UNSAT certificate or replay receipt."
        ),
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
