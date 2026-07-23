from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/classification/ordinary-c1153-v1/open-fifth-deficit-partition-v2"
FIFTH = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-fifth-split/manifest.json"
GENERIC = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-sixth-discriminator-final/manifest.json"


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load(
    "audit_open_deficit",
    ROOT / "checkers/audit_ordinary_c1153_open_deficit_partition.py",
)
GENERIC_CHECKER = load(
    "audit_generic_sixth",
    ROOT / "checkers/audit_ordinary_c1153_sixth_hard_tail_discriminator.py",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_case_domain(case_id: str) -> tuple[dict[str, object], list[int], set[int]]:
    fifth = json.loads(FIFTH.read_text())
    parent_id, index_text = case_id.rsplit("-fifth-", 1)
    parent = next(row for row in fifth["parents"] if row["id"] == parent_id)
    index = int(index_text)
    fixed = [
        *parent["fixed_blocks"],
        parent["fifth_orbits"][index]["canonical_block"],
    ]
    inherited = [*parent["inherited_fourth_units"], *CHECKER.fifth_recipe(parent, index)]
    parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
    _, parent_negative = CHECKER.parent_primary_units(parent_path)
    fixed_variables = {
        CHECKER.BLOCKS.index(tuple(block)) + 1
        for block in fixed
    }
    absent = parent_negative | {-value for value in inherited if value < 0}
    available = set(range(1, 463)) - absent - fixed_variables
    return parent, inherited, available


def test_parent_cnf_units_change_the_known_failed_case_domain() -> None:
    case_id = "intersection-3-third-00-fourth-000-fifth-008"
    parent, inherited, exact_available = exact_case_domain(case_id)
    parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
    _, parent_negative = CHECKER.parent_primary_units(parent_path)
    inherited_negative = {-value for value in inherited if value < 0}
    assert len(parent_negative - inherited_negative) == 30

    fixed = tuple(
        tuple(block)
        for block in [
            *parent["fixed_blocks"],
            parent["fifth_orbits"][8]["canonical_block"],
        ]
    )
    positions = {block: index for index, block in enumerate(CHECKER.BLOCKS, 1)}
    candidates = []
    for triple in CHECKER.TRIPLES:
        if any(set(triple) <= set(block) for block in fixed):
            continue
        coverers = {
            positions[block]
            for block in CHECKER.BLOCKS
            if set(triple) <= set(block)
        } & exact_available
        groups = CHECKER.orbit_variables(
            coverers,
            CHECKER.membership_cells(
                tuple(frozenset(block) for block in fixed),
                frozenset(triple),
            ),
        )
        candidates.append((len(groups), len(coverers), triple))
    assert min(candidates) == (15, 25, (3, 4, 6))


def test_exact_domains_match_all_82_valid_generic_cases() -> None:
    generic = {
        row["id"]: row
        for row in json.loads(GENERIC.read_text())["cases"]
    }
    assert len(generic) == 82
    for case_id, prior in generic.items():
        parent, inherited, exact_available = exact_case_domain(case_id)
        parent_path = ROOT / parent["third_level_parent_cnf"]["path"]
        generic_absent = GENERIC_CHECKER.parent_negative_units(parent_path) | {
            -value for value in inherited if value < 0
        }
        fixed = {tuple(block) for block in prior["fixed_blocks"]}
        generic_available = {
            index
            for index, block in enumerate(CHECKER.BLOCKS, 1)
            if block not in fixed and index not in generic_absent
        }
        assert exact_available == generic_available
        assert len(exact_available) == prior["eligible_sixth_blocks"]
        cells = CHECKER.membership_cells(
            tuple(frozenset(block) for block in prior["fixed_blocks"]),
            None,
        )
        assert CHECKER.orbit_variables(exact_available, cells) == [
            orbit["member_variables"] for orbit in prior["sixth_orbits"]
        ]


def test_available_domain_binding_rejects_one_variable_mutation() -> None:
    _, _, available = exact_case_domain(
        "intersection-3-third-00-fourth-000-fifth-008"
    )
    row = {
        "id": "adversarial-domain",
        "available_primary_block_count": len(available),
        "available_primary_variables_sha256": CHECKER.recipe_digest(
            sorted(available)
        ),
    }
    CHECKER.validate_available_binding(row, available)
    mutated = set(available)
    mutated.remove(min(mutated))
    with pytest.raises(ValueError, match="exact available-primary domain"):
        CHECKER.validate_available_binding(row, mutated)


def test_audit_rejects_tampered_eligible_set(tmp_path: Path) -> None:
    manifest = json.loads((BASE / "manifest.json").read_text())
    target = min(manifest["cases"], key=lambda row: row["id"])
    target["eligible_covering_blocks"] += 1
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="deterministic deficit partition mismatch"):
        CHECKER.audit(ROOT, tampered)


def test_all_open_deficit_partition_receipt() -> None:
    manifest_path = BASE / "manifest.json"
    audit_path = BASE / "independent-audit.json"
    manifest, audit = json.loads(manifest_path.read_text()), json.loads(audit_path.read_text())
    assert manifest["schema_version"] == 2
    assert audit["status"] == "VALID"
    assert audit["manifest_sha256"] == sha(manifest_path)
    assert manifest["case_count"] == audit["case_count"] == 10708
    assert manifest["open_status_counts"] == audit["open_status_counts"] == {
        "FIXED_CAP_TIMEOUT": 82,
        "NEVER_MEASURED": 10626,
    }
    assert manifest["generic_sixth_children"] == audit["generic_sixth_children"]
    assert manifest["deficit_children"] == audit["deficit_children"]
    assert manifest["zero_child_cases"] == audit["zero_child_cases"]
    assert manifest["generic_sixth_children"] == 1_772_515
    assert manifest["deficit_children"] == 19_650
    assert manifest["zero_child_cases"] == 8_476
    assert manifest["deficit_children"] < manifest["generic_sixth_children"]
