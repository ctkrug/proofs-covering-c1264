import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


builder = load("build_sequential_frontier_sweep", "scripts/build_sequential_frontier_sweep.py")
profiler = load("profile_sequential_survivors", "scripts/profile_sequential_survivors.py")
runner = load("run_sequential_frontier_sweep", "scripts/run_sequential_frontier_sweep.py")


class SequentialFrontierSweepTests(unittest.TestCase):
    def test_builder_selects_exactly_the_open_frontier(self):
        value = builder.build()
        ids = [row["id"] for row in value["leaves"]]
        self.assertEqual(32, len(ids))
        self.assertEqual(32, len(set(ids)))
        self.assertEqual(value["leaves"][0]["id"], "s-r1-3")
        self.assertTrue(set(value["preserved_certified_nodes"]).isdisjoint(ids))
        self.assertEqual(60, value["seconds_per_run"])
        self.assertEqual("sequential", value["method"])

    def test_profiler_removes_only_replayed_closures(self):
        manifest = builder.build()
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temporary:
            base = Path(temporary)
            manifest_path = base / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            checkpoint_path = base / "checkpoint.json"
            checkpoint = {
                "manifest_sha256": profiler.sha(manifest_path),
                "results": [
                    {"leaf_id": manifest["leaves"][0]["id"], "status": "UNSAT_VERIFIED", "solver_elapsed_seconds": 1.0},
                    {"leaf_id": manifest["leaves"][1]["id"], "status": "UNKNOWN", "solver_elapsed_seconds": 60.0},
                ],
            }
            checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
            result = profiler.profile(manifest_path, checkpoint_path, builder.PORTFOLIO)
        self.assertEqual(31, result["survivor_count"])
        self.assertNotIn(manifest["leaves"][0]["id"], {row["id"] for row in result["survivors"]})
        self.assertIn(manifest["leaves"][1]["id"], {row["id"] for row in result["survivors"]})
        self.assertGreater(len(result["classes"]), 0)

    def test_runner_accepts_rebuilt_five_orbit_manifest(self):
        manifest = builder.build()
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            verified = runner.verify(path)
        self.assertEqual(len(verified["leaves"]), 32)


if __name__ == "__main__":
    unittest.main()
