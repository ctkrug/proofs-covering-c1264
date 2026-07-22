# C(12,6,4) frozen baseline

Source check: 2026-07-22 UTC.

The La Jolla Covering Repository reports `40 <= C(12,6,4) <= 41` and supplies the 41 blocks preserved
in `sources/ljcr-c1264-41.txt`. The maintained successor Covering Repository was also checked for a
later classical improvement; none was listed. This repository treats the range as a current baseline,
not as proof that no unpublished or concurrent result exists.

## Exact size-40 consequences

There are 924 candidate 6-subsets and 495 four-subsets to cover. In a hypothetical 40-block cover:

1. Every point has degree at least `C(11,5,3)=20`; 240 total point incidences force degree exactly 20.
2. Every pair has multiplicity at least `C(10,4,2)=9`; 600 total pair incidences leave six excesses
   above `66 * 9 = 594`.
3. At a point `x`, the 11 incident pair multiplicities sum to `5 * 20 = 100`. Their baseline is 99,
   so exactly one incident pair has multiplicity 10. The six excess pairs therefore form a perfect
   matching and every other pair has multiplicity 9.
4. All 10,395 perfect matchings are equivalent under relabeling. We fix
   `(0,1),(2,3),(4,5),(6,7),(8,9),(10,11)`, a quotient with stabilizer order 46,080.
5. If `r(B)` is the number of complete fixed pairs in a block, `sum r(B)=60`. The root search is the
   disjoint union of: a canonical `r=0` block exists; or no `r=0` block exists and a canonical `r=1`
   block exists.

Block complementation is not an automorphism of the covering constraints and is forbidden as a
symmetry shortcut absent a separate proof.

## Decision artifacts

- Positive: 40 distinct blocks, replayed by an independent all-four-subsets checker.
- Negative: deterministic direct instance, independently checked symmetry/cube coverage, and replayed
  proof logs for every UNSAT leaf, plus the checked 41-block upper-bound control.

Sources:

- https://ljcr.dmgordon.org/cover/show_cover.php?v=12&k=6&t=4
- https://ljcr.dmgordon.org/cover/show_cover.php?v=11&k=5&t=3
- https://ljcr.dmgordon.org/cover/show_cover.php?v=10&k=4&t=2
- https://www.coveringrepository.com/
