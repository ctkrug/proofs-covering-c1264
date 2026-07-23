# Proof Factory retrospective and transfer tests — 2026-07-23

Scope: read-only reconciliation of the live C campaign and three isolated local benchmarks. No C job was restarted, modified, or scheduled. Local source commit: `f5516c140224e39c01331aef0528d2dfda901a1d`; cloud service inspection at 2026-07-23 13:10 UTC found active Lean/Iris work, not C work. The C integration checkout and cloud receipts are reconciled by the cited hash-bound manifests; dashboards were not used as evidence.

## 1. Verified campaign state

The only global mathematical claim remains `40 <= C(12,6,4) <= 41`. The extension ledger is **33/47 certified**; it is not a catalogue-exhaustion proof. The active route is ordinary 20-block `C(11,5,3)` classification. Its durable status is 32,611 replay-certified fifth leaves, 8,476 audited semantic zero-child receipts, and 216/384 closed fourth parents (the public Proof Factory problem record reports these exact counts). The current local checkpoint is a frozen shallow weighted scale at `f5516c14`; segments 000–002 are recorded, not promoted to any ancestor closure.

Evidence classes must remain separate:

* Replayed solver evidence: individual exact reconstructed CNFs plus externally replayed DRAT proofs; only these enter certified-leaf accounting.
* Semantic receipts: the v2 partition records 8,476 empty coverage clauses and explicitly says they require exact-CNF replay before ledger closure.
* Weighted evidence: exact rational set-cover duals close a formula only after independent audit; exhaustive bottom-up aggregation is needed before a parent closes.
* Provisional/conditional evidence: timeouts, sampled runs, failed local `CORE_UNSAT`, and residual-extension nonextensions do not prove a global negative theorem.
* Failed audit: `open-fifth-deficit-partition-failed-4bfca/independent-audit-failed-4bfca070.json` preserves the cached-parent-negative-unit omission. It invalidates that pilot, not the audited v2 partition.

A valid `C(12,6,4)=41` proof still needs: an exhaustive, justified ordinary-link classification (or an alternative exhaustive route); replayed exact certificates for every terminal exclusion; complete child-by-child aggregation at every promoted parent; and a globally audited mapping from the exhaustive link cases to all 47 extension nodes. A verified 40-block witness would settle the opposite value directly.

## 2. What worked, what failed, and why

Sequential SAT/DRAT and independent replay are the highest-confidence closure mechanism, but proof bytes and replay time are their cost. Canonical partitions and deficit branching are the main scale reducers: the v2 open partition reduces 1,772,515 generic sixth children to 19,650 exact deficit children (98.8914%), with a stated stabilizer proof. Semantic zero-child receipts have high closure potential and low storage, but carry high audit burden because their meaning depends on every inherited and cached unit. Weighted duals are exceptionally compact and independently checkable; their limitation is that they are a lower-bound obstruction, not an aggregation theorem. Depth-two splitting made 4,402 terminal cubes tractable in a selected 12-formula gate, but it is problem-specific scheduling scaffolding until its reconstruction contract transfers. Immutable segments and multi-host reconciliation are operationally valuable: hashes allow exact resume and make provenance reviewable; they do not establish a theorem by themselves.

The cached-parent-unit bug was a shared-domain bug: the pilot derived availability from inherited recipe units but omitted negative primary units already present in the cached parent CNF. Earlier checks compared internally consistent derived data, rather than reconstructing the parent CNF and checking the effective domain. The v2 regression rule now requires hash-bound cached-parent parsing, rejects positive/negative conflicts, and tags every forbidden coverer with parent versus inherited reason. Remaining analogous risks are stale manifest-to-CNF bindings, symmetry actions that are only heuristic, accidental proof/CNF mismatch, and promotion of partial child results.

## 3. Reusable Proof Factory assets

