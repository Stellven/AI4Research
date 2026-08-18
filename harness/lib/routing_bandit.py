#!/usr/bin/env python3
"""Offline cost-aware UCB routing policy evaluator."""
from __future__ import annotations
import argparse, hashlib, json, math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _rows(path: Path) -> list[dict[str, Any]]:
    rows=[]
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if line.strip():
            row=json.loads(line)
            if not isinstance(row,dict): raise ValueError(f"row {n} is not an object")
            rows.append(row)
    return rows


def evaluate(path: Path, baseline: str, cost_weight: float, latency_weight: float, max_cost: float, exploration: float) -> dict[str,Any]:
    rows=_rows(path); errors=[]
    train=[r for r in rows if r.get("split")=="train"]; hold=[r for r in rows if r.get("split")=="holdout"]
    if not train or not hold or len(train)+len(hold)!=len(rows): errors.append("train_and_holdout_required")
    train_ctx={str(r.get("context_id") or "") for r in train}; hold_ctx={str(r.get("context_id") or "") for r in hold}
    if "" in train_ctx|hold_ctx or train_ctx&hold_ctx: errors.append("train_holdout_context_contamination")
    arms=defaultdict(list)
    for r in train:
        try: arms[str(r["arm"])].append((float(r["reward"]),float(r["cost_usd"]),float(r["latency_ms"]),bool(r["success"])))
        except (KeyError,TypeError,ValueError): errors.append("invalid_training_observation")
    if baseline not in arms or len(arms)<2: errors.append("baseline_and_candidate_arms_required")
    total=max(1,sum(map(len,arms.values()))); stats={}
    for arm,obs in arms.items():
        n=len(obs); reward=sum(x[0] for x in obs)/n; cost=sum(x[1] for x in obs)/n; latency=sum(x[2] for x in obs)/n; success=sum(x[3] for x in obs)/n
        utility=reward-cost_weight*cost-latency_weight*(latency/1000.0); ucb=utility+exploration*math.sqrt(math.log(total+1)/n)
        stats[arm]={"samples":n,"mean_reward":reward,"mean_cost_usd":cost,"mean_latency_ms":latency,"success_rate":success,"utility":utility,"ucb_score":ucb,"within_cost_budget":cost<=max_cost}
    eligible={a:s for a,s in stats.items() if s["within_cost_budget"]}
    selected=max(eligible,key=lambda a:eligible[a]["ucb_score"]) if eligible else ""
    paired=defaultdict(dict)
    for r in hold: paired[str(r.get("context_id"))][str(r.get("arm"))]=r
    deltas=[]
    for ctx,values in paired.items():
        if baseline not in values or selected not in values: errors.append(f"unpaired_holdout:{ctx}"); continue
        def util(r): return float(r["reward"])-cost_weight*float(r["cost_usd"])-latency_weight*(float(r["latency_ms"])/1000.0)
        deltas.append({"context_id":ctx,"utility_delta":util(values[selected])-util(values[baseline]),"cost_delta_usd":float(values[selected]["cost_usd"])-float(values[baseline]["cost_usd"]),"latency_delta_ms":float(values[selected]["latency_ms"])-float(values[baseline]["latency_ms"]),"selected_success":bool(values[selected]["success"]),"baseline_success":bool(values[baseline]["success"])})
    mean_delta=sum(x["utility_delta"] for x in deltas)/len(deltas) if deltas else 0.0
    regressions=[x["context_id"] for x in deltas if x["baseline_success"] and not x["selected_success"]]
    if selected in {"",baseline}: errors.append("no_candidate_selected")
    if not deltas or mean_delta<=0: errors.append("no_positive_holdout_utility")
    if regressions: errors.append("holdout_success_regression")
    accepted=not errors
    return {"schema_version":"solar.routing_bandit_evaluation.v1","status":"accepted" if accepted else "rejected","algorithm":"offline_cost_aware_ucb1","source":{"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"rows":len(rows)},"policy":{"baseline_arm":baseline,"selected_arm":selected,"cost_weight":cost_weight,"latency_weight":latency_weight,"max_mean_cost_usd":max_cost,"exploration":exploration},"training_arm_stats":stats,"holdout":{"paired_contexts":len(deltas),"mean_utility_delta":mean_delta,"success_regressions":regressions,"deltas":deltas},"rollback":f"restore routing arm {baseline}","errors":errors,"limitations":["This is offline UCB replay, not Bayesian optimization or cost-aware reinforcement learning.","Acceptance is bounded to the hash-addressed trace and does not authorize automatic online deployment."]}


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("evaluate",nargs="?"); ap.add_argument("--traces",required=True,type=Path); ap.add_argument("--baseline-arm",required=True); ap.add_argument("--cost-weight",type=float,default=1.0); ap.add_argument("--latency-weight",type=float,default=.1); ap.add_argument("--max-mean-cost-usd",type=float,default=1.0); ap.add_argument("--exploration",type=float,default=.2); ap.add_argument("--output",required=True,type=Path); a=ap.parse_args()
    try:r=evaluate(a.traces.resolve(),a.baseline_arm,a.cost_weight,a.latency_weight,a.max_mean_cost_usd,a.exploration)
    except Exception as e:r={"schema_version":"solar.routing_bandit_evaluation.v1","status":"rejected","errors":[str(e)]}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8"); print(json.dumps(r)); return 0 if r.get("status")=="accepted" else 2
if __name__=="__main__": raise SystemExit(main())
