from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "minimize_link_residual_core_checkpointed",
    ROOT / "scripts" / "minimize_link_residual_core_checkpointed.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class CheckpointedCoreMinimizerTests(unittest.TestCase):
    def test_pair_equalities_are_prioritized(self) -> None:
        groups, _ = module.build_groups(
            ROOT / "artifacts" / "discoveries" / "link-orbit-s-r1-3" / "witness.txt",
        )
        seed = __import__("json").loads((
            ROOT / "artifacts" / "discoveries" / "link-orbit-s-r1-3" /
            "residual-extension" / "semantic-core.json"
        ).read_text())
        core = [row["group_index"] for row in seed["semantic_groups"]]
        order = sorted(core, key=lambda index: (groups[index]["kind"] != "pair_equality", index))
        self.assertTrue(all(groups[index]["kind"] == "pair_equality" for index in order[:27]))


if __name__ == "__main__":
    unittest.main()
