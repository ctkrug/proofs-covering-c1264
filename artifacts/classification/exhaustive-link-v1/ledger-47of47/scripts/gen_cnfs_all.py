import sys, json, hashlib, argparse
from pathlib import Path
WT=Path("/Users/Krug/.codex/worktrees/c1264-canonical-import-v2")
sys.path.insert(0,str(WT/"scripts"))
import run_cardinality_encoding_benchmark as shared

ap=argparse.ArgumentParser()
ap.add_argument("--blocker",required=True)
ap.add_argument("--outdir",required=True)
ap.add_argument("--nodes",default="")
ap.add_argument("--any-status",dest="any_status",action="store_true")
a=ap.parse_args()

man=json.loads((WT/"artifacts/portfolio/frontier-manifest-v1.json").read_text())
open_nodes=[n for n in man["nodes"]] if a.any_status else [n for n in man["nodes"] if n["final_coverage_status"]=="open"]
if a.nodes:
    want=set(a.nodes.split(","))
    open_nodes=[n for n in open_nodes if n["id"] in want]
blocker=Path(a.blocker)
outdir=Path(a.outdir); outdir.mkdir(parents=True,exist_ok=True)
idx={"blocker":str(blocker),"blocker_sha256":hashlib.sha256(blocker.read_bytes()).hexdigest(),"nodes":[]}
for n in open_nodes:
    leaf={k:n[k] for k in ("id","root_index","secondary_index","tertiary_index")}
    cnf,rec=shared.build_cnf(blocker,leaf,"sequential")
    p=outdir/f"{n['id']}.cnf"
    cnf.to_file(str(p))
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    idx["nodes"].append({"id":n["id"],"kind":n["kind"],"root_index":n["root_index"],
        "secondary_index":n["secondary_index"],"tertiary_index":n["tertiary_index"],
        "inherited_result_sha256":n["inherited_result_sha256"],
        "cnf":str(p),"cnf_sha256":h,"vars":cnf.nv,"clauses":len(cnf.clauses),
        "non_cardinality_core_sha256":rec["non_cardinality_core_sha256"]})
    print(n["id"],h[:16],cnf.nv,len(cnf.clauses),flush=True)
(outdir/"index.json").write_text(json.dumps(idx,indent=2,sort_keys=True)+"\n")
print("wrote",outdir/"index.json")
