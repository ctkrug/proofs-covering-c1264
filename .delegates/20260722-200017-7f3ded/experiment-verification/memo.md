## Verification memo

**Current uncertainty:** the official table still reports \(40\le C(12,6,4)\le41\), with a 41-block simulated-annealing construction. [La Jolla Covering Repository](https://ljcr.dmgordon.org/cover/show_cover.php?v=12&k=6&t=4)

**Best live route:** a *genuine three-block, point-degree-preserving ejection-chain* search from the six-defect 40-block near-cover. The two registered routes were tied at 30.36, but the kmtotalizer challenger has failed its fixed benchmark (8 verified closures versus sequential’s 15), while exact-degree two-block repair has four negative runs. Two barrier-crossing runs accepted 35,000 trades total yet remained at six uncovered quadruples. The repository’s own tournament plan therefore calls for a neighborhood with temporary slack or at least three-block repair.

**Cheapest discriminator:** implement only the three-block extension, then run 20 frozen seeds with 10,000 scored proposals/seed (hard 10 s wall cap/seed; stop early only on a verified witness). Each move must:

- remove/add three distinct blocks, retain 40 distinct blocks and exact point degree 20;
- add a block containing a currently uncovered quadruple;
- preserve aggregate point incidence;
- be indecomposable into a legal two-block trade;
- score primarily by uncovered quadruples, then pair-deficit/excess only as tie-breakers.

The retained signal is a directly audited best value of at most five uncovered quadruples, or a valid zero-defect witness. If all 20 runs remain at six or worse, demote this warm-start basin; it says nothing global about 40-covers.

**Controls and independent verification:**

- Pin the 41-block source hash `395bc8…13e5`; rerun its positive cover check and a one-block-deletion negative check.
- Keep the existing two-block barrier receipts as the historical control; do not rerun them unchanged.
- Producer writes seed, executable/source hashes, warm-start deletion, proposal/accept counts, final 40 blocks, and a hash-chained accepted-move trace.
- A new standalone checker must replay the trace, verify each move’s distinctness, exact point degrees, incidence preservation, and indecomposability, then recompute all 495 quadruple counts from scratch.
- Run existing `checkers/verify_cover.py --expected-blocks 40` on any zero-defect output in a separate process. Also permute point labels and recheck coverage as a metamorphic control.
- Treat solver/search status and internal delta counts as diagnostic only; the direct checker is the acceptance gate.

**Search-efficiency design:** retain the forced perfect-matching normalization—valid by the independently checked point/pair lower-bound arithmetic—but do not add further symmetry restrictions. Precompute the 924 block-to-15-quadruple masks and two-block signature buckets once. A targeted three-block proposal uses one missing quadruple (28 possible added blocks) plus sampled removal triples; incremental updates touch at most 45 quad counters, versus rescoring all 495, an approximately **11× safe delta reduction**. Avoid enumerating all \(\binom{924}{3}\) triples; derive the remaining two additions from the precomputed pair-signature bucket. Batch neither seeds nor score updates across workers; the route is random and host-policy permits only one active shared-host search.

**Failure modes:** accidentally generating disguised two-block moves; duplicate blocks; broken fixed-matching coordinates; trace/checker sharing producer logic; energy improvements that hide unchanged defect count; startup time excluded from cost; and seed selection after seeing outcomes. All are blocked by the trace audit, fixed seed manifest, primary-metric rule, and total runtime receipt.

**Reusable artifact:** `artifacts/constructive/three-block-screen-<id>/manifest.json`, per-seed results/traces, and `checkers/audit_three_block_screen.py`. This is reusable for later neighborhoods without treating a negative screen as an exclusion.

**Sol should reject:** any “no witness” as lower-bound evidence; any candidate accepted only by the producer; any scale-up without an audited improvement below six; and any claim that the 20-seed screen exhausts the matching-normalized space. Sol should independently verify the baseline invariant receipt, one full trace replay, and every alleged witness directly.
