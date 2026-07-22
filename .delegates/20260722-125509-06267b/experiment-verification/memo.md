Memo — experiment verification

**Best live route (proposal):** replace the sequential-counter degree equalities in the 47-node link frontier with a proof-producing `kmtotalizer` encoding, retaining the exact matching reduction, `C2 wr S5` canonical augmentation, coverage clauses, and catalog-4 orbit blockers.

**Rationale:** direct cubing closed only 10/128 sampled cubes (7.8125%); deeper fourth-layer branching and Glucose4 reuse are explicitly stopped. The alternative is genuinely different at the propagation/encoding layer while preserving the current decomposition. A dry build of the 11 link-degree constraints gives 20,482 variables and 81,378 clauses for `kmtotalizer`, versus 40,642 and 80,525 for sequential counters: a safe 49.6% variable reduction for only 1.06% more clauses. This is the best available low-cost structural reduction found.

**Cheapest discriminator:** 20 predeclared frontier leaves, each run cold under external CaDiCaL 1.7.3 for 10 seconds in both encodings (40 runs; ≤400 solver-seconds, before proof replay). Select deterministically by SHA-256 of `catalog4_hash || leaf-id`: 4 root-0 secondary, 4 root-1 secondary, and 12 root-0/secondary-0 tertiary leaves. Randomize within each matched pair and pin one core. Count a closure only when UNSAT has a DRAT replay; SAT is checked directly, canonicalized against all four catalogued orbits, then sent to the residual 40-block checker.

**Controls:**

- Rebuild catalog-4 from its four witness files before every run. I regenerated its absent blocker and independently audited it: blocker SHA-256 `d68f…cad4`, 1,616 clauses/images; audit SHA-256 `a89c…f769`, matching the recorded receipt.
- Rebuild both CNFs from the same primary-variable ordering, constraints, root units, and blocker hash; auditor verifies every non-cardinality clause byte-for-byte.
- Add a separate structural cardinality auditor that checks totalizer gates/ranges inductively, rather than reusing PySAT’s sequential-counter implementation.
- Run the existing sequential CNF as the matched cold control; preserve command, binary hash, seed/configuration, wall time, CNF hash, proof hash, and replay receipt.
- Retain the published 41-block cover as a positive end-to-end checker control. The current authoritative source still reports `40 ≤ C(12,6,4) ≤ 41`. [La Jolla Covering Repository](https://ljcr.dmgordon.org/cover/show_cover.php?v=12&k=6&t=4)

**Search-efficiency check:** symmetry is already the decisive reduction: fixed perfect matching gives a 10,395-fold quotient; link canonicalization uses the order-3,840 `C2 wr S5` action. Keep bitset incidence generation, streamed compressed DRATs, per-leaf batching, and reusable catalog blockers. Do not reuse learned clauses across changed encodings. Do not add a fourth canonical level: it expands ten parents to 3,074 children without a valid positive signal.

**Stop condition:** promote only if the alternative closes at least 8/20 (40%) with replayed proofs, has no semantic/audit disagreement, and proof growth projects below the existing 30-GB ceiling. Otherwise stop this encoding unchanged; UNKNOWN is not evidence.

**Likely failure modes:** catalog-4 blocker missing from the repository checkout; auxiliary-ID overlap; a totalizer auditor that merely reproduces the producer; timer overshoot; treating a new link as a cover; and sampling only low-index fourth children.

**Reusable artifact:** a hash-bound catalog-4 blocker regeneration receipt plus paired-tranche manifest and independent cardinality-structure auditor.

**Sol should reject:** un-replayed UNSAT results, PySAT-shared “independence,” any gate based on the prior biased fourth-child sample, and any exact-value claim before all canonical link cases are covered and every residual extension is independently verified.
