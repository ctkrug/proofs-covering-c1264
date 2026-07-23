from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_ordinary_c1153_shallow_weighted_pipeline_v2.py"


def load_pipeline():
    spec = spec_from_file_location("shallow_weighted_pipeline_v2", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_segment_counts_include_short_final_segment():
    pipeline = load_pipeline()
    assert pipeline.expected_segment_count(83) == 2048
    assert pipeline.expected_segment_count(84) == 1800


def test_short_final_segment_generation_and_audit_validate():
    pipeline = load_pipeline()
    folder, summary = pipeline.validate_generation(84)
    audit = pipeline.validate_audit(84, folder, summary)
    assert summary["selected"] == 1800
    assert audit["selected"] == 1800
    assert audit["status"] in {"VALID", "VALID_GATE_FAILED"}
