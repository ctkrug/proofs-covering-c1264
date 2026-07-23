## Verification memo

**Best live route:** independently validate the ordinary \(C(11,5,3)=20\) classification reduction before further \(C(12,6,4)\) search. It is the current structural bottleneck; the constructive slack sampler is stopped absent a new basin/selector, while the cardinality alternative underperformed its control. The official table still reports \(40\le C(12,6,4)\le41\). [La Jolla Covering Repository](https://ljcr.dmgordon.org/cover/show_cover.php?v=12&k=6&t=4)

**What I verified (computed, not a theorem):** the immutable fourth-level manifest has 13 parents and 790 canonical branches. I regenerated, in `/tmp`, the five top-level and 42 third-level CNFs from the representative and semantic recipe; every regenerated CNF matched its recorded SHA-256. The independent partition checker then validated all 790 branches. One regenerated leaf, `intersection-3-third-00-fourth-031`, replayed with local `drat-trim`.

**Critical accounting correction:** 406 independently replayed UNSAT leaves + 32 fixed-cap timeouts = 438 measured leaves. Therefore **352 of 790 are unmeasured**, yielding **384 open branches**, not 32. The 32 are only the measured timeout subset.

**Cheapest discriminator:** first run a hash-bound inventory/reconstruction gate, before any new solver work:

1. Rebuild the 5+42 parent CNFs into a temporary directory and require exact manifest hashes.
2. Recompute the 13 stabilizer partitions and require 790 branches.
3. Require a one-to-one table of all 790 IDs: 406 replayed UNSAT, 32 timeout, 352 unmeasured.
4. Replay all 406 proofs against regenerated exact CNFs with a checker independent of the solver; any mismatch stops the route.

This kills either a hidden artifact/partition error or the misleading “32 remaining” premise cheaply. A nonisomorphic 20-block ordinary cover immediately falsifies uniqueness.

**Controls:**

- Validate the maintained 20-block representative covers all 165 triples and has 20 distinct blocks.
- Hash-check parent CNFs, unit recipes, compressed and decompressed proofs.
- Negative control: alter one branch unit; the exact-CNF hash and proof replay must fail.
- Treat SAT models as candidates only after direct coverage and isomorphism testing.
- Treat UNKNOWN/timeout as open; never infer UNSAT from a partial proof.

**Failure modes to attack:**

- The checked-out repository omits ignored `*.cnf` parents, so the existing audit script fails directly despite the Python dependency being present.
- Existing runner paths reference a missing `.venv/sat-audit-tools/...` toolchain.
- Boundary results were stored under the discriminator campaign directory, so replay must bind each leaf to its protocol/selection rather than trust directory names.
- The present independent-audit receipt alone is not sufficient reproducibility evidence until reconstruction is rerunnable.

**Search-efficiency pass:** symmetry is already the largest safe reduction: 5,246 eligible fourth blocks across parents collapse to 790 first-present stabilizer orbits, an **84.9% reduction**. Retain the 13 parent CNFs plus unit recipes rather than materializing child CNFs; stream the 51 MB compressed proof portfolio; batch proof replay conservatively (up to four workers only if memory remains bounded). Reconstruct shared coverage/cardinality/blocker clauses once per parent. Do not reuse incremental solver state: the matched incremental control closed 0/10 leaves. The reusable artifact should be a permanent deterministic parent-CNF reconstructor plus full 790-row status manifest.

**Stop condition:** do not scale any ordinary-link solver tranche unless all reconstruction hashes and the full 406-proof replay pass. Stop/repartition on any coverage, orbit, hash, or replay mismatch; stop for independent isomorphism audit on SAT.

**What Sol should reject:** any exact-value claim, any claim that only 32 fourth leaves remain, and any “independent audit” that cannot regenerate its ignored CNFs. Verify the 406 closures and the 352-unmeasured accounting independently before allocating more proof search.

No durable research files were changed.
