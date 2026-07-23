# Slack-chain discriminator and verification plan

## Recommendation

Run the proposed temporary-point-degree-slack route, but make one proposal a
**four-exchange token cycle**, not a two- or three-exchange chain.  Start from
the hash-bound six-defect 40-block warm start
`4321dea0f828f30bf5cb1d3c54b4a94349e9bc3f54bd25ea23dbac79ae030a07`.
Each elementary exchange replaces `B` by a nonselected block obtained by
replacing exactly one point: it changes the degree vector by `-e_a+e_b`.
Choose a directed four-cycle `a→b→c→d→a`, with distinct points, and make the
successive exchanges carry the unique +1 token.  Thus every intermediate has
L1 degree deviation exactly 2; the endpoint has 40 blocks and all degrees 20.
Require four distinct removals and additions, no cancellation, an endpoint
different from the start, and at least one final added block covering a
quadruple missing at chain start.  Reject endpoints containing an exact
one-, two-, or three-block degree-preserving subtrade.

This is a material new sampler, not a repeat of the blocked exact-degree
screen: it has temporary off-fibre states and endpoints of genuine
four-block distance.  Two exchanges would merely form a two-block exact
trade; three can end in the already sampled exact three-block neighborhood.
The prior screen (20 seeds, 200,000 proposals) was validly replayed but never
beat six defects, so its generator/temperature/basin must not be reused as
the treatment.

## Cheapest discriminator

After unit and semantic gates, run exactly two fixed seeds (126480, 126481),
1,000 chain attempts each, with a 10-second inclusive cap per seed.
Persistent-state acceptance and best-candidate scoring occur only at exact
endpoints using the existing lexicographic defect/pair score.  Record all
generated complete chains, including rejected endpoint score decisions;
failed partial chains are counted by explicit reason.  The treatment passes
only if an independently replayed exact endpoint has at most five uncovered
quadruples.  A zero-defect endpoint is only a witness candidate and must pass
the separate all-495 direct cover checker.

The matched control is the previous exact-degree sampler, unchanged except
for seeds, with the same two seeds, 1,000 scored proposals, endpoint score,
and wall cap.  It is a calibration control, not a retest of its already
negative 20-seed conclusion.  Report completed-chain rate, nontrivial exact
return rate, distinct endpoint hashes, and best defect count for both arms.
No return, a return rate below 1% (fewer than 20 in 2,000 attempts), or no
audited endpoint below six stops the route; do not scale it.  A 5-defect
return permits only a fresh, predeclared scaled screen; a 0-defect return
switches immediately to witness verification.

## Independent verification

Write a new checker, not an extension that imports producer helpers.  It must
reconstruct the 924 blocks and all 495 quadruple counters by direct
combinations; hash-bind source, producer, checker, manifest, trace, and every
candidate.  Replay each elementary exchange and check: selected/unselected
membership; one-point replacement (intersection 5); block count 40; exact
degree vector at endpoints; L1=2 and exactly one +1/one -1 at intermediates;
the declared token transition; distinct/no-cancellation rules; endpoint
subtrade exclusion by exhaustive proper subsets; independently recomputed
metrics; and hash-chain order.  The checker must recompute the target-missing
quadruple from the pre-chain state, rather than trusting a trace field.

Controls: (1) the pinned 41-block Gordon/Nurmela--Östergård cover must cover
all 495 quadruples; (2) its specified one-block deletion must fail; (3) a
synthetic valid four-cycle trace must replay; (4) four mutation tests must be
rejected: altered intermediate degree, a selected addition, a wrong token
edge, and a fake exact endpoint.  Finally apply an independent label
permutation to any zero-defect candidate and directly recheck both labels.

## Efficiency and failure modes

There are 924 six-subsets.  A naive four-addition space has
`C(924,4)=30,175,396,251` choices; the safe proposal reduction is structural,
not a completeness claim: each elementary step has at most 36 one-point
neighbors.  The warm start empirically has all `40×6×6=1,440` first exchanges
available, and each of its six uncovered quadruples has 36 available targeted
additions.  Generate on demand, use integer block IDs/bitmasks, update only
the 15 affected quadruple and pair counters per block, and keep current
coverage incidence arrays.  No symmetry quotient is safe for a single fixed
labelled warm start unless its stabilizer is computed and independently
checked; defer it.  No solver state, batching, or compression is needed at
this 2,000-chain gate; write compact JSONL IDs plus periodic snapshots.

Likely failures are a chain that secretly never leaves the exact fibre,
endpoints that reduce to prior two/three-block trades, biased generation that
always targets the same missing quadruple, incremental-counter drift, and
confusing a heuristic miss with an exclusion.  The above trace replay,
subtrade check, per-target histogram, periodic full recomputation, and stated
stop rule address these.  The Sol principal should reject any claimed advance
without the new independent checker receipt, the matched-control report, and
direct verification of an endpoint below six.

Source: https://ljcr.dmgordon.org/cover/show_cover.php?v=12&k=6&t=4 (retrieved
2026-07-23: 40 <= C(12,6,4) <= 41; page identifies the 41-cover construction
as Nurmela and Östergård simulated annealing).
