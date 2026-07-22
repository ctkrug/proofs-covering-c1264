import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostTrancheClassificationTests(unittest.TestCase):
    def test_open_classes_partition_current_audited_ledger(self):
        with tempfile.NamedTemporaryFile(suffix=".json", dir=ROOT, delete=False) as handle:
            output = Path(handle.name)
        try:
            subprocess.run(
                [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/classify_remaining_frontier.py"),
                 "--output", str(output)], check=True, cwd=ROOT, capture_output=True, text=True,
            )
            value = json.loads(output.read_text())
            self.assertEqual(value["global_ledger"], "32/47")
            self.assertEqual(value["open_total"], 15)
            self.assertEqual(value["counts"], {
                "blocked_by_newly_discovered_orbit": 2,
                "fixed_cap_timeout": 12,
                "never_measured": 1,
            })
            self.assertEqual([row["id"] for row in value["classes"]["never_measured"]], ["s-r0-1"])
            self.assertEqual(
                [row["id"] for row in value["classes"]["blocked_by_newly_discovered_orbit"]],
                ["t-16", "t-17"],
            )
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
