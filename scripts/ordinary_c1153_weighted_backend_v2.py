#!/usr/bin/env python3
"""Fast proposal backend for future ordinary-C(11,5,3) weighted work.

HiGHS is only a floating-point dual proposal engine. ``exact_check`` remains
the acceptance gate. This module is intentionally not wired into the frozen
shallow-weighted-scale-v1 campaign.
"""

from __future__ import annotations

import hashlib
import time

from build_ordinary_c1153_multi_deficit_gate import primary_units as _parse_primary_units
from run_ordinary_c1153_shallow_weighted_scale import BLOCK_TRIPLES


_PRIMARY_BY_OBJECT: dict[int, tuple[bytes, str, frozenset[int], frozenset[int]]] = {}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def cached_primary_units(parent_raw: bytes) -> tuple[set[int], set[int]]:
    """Parse a parent once after binding its immutable bytes to SHA-256."""
    key = id(parent_raw)
    cached = _PRIMARY_BY_OBJECT.get(key)
    if cached is None:
        digest = sha256_bytes(parent_raw)
        positive, negative = _parse_primary_units(parent_raw)
        cached = (
            parent_raw,
            digest,
            frozenset(positive),
            frozenset(negative),
        )
        _PRIMARY_BY_OBJECT[key] = cached
    elif cached[0] is not parent_raw:
        raise ValueError("Python object-identity cache collision")
    return set(cached[2]), set(cached[3])


def install_exact_identity_cache() -> None:
    """Patch only the two known parent-unit parse call sites in this process."""
    import run_ordinary_c1153_ilp_forced_gate as ilp_gate
    import run_ordinary_c1153_multi_deficit_discriminator as multi_gate

    ilp_gate.primary_units = cached_primary_units
    multi_gate.primary_units = cached_primary_units


def solve_highs(
    uncovered: list[tuple[int, ...]], available: list[int], seconds: float = 1.0
) -> tuple[str, list[dict[str, object]], float]:
    """Return a floating dual proposal from one in-process continuous LP."""
    import highspy
    import numpy as np

    started = time.perf_counter()
    row_index = {triple: index for index, triple in enumerate(uncovered)}
    starts = [0]
    indices: list[int] = []
    for value in available:
        indices.extend(row_index[triple] for triple in BLOCK_TRIPLES[value - 1] if triple in row_index)
        starts.append(len(indices))
    lp = highspy.HighsLp()
    lp.num_col_ = len(available)
    lp.num_row_ = len(uncovered)
    lp.col_cost_ = np.ones(lp.num_col_, dtype=np.float64)
    lp.col_lower_ = np.zeros(lp.num_col_, dtype=np.float64)
    lp.col_upper_ = np.full(lp.num_col_, highspy.kHighsInf, dtype=np.float64)
    lp.row_lower_ = np.ones(lp.num_row_, dtype=np.float64)
    lp.row_upper_ = np.full(lp.num_row_, highspy.kHighsInf, dtype=np.float64)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = np.asarray(starts, dtype=np.int32)
    lp.a_matrix_.index_ = np.asarray(indices, dtype=np.int32)
    lp.a_matrix_.value_ = np.ones(len(indices), dtype=np.float64)
    solver = highspy.Highs()
    solver.setOptionValue("output_flag", False)
    solver.setOptionValue("threads", 1)
    solver.setOptionValue("time_limit", float(seconds))
    if solver.passModel(lp) != highspy.HighsStatus.kOk:
        return "MODEL_ERROR", [], time.perf_counter() - started
    solver.run()
    status = solver.modelStatusToString(solver.getModelStatus())
    duals = []
    if status == "Optimal":
        solution = solver.getSolution()
        duals = [
            {"triple": list(triple), "value": float(value)}
            for triple, value in zip(uncovered, solution.row_dual)
        ]
    return status, duals, time.perf_counter() - started


def exact_check(domain: dict[str, object], certificate: dict[str, object] | None) -> bool:
    """Independently check a rationalized weighted obstruction exactly."""
    if certificate is None:
        return False
    uncovered = {tuple(row) for row in domain["uncovered"]}
    weights: dict[tuple[int, ...], int] = {}
    for row in certificate["weights"]:
        triple, numerator = tuple(row[:3]), row[3]
        if (
            triple not in uncovered
            or triple in weights
            or not isinstance(numerator, int)
            or numerator <= 0
        ):
            raise ValueError("invalid exact certificate weight")
        weights[triple] = numerator
    total = sum(weights.values())
    denominator = certificate["denominator"]
    if total != certificate["total_numerator"]:
        raise ValueError("certificate total mismatch")
    if total <= domain["remaining_slots"] * denominator:
        raise ValueError("insufficient exact weighted lower bound")
    maximum = max(
        (
            sum(weight for triple, weight in weights.items() if triple in BLOCK_TRIPLES[value - 1])
            for value in domain["available"]
        ),
        default=0,
    )
    if maximum != certificate["maximum_eligible_block_load"] or maximum > denominator:
        raise ValueError("exact certificate overload")
    return True
