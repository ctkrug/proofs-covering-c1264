#!/usr/bin/env python3
"""Build a compact coverage-deficit partition for all open fifth leaves."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTS = tuple(range(1, 12))
BLOCKS = tuple(itertools.combinations(POINTS, 5))
TRIPLES = tuple(itertools.combinations(POINTS, 3))
BLOCK_SETS = {block: frozenset(block) for block in BLOCKS}
TRIPLE_COVERERS = {
    triple: frozenset(block for block in BLOCKS if frozenset(triple) <= BLOCK_SETS[block])
    for triple in TRIPLES
}
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split"
FIFTH = BASE / "manifest.json"
TERMINAL = BASE / "terminal-aggregate-audit.json"
DISCRIMINATOR = BASE / "discriminator-5s-summary.json"
LEDGER = BASE / "suffix-scale-ledger.json"
TARGET = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe_sha(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + "\n").encode()).hexdigest()


def clause_sha(values: list[int]) -> str:
    return hashlib.sha256((" ".join(map(str, values)) + (" " if values else "") + "0\n").encode()).hexdigest()


def fifth_units(parent: dict[str, object], index: int) -> list[int]:
    return [
        *[-value for orbit in parent["fifth_orbits"][:index] for value in orbit["member_variables"]],
        parent["fifth_orbits"][index]["canonical_variable"],
    ]


def parent_primary_units(path: Path) -> tuple[set[int], set[int]]:
    """Read exact primary-variable units from a cached parent DIMACS."""
    positive: set[int] = set()
    negative: set[int] = set()
    with path.open() as source:
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
    overlap = positive & negative
    if overlap:
        raise ValueError(f"parent CNF has conflicting primary units: {sorted(overlap)}")
    return positive, negative


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


def measured_statuses(ledger: dict[str, object]) -> dict[str, str]:
    discriminator = json.loads(DISCRIMINATOR.read_text())
    statuses = {row["leaf_id"]: row["status"] for row in discriminator["outcomes"]}
    if len(statuses) != len(discriminator["outcomes"]):
        raise ValueError("duplicate discriminator result")
    for segment in ledger["segments"]:
        directory = BASE / "segments" / f"segment-{segment['segment']:04d}"
        receipt = json.loads((directory / "runner-receipt.json").read_text())
        paths = sorted(directory.glob("*/result.json"))
        if len(paths) != receipt["selected"] or receipt["completed"] != receipt["selected"]:
            raise ValueError(f"segment {segment['segment']} is incomplete")
        for path in paths:
            row = json.loads(path.read_text())
            if row["leaf_id"] in statuses:
                raise ValueError("measured sets overlap")
            statuses[row["leaf_id"]] = row["status"]
    return statuses


def cells(fixed: tuple[tuple[int, ...], ...], triple: tuple[int, ...] | None = None) -> tuple[tuple[int, ...], ...]:
    buckets: dict[tuple[object, ...], list[int]] = {}
    triple_set = set(triple or ())
    for point in POINTS:
        key = (*tuple(point in block for block in fixed), point in triple_set) if triple is not None else tuple(point in block for block in fixed)
        buckets.setdefault(key, []).append(point)
    return tuple(tuple(buckets[key]) for key in sorted(buckets))


def orbit_rows(values: set[tuple[int, ...]], partition: tuple[tuple[int, ...], ...], positions: dict[tuple[int, ...], int]) -> list[dict[str, object]]:
    groups: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
    cell_sets = tuple(frozenset(cell) for cell in partition)
    for block in values:
        key = tuple(len(BLOCK_SETS[block] & cell) for cell in cell_sets)
        groups.setdefault(key, []).append(block)
    rows = []
    for index, blocks in enumerate(sorted((sorted(group) for group in groups.values()), key=lambda group: group[0])):
        variables = [positions[block] for block in blocks]
        rows.append({
            "index": index,
            "canonical_variable": variables[0],
            "member_variables": variables,
            "size": len(variables),
        })
    return rows


def build() -> dict[str, object]:
    fifth, terminal, ledger = map(lambda path: json.loads(path.read_text()), (FIFTH, TERMINAL, LEDGER))
    if terminal["status"] != "VALID" or terminal["counts"]["open_distinct"] != 10708:
        raise ValueError("terminal aggregate is not the exact 10,708-open checkpoint")
    parents = {parent["id"]: parent for parent in fifth["parents"]}
    all_rows = []
    for parent in fifth["parents"]:
        all_rows.extend((f"{parent['id']}-fifth-{index:03d}", parent, index) for index in range(parent["branch_count"]))
    if len(all_rows) != 43319 or len({row[0] for row in all_rows}) != 43319:
        raise ValueError("fifth manifest domain mismatch")
    measured = measured_statuses(ledger)
    unsat_statuses = {"UNSAT_VERIFIED", "UNSAT_VERIFIED_BY_RUNNER", "PROVISIONAL_UNSAT_PROOF_RETAINED"}
    foreign = set(measured.values()) - unsat_statuses - {"FIXED_CAP_TIMEOUT"}
    if foreign:
        raise ValueError(f"unexpected measured statuses: {sorted(foreign)}")
    open_rows = []
    for leaf_id, parent, index in all_rows:
        status = measured.get(leaf_id)
        if status in unsat_statuses:
            continue
        open_rows.append((leaf_id, parent, index, "FIXED_CAP_TIMEOUT" if status == "FIXED_CAP_TIMEOUT" else "NEVER_MEASURED"))
    counts = Counter(row[3] for row in open_rows)
    if counts != {"FIXED_CAP_TIMEOUT": 82, "NEVER_MEASURED": 10626}:
        raise ValueError(f"open-set decomposition mismatch: {counts}")

    block_positions = {block: index for index, block in enumerate(BLOCKS, 1)}
    parent_unit_cache: dict[str, tuple[set[int], set[int]]] = {}
    cases = []
    generic_total = deficit_total = 0
    for leaf_id, parent, index, status in open_rows:
        fixed_four = tuple(tuple(block) for block in parent["fixed_blocks"])
        fifth_block = tuple(parent["fifth_orbits"][index]["canonical_block"])
        fixed = (*fixed_four, fifth_block)
        inherited = [*parent["inherited_fourth_units"], *fifth_units(parent, index)]
        parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
        parent_key = str(parent_path)
        if parent_key not in parent_unit_cache:
            if sha(parent_path) != parent["third_level_parent_cnf"]["sha256"]:
                raise ValueError(f"{leaf_id}: cached parent CNF hash mismatch")
            parent_unit_cache[parent_key] = parent_primary_units(parent_path)
        parent_positive, parent_negative = parent_unit_cache[parent_key]
        inherited_positive = {value for value in inherited if value > 0}
        inherited_negative = {-value for value in inherited if value < 0}
        if parent_negative & inherited_positive:
            raise ValueError(f"{leaf_id}: parent-negative/inherited-positive conflict")
        if inherited_negative & (parent_positive | inherited_positive):
            raise ValueError(f"{leaf_id}: inherited-negative/positive conflict")
        fixed_variables = {block_positions[block] for block in fixed}
        if not parent_positive <= fixed_variables:
            raise ValueError(f"{leaf_id}: parent positive primary unit is missing from fixed prefix")
        if inherited_positive - fixed_variables:
            raise ValueError(f"{leaf_id}: inherited positive primary unit is missing from fixed prefix")
        absent = parent_negative | inherited_negative
        available = set(BLOCKS) - {BLOCKS[value - 1] for value in absent} - set(fixed)
        generic_rows = orbit_rows(available, cells(fixed), block_positions)
        candidates = []
        already_covered = {triple for triple in TRIPLES if any(frozenset(triple) <= BLOCK_SETS[block] for block in fixed)}
        for triple in TRIPLES:
            if triple in already_covered:
                continue
            covering = set(TRIPLE_COVERERS[triple] & available)
            rows = orbit_rows(covering, cells(fixed, triple), block_positions)
            candidates.append((len(rows), len(covering), triple, rows))
        branch_count, eligible_count, triple, deficit_rows = min(candidates, key=lambda row: row[:3])
        prefix_cells = cells(fixed)
        triple_cells = cells(fixed, triple)
        contradiction = None
        if eligible_count == 0:
            covering_variables = sorted(block_positions[block] for block in TRIPLE_COVERERS[triple])
            forbidden = []
            for variable in covering_variables:
                if variable not in absent:
                    raise ValueError(f"{leaf_id}: zero-child coverer lacks an exact negative-unit reason")
                reasons = []
                if variable in parent_negative:
                    reasons.append("PARENT_CNF_NEGATIVE_UNIT")
                if variable in inherited_negative:
                    reasons.append("INHERITED_NEGATIVE_UNIT")
                forbidden.append({"variable": variable, "reasons": reasons})
            contradiction = {
                "semantic_status": "EMPTY_RESIDUAL_COVERAGE_CLAUSE_NOT_YET_SOLVER_CERTIFIED",
                "selected_triple": list(triple),
                "coverage_clause_variables": covering_variables,
                "coverage_clause_sha256": clause_sha(covering_variables),
                "forbidden_coverers": forbidden,
                "residual_eligible_variables": [],
                "empty_residual_clause_sha256": clause_sha([]),
                "claim_limit": "Semantic contradiction receipt only; generate and externally replay the exact CNF proof before ledger closure.",
            }
        cases.append({
            "id": leaf_id,
            "open_status": status,
            "fourth_parent_id": parent["id"],
            "top_parent": parent["top_parent"],
            "fifth_index": index,
            "fifth_position": position(index, parent["branch_count"]),
            "fixed_blocks": [list(block) for block in fixed],
            "third_level_parent_cnf": parent["third_level_parent_cnf"],
            "inherited_units": inherited,
            "inherited_unit_sha256": recipe_sha(inherited),
            "chosen_uncovered_triple": list(triple),
            "prefix_stabilizer_cell_sizes": [len(cell) for cell in prefix_cells],
            "triple_stabilizer_cell_sizes": [len(cell) for cell in triple_cells],
            "eligible_covering_blocks": eligible_count,
            "deficit_kind": "NO_ELIGIBLE_COVERER" if eligible_count == 0 else "FIRST_OCCUPIED_COVERING_ORBIT",
            "semantic_contradiction_receipt": contradiction,
            "available_primary_block_count": len(available),
            "available_primary_variables_sha256": recipe_sha(
                sorted(block_positions[block] for block in available)
            ),
            "generic_sixth_branch_count": len(generic_rows),
            "branch_count": branch_count,
            "covering_block_orbits": deficit_rows,
        })
        generic_total += len(generic_rows)
        deficit_total += branch_count
    manifest = {
        "schema_version": 2,
        "status": "BUILT_NOT_SOLVED",
        "bindings": {
            "fifth_manifest": {"path": str(FIFTH.relative_to(ROOT)), "sha256": sha(FIFTH)},
            "terminal_aggregate": {"path": str(TERMINAL.relative_to(ROOT)), "sha256": sha(TERMINAL)},
            "discriminator_summary": {"path": str(DISCRIMINATOR.relative_to(ROOT)), "sha256": sha(DISCRIMINATOR)},
            "suffix_ledger": {"path": str(LEDGER.relative_to(ROOT)), "sha256": sha(LEDGER)},
        },
        "selection": "Every fifth branch not carrying a solver/replay UNSAT result in the terminal aggregate sources: exactly 82 fixed-cap timeouts plus 10,626 never-measured leaves.",
        "open_status_counts": dict(counts),
        "invariant": "For the chosen triple T, no fixed block covers T. Every C(11,5,3) completion covers T, hence contains an available block covering T.",
        "partition_rule": "Restrict the five-block prefix stabilizer to permutations fixing T setwise; partition available T-covering blocks into orbits; select the least occupied orbit, force earlier covering orbits absent, and map one selected block to the orbit representative.",
        "action_exactness": "Each of the five fixed prefix blocks is held setwise and individually. Points with identical five-block membership vectors may be permuted freely; these symmetric-cell permutations form exactly the full prefix stabilizer. Requiring T setwise splits each cell by the T-membership flag. The resulting direct product of symmetric groups is exactly the prefix-and-triple stabilizer.",
        "orbit_witness": "Two blocks are in the same recorded orbit iff they have equal intersection counts with every prefix-and-triple cell. An explicit relabeling is obtained independently in each cell by bijecting the selected points of the first block to those of the second and extending to a permutation of the cell. Adjacent transpositions within each cell give generators.",
        "cache_limit": "Membership signatures are used only to cache this proved action/orbit computation. No CNF or proof is deduplicated from a signature without a separately checked variable/auxiliary relabeling.",
        "available_domain_rule": "A primary block is available only when it is neither fixed positive nor forbidden by a negative primary unit in the exact hash-bound cached parent CNF or the inherited fourth/fifth unit recipe. Parent and inherited positive/negative conflicts are rejected.",
        "representation": "Cached third-level parent CNF plus inherited fourth/fifth units, negative units for all earlier covering-block orbits, and one canonical positive unit; no duplicate CNFs are materialized.",
        "case_count": len(cases),
        "generic_sixth_children": generic_total,
        "deficit_children": deficit_total,
        "zero_child_cases": sum(case["branch_count"] == 0 for case in cases),
        "zero_child_mechanism": "A zero-child case is a semantic empty coverage clause: all 28 blocks covering its selected triple are forbidden by exact parent-CNF and/or inherited negative primary units. These are structural contradictions, counted separately from solver UNSAT until exact proofs replay.",
        "reduction_fraction": 1 - deficit_total / generic_total,
        "cases": cases,
        "claim_limit": "Structural partition only. No child was solved and no fifth/fourth parent closes from this manifest.",
    }
    TARGET.mkdir(parents=True, exist_ok=False)
    (TARGET / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({key: manifest[key] for key in ("case_count", "open_status_counts", "generic_sixth_children", "deficit_children", "reduction_fraction")}, sort_keys=True))
    return manifest


if __name__ == "__main__":
    build()
