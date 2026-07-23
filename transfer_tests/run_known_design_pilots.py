#!/usr/bin/env python3
"""Small, isolated transfer benchmarks.  No C(12,6,4) artifact is read."""
from __future__ import annotations
import itertools, json, hashlib
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'transfer_tests'/'results.json'
DESIGNS={
 'fano_s2_3_7':(7,3,2,[(0,1,2),(0,3,4),(0,5,6),(1,3,5),(1,4,6),(2,3,6),(2,4,5)]),
 'affine_s2_3_9':(9,3,2,[(0,3,6),(1,4,7),(2,5,8),(0,5,7),(1,3,8),(2,4,6),(0,4,8),(1,5,6),(2,3,7),(0,1,2),(3,4,5),(6,7,8)]),
 'sqs_s3_4_8':(8,4,3,None)}
def sub(b,t): return set(itertools.combinations(sorted(b),t))
def sha(o): return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def run(name, d):
 v,k,t,raw=d
 # The 14 affine planes of F_2^3: an independently recognisable S(3,4,8).
 if raw is None:
  raw=sorted({tuple(sorted({a,a^u,a^v,a^u^v})) for a in range(8) for u in range(1,8) for v in range(u+1,8) if u!=v})
 blocks=[frozenset(x) for x in raw]; universe=set(itertools.combinations(range(v),t)); allb=[frozenset(x) for x in itertools.combinations(range(v),k)]
 assert set().union(*(sub(b,t) for b in blocks))==universe
 # two omitted correct blocks, then one deliberately non-design block is spent; one slot remains.
 cases=[]
 for i,j in itertools.combinations(range(len(blocks)),2):
  omitted=(blocks[i],blocks[j]); residual=sub(omitted[0],t)|sub(omitted[1],t)
  reps={}
  for x in allb:
   if x in blocks: continue
   key=tuple(sorted((len(x&omitted[0]),len(x&omitted[1]))))
   reps.setdefault(key,x)
  for key,x in reps.items():
   left=residual-sub(x,t)
   max_cover=max(len(left&sub(y,t)) for y in allb)
   lower=Fraction(len(left),max_cover) if max_cover else Fraction(10**9,1)
   cases.append({'omitted':[i,j],'orbit_signature':key,'candidate':sorted(x),'uncovered':len(left),'dual_lower':[lower.numerator,lower.denominator],'closed_by_weighted_dual':lower>1,'zero_child':max_cover==0})
 closed=sum(x['closed_by_weighted_dual'] for x in cases)
 return {'name':name,'parameters':{'v':v,'k':k,'t':t,'known_size':len(blocks)},'design_blocks':[sorted(x) for x in blocks],'all_tsets':len(universe),'two_omission_cases':len(cases),'symmetry_representatives':len(cases),'naive_wrong_children':sum(1 for _ in itertools.combinations(blocks,2))*(len(allb)-len(blocks)),'weighted_closed':closed,'weighted_closed_fraction':[closed,len(cases)],'zero_child_contradictions':sum(x['zero_child'] for x in cases),'certificate_kind':'uniform rational LP-dual: each uncovered t-set has weight 1/max_block_coverage','cases':cases}
def main():
 out={'schema':1,'scope':'isolated known-ground-truth transfer tests; no C(12,6,4) receipts consumed','pilots':[run(n,d) for n,d in DESIGNS.items()]}; out['sha256_without_hash']=sha(out); OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print(OUT)
if __name__=='__main__': main()
