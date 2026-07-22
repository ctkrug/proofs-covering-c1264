## Verification memo

Best live route: the gated kmtotalizer-vs-sequential cold benchmark on the 47-node canonical link frontier. It changes only the 11 degree equalities, while preserving the 165 triple-cover clauses, orbit blockers, and root units.

Reported checks: official DRAT-trim was restored at upstream revision `2e3b2dc…`, binary SHA `92f0aa…`. A trivial positive and negative checker control behaved correctly. More importantly, fresh CaDiCaL 1.7.3 replay of the archived root-2 link CNF closed in 4.12 s; its 14.3 MB DRAT proof verified and the source-to-CNF auditor passed. See [provenance](/root/proof-factory/research/covering-c1264/workspace/toolchains/drat-trim/PROVENANCE.md) and [control receipts](/root/proof-factory/research/covering-c1264/workspace/artifacts/controls/link-orbit-third-root-2-replay-20260722).

Cheapest discriminator: predeclare 20 leaves—secondary `(r,s)` = `(0,3),(0,6),(0,4),(1,5),(1,8),(1,3)`; tertiary indices = `0,29,32,24,27,10,2,11,26,1,6,30,15,5`. These are SHA-ranked from the hash-bound 47-node manifest, stratified 3/6 root-0 secondary, 3/8 root-1 secondary, and 14/33 tertiary. Run each twice, cold, CaDiCaL 1.7.3, 60 s/leaf: sequential then kmtotalizer. Maximum solver allocation is 40 CPU-minutes before replay.

The encoding delta is material: the 11 equalities use 20,020 kmtotalizer auxiliaries versus 40,180 sequential auxiliaries (49.8% fewer), with 853 more clauses.

Controls and acceptance:

- Emit a common, hash-bound non-cardinality core; byte-compare it between forms.
- Independently audit each totalizer’s point-literal universe, bound, auxiliary-range isolation, and clause confinement; reject malformed/overlapping ranges.
- Preserve CNF, solver log, proof, replay receipt, and independent CNF audit per UNSAT. SAT requires direct link validation and full-catalog canonicalization; UNKNOWN is neutral.
- Call kmtotalizer promising only if it yields at least 8/20 replay-verified UNSAT closures and at least four more than sequential under identical caps.

Stop immediately on any core-digest/cardinality-audit/verdict disagreement, a missing proof for an UNSAT claim, or projected proof storage above 30 GB. Redirect after the tranche if the acceptance rule fails; do not extend timeouts unchanged.

Main failure mode: all 189 historical validation receipts reference omitted `external.drat` files, so historical replays cannot be asserted despite their hashes. The fresh nontrivial control repairs tool availability, not archival completeness.

Scaling discipline: retain the exact 10,395 matching quotient and the order-3,840 link stabilizer; do not multiply those reductions as a global factor. Keep canonical augmentation and orbit blockers, stream/compress proofs only after hashing raw files, batch independent cold leaves with checkpointed receipts, avoid the ruled-out incremental wrapper, and reuse no solver state in the comparison.

Sol should reject any claim that this settles \(C(12,6,4)\), any “replayed historical proof” claim without the missing proof bytes, or any comparison lacking identical cores and independently replayed proofs.
