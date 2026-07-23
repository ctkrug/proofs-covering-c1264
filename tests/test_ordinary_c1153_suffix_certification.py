import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts/certify_ordinary_c1153_suffix_batch.py"
    spec = importlib.util.spec_from_file_location("suffix_certification", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_streamed_exact_cnf_matches_existing_hash(tmp_path: Path) -> None:
    module = load_module()
    _, lookup = module.load_domain()
    result_path = next((module.BASE / "segments/segment-0011").glob("*/result.json"))
    result = module.json.loads(result_path.read_text())
    parent, index = lookup[result["leaf_id"]]
    assert module.unit_sha(parent["inherited_fourth_units"]) == result["inherited_fourth_unit_sha256"]
    units = parent["inherited_fourth_units"] + module.fifth_units(parent, index)
    target = tmp_path / "exact.cnf"
    variables, clauses = module.write_exact_cnf(ROOT / parent["third_level_parent_cnf"]["path"], units, target)
    assert (variables, clauses) == (result["exact_cnf_variables"], result["exact_cnf_clauses"])
    assert module.sha(target) == result["exact_cnf_sha256"]


def test_eligible_results_require_qa_passed_segment() -> None:
    module = load_module()
    _, lookup = module.load_domain()
    rows = module.eligible_results(lookup)
    assert rows
    assert len({row["leaf_id"] for row in rows}) == len(rows)
    assert all(row["segment"] >= 0 for row in rows)
    assert all(len(row["exact_cnf_sha256"]) == 64 and len(row["proof_sha256"]) == 64 for row in rows)
