#!/usr/bin/env python3
"""Independent small checker: recalculates coverage and every claimed rational dual."""
from __future__ import annotations
import itertools,json,sys
from fractions import Fraction
from pathlib import Path
def ts(b,t): return set(itertools.combinations(sorted(b),t))
def main(p):
 data=json.loads(Path(p).read_text())
 for q in data['pilots']:
  v,k,t=(q['parameters'][z] for z in ('v','k','t')); B=[frozenset(x) for x in q['design_blocks']]; U=set(itertools.combinations(range(v),t)); A=[frozenset(x) for x in itertools.combinations(range(v),k)]
  if set().union(*(ts(b,t) for b in B)) != U: raise SystemExit(q['name']+' bad witness')
  closed=zero=0
  for c in q['cases']:
   i,j=c['omitted']; x=frozenset(c['candidate']); R=ts(B[i],t)|ts(B[j],t); L=R-ts(x,t); m=max(len(L&ts(y,t)) for y in A); f=Fraction(len(L),m) if m else Fraction(10**9)
   if [f.numerator,f.denominator]!=c['dual_lower'] or (f>1)!=c['closed_by_weighted_dual']: raise SystemExit(q['name']+' bad dual')
   closed+=f>1; zero+=m==0
  if closed!=q['weighted_closed'] or zero!=q['zero_child_contradictions']: raise SystemExit(q['name']+' bad totals')
 print('VALID',len(data['pilots']),'isolated pilots')
if __name__=='__main__': main(sys.argv[1])
