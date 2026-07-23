# Fifth-level suffix terminal review

Status: **suffix fully measured; ordinary classification incomplete**.

The global covering bound remains `40 <= C(12,6,4) <= 41`, and the separate
extension ledger remains `33/47` certified. Nothing in this tranche changes
either statement.

## Completed work

- Immutable suffix segments `0` through `127` completed under the frozen
  five-second, four-worker protocol. All segment QA gates passed.
- All `32,597` selected suffix leaves were measured: `32,547` solver-UNSAT
  with retained hash-bound proofs, `50` fixed-cap timeouts, and no SAT.
- Eleven resumable bulk certification batches independently reconstructed and
  replayed `11,264` proofs. Deterministic segment QA independently replayed
  another `4,046`; the two sets are disjoint. Thus `15,310` suffix UNSAT
  leaves are replay-certified and `17,237` suffix proofs remain provisional.
- The pre-existing discriminator contributes `64` more replay-certified fifth
  leaves and `32` timeouts.
- The app crash interrupted segment 45 after 108 case receipts and batch 2
  after 65 certification receipts. Both resumed from those exact receipts;
  neither completed case was rerun.

The independent terminal aggregation is `VALID`. Across all `43,319`
fifth-level branches, `32,693` are measured, `32,611` have an UNSAT outcome,
`15,374` are replay-certified, `82` timed out, and `10,626` were intentionally
never measured. Therefore `10,708` fifth leaves remain open. No fourth-level
parent is completely certified.

## Performance and storage

- Retained compressed suffix proofs: `3,670,911,145` bytes.
- Persistent segment artifacts: `3,734,186,756` bytes; certification receipts
  and replay logs: `279,940,156` bytes.
- Maximum conservative per-segment transient-disk bound: `54,835,586` bytes;
  approximately 26 GiB remained free at the terminal gate.
- In the 4,046 sampled proofs, compressed size median was `110,505.5` bytes,
  p95 `113,259`, and maximum `3,191,150`.
- Bulk certification recorded `11,264` cases in `3,442.44` worker-wall seconds,
  or `3.27` certificates/second. Reconstruction averaged `0.00309` seconds,
  decompression `0.00382`, and external replay `0.28874` per case. At that
  observed single-worker rate, the `17,237`-proof backlog is about 1.46 hours.

## Hard-tail hypothesis and discriminator

The falsifiable hypothesis is that early first-present orbit choices are hard
because they accumulate too few negative block units. The frozen evidence has
58.33% and 62.50% timeout rates at fifth orbits zero and one, 5.56% in the
remaining early prefix, 0.75% in the first suffix quartile, and 0% in the
later half.

A separate checker validated an exhaustive, disjoint sixth-block partition of
the 48 timeout leaves frozen through segment 24: 6,815 children under the exact
five-block stabilizers. The prediction is that at least 75% of latter-half
sixth children close and remaining timeouts concentrate in the first quarter.
Fewer than 75% closing, or diffuse timeout mass, falsifies the rank explanation
and triggers clustering by five-block incidence type/stabilizer.

The final hard tail has 82 timeouts, so the audited snapshot is not yet the
launch manifest: 34 later timeouts must be added and independently audited.

## Positive lane

No residual-extension SAT search was launched. The host has eight logical CPUs
and 8 GiB RAM; the four-worker harvest, one replay worker, and other active
proof-lab processes consumed the genuine headroom. Running the eleven
conditional residual CNFs would have materially slowed the primary
classification and certification lanes. This is a capacity decision, not a
negative mathematical result.

## Next action

The single highest-value experiment is to refresh the sixth-block discriminator
from 48 to all 82 terminal timeouts, audit only the 34 additions plus global
union/disjointness, and run the predeclared stratified early-versus-latter
sample at the unchanged cap. If its >=75% latter-half prediction passes, scale
the cheap sixth suffix and use the same structural split to attack the deferred
10,626 early-prefix leaves. If it fails, stop rank-based splitting and cluster
the full 10,708-leaf residual by fixed five-block incidence/stabilizer before
selecting another method.

The classification cannot be called complete until every retained proof is
exhaustively replayed, all 10,708 open fifth leaves are resolved or soundly
partitioned deeper, and every parent aggregation is independently audited.
