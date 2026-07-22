from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLOCKING = ROOT / "artifacts" / "pilot" / "link-orbit-known-control-blocking.cnf"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


finder = load("find_next_link_orbit", ROOT / "scripts" / "find_next_link_orbit.py")


class NextLinkOrbitTests(unittest.TestCase):
    def test_no_fixed_block_exact_degree_encoding(self) -> None:
        cnf, blocks, ranges, blocker_count, root = finder.build(BLOCKING)
        self.assertEqual(len(blocks), 462)
        self.assertEqual(blocker_count, 320)
        self.assertEqual(len(ranges), 11)
        self.assertNotIn([1], cnf.clauses)
        self.assertEqual(ranges[0]["first"], 463)
        self.assertIsNone(root)

    def test_six_roots_are_disjoint_and_exhaustive(self) -> None:
        orbits = finder.root_orbits()
        self.assertEqual([len(orbit) for orbit in orbits], [80, 120, 10, 32, 160, 60])
        self.assertEqual(len(set().union(*orbits)), 462)
        for left in range(6):
            for right in range(left):
                self.assertFalse(orbits[left] & orbits[right])

    def test_root_case_fixes_only_canonical_after_earlier_orbits(self) -> None:
        cnf, _, _, _, root = finder.build(BLOCKING, 2)
        self.assertEqual(root["earlier_orbit_variables_forced_false"], 200)
        self.assertIn([root["canonical_variable"]], cnf.clauses)

    def test_root_zero_secondary_partition_is_complete(self) -> None:
        orbits = finder.secondary_orbits(0)
        self.assertEqual(len(orbits), 39)
        self.assertEqual(len(set().union(*orbits)), 461)
        cnf, _, _, _, root = finder.build(BLOCKING, 0, 1)
        secondary = root["secondary"]
        self.assertEqual(secondary["stabilizer_order"], 48)
        self.assertIn([secondary["canonical_variable"]], cnf.clauses)

    def test_root_zero_secondary_zero_tertiary_partition_is_complete(self) -> None:
        secondary = finder.secondary_orbits(0)
        tertiary = finder.tertiary_orbits(0, 0)
        eligible = set().union(*tertiary)
        self.assertEqual(
            eligible,
            set(__import__("itertools").combinations(range(1, 12), 5))
            - {finder.LINK_ROOTS[0], min(secondary[0])},
        )
        for left in range(len(tertiary)):
            for right in range(left):
                self.assertFalse(tertiary[left] & tertiary[right])
        cnf, _, _, _, root = finder.build(BLOCKING, 0, 0, 1)
        tertiary_record = root["tertiary"]
        self.assertEqual(tertiary_record["stabilizer_order"], 8)
        self.assertIn([tertiary_record["canonical_variable"]], cnf.clauses)

    def test_three_block_quaternary_partition_is_complete(self) -> None:
        secondary = finder.secondary_orbits(0)
        tertiary = finder.tertiary_orbits(0, 0)
        quaternary = finder.quaternary_orbits(0, 0, 1)
        earlier_tertiary = set().union(*tertiary[:1])
        eligible = set(__import__("itertools").combinations(range(1, 12), 5)) - {
            finder.LINK_ROOTS[0], min(secondary[0]), min(tertiary[1]),
        } - earlier_tertiary
        self.assertEqual(set().union(*quaternary), eligible)
        for left in range(len(quaternary)):
            for right in range(left):
                self.assertFalse(quaternary[left] & quaternary[right])
        cnf, _, _, _, root = finder.build(BLOCKING, 0, 0, 1, 1)
        record = root["quaternary"]
        self.assertEqual(record["stabilizer_order"], 2)
        self.assertIn([record["canonical_variable"]], cnf.clauses)

    def test_quaternary_requires_tertiary_index(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a tertiary"):
            finder.build(BLOCKING, 0, 0, None, 0)

    def test_rejects_nonprimary_orbit_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "bad.cnf"
            path.write_text("p cnf 462 1\n" + " ".join(["-1"] * 19 + ["-463", "0"]) + "\n")
            with self.assertRaises(ValueError):
                finder.parse_blockers(path, 462)


if __name__ == "__main__":
    unittest.main()
