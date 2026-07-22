from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


repair = load("run_constructive_sat_repair", ROOT / "scripts" / "run_constructive_sat_repair.py")


class ConstructiveSatRepairTests(unittest.TestCase):
    def test_base_encodes_coverage_and_exact_point_degrees(self) -> None:
        cnf = repair.build_base()
        self.assertGreater(cnf.nv, 924)
        self.assertGreater(len(cnf.clauses), 495)
        self.assertEqual(len(repair.QUADS), 495)

    def test_known_41_source_minus_one_is_accepted_as_near_cover(self) -> None:
        lines = [line for line in (ROOT / "sources" / "ljcr-c1264-41.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
        temporary = ROOT / ".proof-experiments" / "test-near-cover.txt"
        temporary.parent.mkdir(exist_ok=True)
        temporary.write_text("\n".join(lines[:40]) + "\n", encoding="utf-8")
        try:
            self.assertEqual(len(repair.read_candidate(temporary)), 40)
        finally:
            temporary.unlink()


if __name__ == "__main__":
    unittest.main()