| Asset | Class / contract / verifier | Maturity and boundary |
|---|---|---|
| Canonical augmentation | Generic finite-CSP symmetry action; input prefix plus proved group, output orbit representatives and relabeling witness; independent group/action audit | Mature for set systems; `canonical-partition` package |
| Exact residual-CNF reconstruction | Generic SAT; parent hash plus ordered units -> DIMACS hash; separate byte-level reconstructor | Mature; `residual-cnf` package |
| Content-addressed receipts | Generic; immutable manifest declares inputs, command, outputs, hashes; hash verifier | Mature; `proof-receipts` package |
| Empty coverage-clause contradiction | Covering-specific; coverage clause plus all forbidden literals/reasons -> semantic receipt then CNF/DRAT | Audit-gated; `coverage-obstruction` package |
| Rational weighted set-cover dual | Covering-specific; uncovered t-sets, eligible blocks, rational weights -> inequality checker | Mature at formula level; `weighted-dual` package |
| Bottom-up aggregation | Generic finite partition; exhaustive child manifest + valid terminal receipts -> parent receipt | Mature contract, limited scale data; `aggregate` package |
| DRAT replay/checking | Generic SAT; CNF/proof/checker pinned -> replay receipt | Mature; retain external binary pinning |
| Immutable distributed segments | Generic batch computation; frozen queue, capacity cap, checkpoint hash -> reconciled segment | Mature operationally; `segments` package |

Do not refactor these boundaries into the active campaign: extract only from frozen, tested snapshots.

## 4. External relevance and transfer tests

Candidate ranking (known ground truth first): `S(3,4,8)` (best: rich t=3 residuals, 14-block exact optimum); `C(9,3,2)=12` (affine plane); `C(7,3,2)=7` (Fano); `C(13,3,2)=26` (Steiner triple system); `C(13,4,2)=13` (projective plane of order 3); `C(15,3,2)=35` (Steiner triple system). All have direct cover checkers and counting lower bounds; the La Jolla repository is the maintained covering source, and its `C(9,3,2)` entry explicitly gives the affine construction.

Three pilots live under `transfer_tests/`, use no C receipts, and pass a separately written checker. Each removes two known blocks, spends one remaining slot on a non-design representative, and proves the remaining one-slot task impossible with a uniform rational set-cover dual. Results: Fano 105/105 representatives, affine 372/372, SQS(8) 518/518; zero-child count is 0 in all three. Naive wrong-child counts versus tested representatives are 588/105, 4,752/372, and 5,096/518 respectively. These prove transfer of exact dual checking and conservative signature partitioning, not broad performance: the benchmarks are deliberately favorable and their duals are uniform.

## 5. Productive future plan

Flagship target after the benchmarks: **a bounded `C(v,6,4)` record-improvement search on the existing local C(13,6,4) target**, not a new negative theorem. It keeps the verifier and witness channel simple while transferring construction, canonicalization, and immutable verification. It requires Charlie approval before activation.

Days 1–7: package only the frozen dual and residual-reconstruction interfaces; reproduce the three pilots from a clean environment. Days 8–14: add a nonuniform exact-dual benchmark and an independent SAT/DRAT residual benchmark. Days 15–21: demonstrate cross-host segment hash reconciliation without production capacity. Days 22–30: select one target only if all contracts replay cleanly, publication novelty is checked, and a compact witness/certificate path exists. Stop any route whose next tranche has no new independently verified closure per declared budget. Publishable now: schemas, independent checkers, failure archive, and benchmark note; campaign-specific: C frontier binding, ordinary-link catalogue, and active queues.

Reproducibility packet: source-status timestamp and URLs, pinned Python/checker versions, machine-readable input/output manifests, independent checker, failure artifacts including the cached-unit incident, compute/tool disclosure, and a short research note (statement, prior status, method, artifacts, limits, reproduction command).

## Decision memo

* **C status:** 40–41; 33/47 certified extension closures; ordinary classification incomplete.
* **Strongest reusable assets:** hash-bound residual reconstruction, independently checked rational duals, and immutable replayable receipts/segments.
* **Best benchmark:** SQS(8), 518/518 isolated representative cases closed by an independent exact-dual checker.
* **Transferability:** real for certificate plumbing and small covering residuals; not yet demonstrated for hard-tail throughput or global aggregation.
* **Recommended next target:** local `C(13,6,4)` witness-improvement track, subject to approval and benchmark gates.
* **Next experiment:** nonuniform-dual plus SAT/DRAT residual benchmark on SQS(8), clean-machine replay required.
