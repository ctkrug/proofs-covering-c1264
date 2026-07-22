from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load("verify_cover", ROOT / "checkers" / "verify_cover.py")
builder = load("build_pilot_instances", ROOT / "scripts" / "build_pilot_instances.py")
auditor = load("audit_pilot_instance", ROOT / "checkers" / "audit_pilot_instance.py")


class BaselineTests(unittest.TestCase):
    def test_published_41_block_control(self) -> None:
        result = checker.verify(
            ROOT / "sources" / "ljcr-c1264-41.txt", v=12, k=6, t=4, expected_blocks=41,
        )
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["covered_t_sets"], 495)

    def test_truncated_control_is_rejected(self) -> None:
        lines = (ROOT / "sources" / "ljcr-c1264-41.txt").read_text().splitlines()
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "truncated.txt"
            path.write_text("\n".join(lines[:-1]) + "\n")
            with self.assertRaisesRegex(ValueError, "not a cover"):
                checker.verify(path, v=12, k=6, t=4, expected_blocks=40)

    def test_direct_root_partition_and_counts(self) -> None:
        _blocks, first, first_meta = builder.direct_constraints("r0-present")
        _blocks, second, second_meta = builder.direct_constraints("no-r0-r1-present")
        self.assertEqual(first_meta["variables"], 924)
        self.assertEqual(first_meta["r0_variables"], 64)
        self.assertEqual(len(first), 495 + 66 + 1)
        self.assertEqual(len(second), 495 + 66 + 64 + 1)

    def test_link_counts(self) -> None:
        links, constraints, metadata = builder.link_constraints()
        self.assertEqual(len(links), 462)
        self.assertEqual(len(constraints), 165 + 11)
        self.assertEqual(metadata["variables"], 462)

    def test_frozen_instances_pass_independent_semantic_audit(self) -> None:
        for name in ("direct-r0", "direct-no-r0-r1", "link"):
            result = auditor.audit(
                ROOT / "artifacts" / "baseline" / f"{name}.opb",
                ROOT / "artifacts" / "baseline" / f"{name}.json",
            )
            self.assertEqual(result["status"], "valid")


if __name__ == "__main__":
    unittest.main()
