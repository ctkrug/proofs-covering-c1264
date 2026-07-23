import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    path = ROOT / "checkers/audit_ordinary_c1153_deficit_partition.py"
    spec = importlib.util.spec_from_file_location("deficit_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_committed_deficit_partition_is_valid():
    module = load_checker()
    manifest = ROOT / "artifacts/classification/ordinary-c1153-v1/hard-tail-deficit-partition/manifest.json"
    result = module.audit(ROOT, manifest)
    assert result["status"] == "VALID"
    assert result["case_count"] == 82
    assert result["deficit_children"] < result["generic_sixth_children"]
