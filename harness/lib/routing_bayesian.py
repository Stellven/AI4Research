#!/usr/bin/env python3
"""Bounded offline Gaussian-process optimization for route/config selection."""
from __future__ import annotations
import argparse, hashlib, json, math
from collections import defaultdict
from pathlib import Path
from typing import Any

def _rows(path:Path)->list[dict[str,Any]]:
 rows=[]
 for number,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
  if line.strip():
   row=json.loads(line)
   if not isinstance(row,dict): raise ValueError(f"row {number} is not an object")
   rows.append(row)
 return rows

def _rbf(a:list[float],b:list[float],scale:float)->float:
 return math.exp(-.5*sum((x-y)**2 for x,y in zip(a,b))/(scale*scale))

def _chol(matrix:list[list[float]])->list[list[float]]:
 n=len(matrix); lower=[[0.0]*n for _ in range(n)]
 for i in range(n):
  for j in range(i+1):
   value=matrix[i][j]-sum(lower[i][k]*lower[j][k] for k in range(j))
   if i==j:
    if value<=1e-12: raise ValueError("gaussian_process_kernel_not_positive_definite")
    lower[i][j]=math.sqrt(value)
   else: lower[i][j]=value/lower[j][j]
 return lower

def _solve(lower:list[list[float]],values:list[float])->list[float]:
 n=len(values); forward=[0.0]*n; result=[0.0]*n
 for i in range(n): forward[i]=(values[i]-sum(lower[i][j]*forward[j] for j in range(i)))/lower[i][i]
 for i in range(n-1,-1,-1): result[i]=(forward[i]-sum(lower[j][i]*result[j] for j in range(i+1,n)))/lower[i][i]
 return result

def _posterior(xs:list[list[float]],ys:list[float],point:list[float],scale:float,noise:float)->tuple[float,float]:
 kernel=[[_rbf(a,b,scale)+(noise*noise if i==j else 0.0) for j,b in enumerate(xs)] for i,a in enumerate(xs)]
 lower=_chol(kernel); cross=[_rbf(x,point,scale) for x in xs]
 alpha=_solve(lower,ys); projected=_solve(lower,cross)
 mean=sum(a*y for a,y in zip(cross,alpha)); variance=max(0.0,1.0-sum(a*b for a,b in zip(cross,projected)))
 return mean,math.sqrt(variance)

def evaluate(path:Path,baseline:str,cost_weight:float,latency_weight:float,max_cost:float,beta:float,length_scale:float,noise:float,max_uncertainty:float)->dict[str,Any]:
 rows=_rows(path); errors=[]
 train=[r for r in rows if r.get("split")=="train"]; hold=[r for r in rows if r.get("split")=="holdout"]
 if not train or not hold or len(train)+len(hold)!=len(rows): errors.append("train_and_holdout_required")
 train_ctx={str(r.get("context_id") or "") for r in train}; hold_ctx={str(r.get("context_id") or "") for r in hold}
 if "" in train_ctx|hold_ctx or train_ctx&hold_ctx: errors.append("train_holdout_context_contamination")
 if beta<0 or length_scale<=0 or noise<=0 or max_uncertainty<=0: errors.append("invalid_surrogate_parameters")
 obs=defaultdict(list); configs={}
 for row in train:
  try:
   arm=str(row["arm"]); raw=row["config"]
   if not isinstance(raw,dict) or not raw: raise ValueError
   config={str(k):float(v) for k,v in raw.items()}
   if arm in configs and configs[arm]!=config: errors.append(f"inconsistent_config:{arm}")
   configs[arm]=config
   obs[arm].append((float(row["reward"]),float(row["cost_usd"]),float(row["latency_ms"]),bool(row["success"])))
  except (KeyError,TypeError,ValueError): errors.append("invalid_training_observation")
 names=sorted(next(iter(configs.values()))) if configs else []
 if any(sorted(c)!=names for c in configs.values()): errors.append("inconsistent_config_features")
 if baseline not in obs or len(obs)<2: errors.append("baseline_and_candidate_arms_required")
 if any(len(values)<2 for values in obs.values()): errors.append("at_least_two_observations_per_arm_required")
 stats={}; xs=[]; ys=[]
 if not errors:
  for arm,values in obs.items():
   n=len(values); reward=sum(v[0] for v in values)/n; cost=sum(v[1] for v in values)/n; latency=sum(v[2] for v in values)/n; success=sum(v[3] for v in values)/n
   utility=reward-cost_weight*cost-latency_weight*latency/1000.0
   xs.append([configs[arm][name] for name in names]);ys.append(utility)
   stats[arm]={"samples":n,"config":configs[arm],"mean_reward":reward,"mean_cost_usd":cost,"mean_latency_ms":latency,"success_rate":success,"observed_utility":utility,"within_cost_budget":cost<=max_cost}
  for arm,point in zip(obs,xs):
   mean,std=_posterior(xs,ys,point,length_scale,noise);stats[arm].update({"posterior_mean_utility":mean,"posterior_stddev":std,"acquisition_gp_ucb":mean+beta*std})
 eligible={a:s for a,s in stats.items() if s["within_cost_budget"] and s["posterior_stddev"]<=max_uncertainty}
 selected=max(eligible,key=lambda a:eligible[a]["acquisition_gp_ucb"]) if eligible else ""
 if not eligible: errors.append("no_budget_and_uncertainty_eligible_candidate")
 elif selected==baseline: errors.append("no_candidate_selected")
 paired=defaultdict(dict)
 for row in hold: paired[str(row.get("context_id"))][str(row.get("arm"))]=row
 deltas=[]
 if selected:
  for ctx,values in paired.items():
   if baseline not in values or selected not in values: errors.append(f"unpaired_holdout:{ctx}");continue
   try:
    def utility(row): return float(row["reward"])-cost_weight*float(row["cost_usd"])-latency_weight*float(row["latency_ms"])/1000.0
    deltas.append({"context_id":ctx,"utility_delta":utility(values[selected])-utility(values[baseline]),"selected_success":bool(values[selected]["success"]),"baseline_success":bool(values[baseline]["success"])})
   except (KeyError,TypeError,ValueError): errors.append(f"invalid_holdout_observation:{ctx}")
 mean_delta=sum(x["utility_delta"] for x in deltas)/len(deltas) if deltas else 0.0
 regressions=[x["context_id"] for x in deltas if x["baseline_success"] and not x["selected_success"]]
 if not deltas or mean_delta<=0: errors.append("no_positive_holdout_utility")
 if regressions: errors.append("holdout_success_regression")
 errors=list(dict.fromkeys(errors)); accepted=not errors
 return {"schema_version":"solar.routing_bayesian_evaluation.v1","status":"accepted" if accepted else "rejected","algorithm":"bounded_gaussian_process_ucb","source":{"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"rows":len(rows)},"surrogate":{"kernel":"rbf","feature_names":names,"length_scale":length_scale,"observation_noise":noise,"acquisition":"gp_ucb","beta":beta,"max_selected_posterior_stddev":max_uncertainty},"policy":{"baseline_arm":baseline,"selected_arm":selected,"cost_weight":cost_weight,"latency_weight":latency_weight,"max_mean_cost_usd":max_cost,"deployment_authorized":False},"training_arm_stats":stats,"holdout":{"paired_contexts":len(deltas),"mean_utility_delta":mean_delta,"success_regressions":regressions,"deltas":deltas},"rollback":f"restore routing arm {baseline}","errors":errors,"limitations":["This is bounded offline Gaussian-process optimization, not online reinforcement learning.","Acceptance is limited to the hash-addressed trace and never authorizes automatic deployment."]}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("evaluate",nargs="?");ap.add_argument("--traces",required=True,type=Path);ap.add_argument("--baseline-arm",required=True);ap.add_argument("--cost-weight",type=float,default=1.0);ap.add_argument("--latency-weight",type=float,default=.1);ap.add_argument("--max-mean-cost-usd",type=float,default=1.0);ap.add_argument("--beta",type=float,default=.2);ap.add_argument("--length-scale",type=float,default=1.0);ap.add_argument("--noise",type=float,default=.05);ap.add_argument("--max-selected-uncertainty",type=float,default=.25);ap.add_argument("--output",required=True,type=Path);a=ap.parse_args()
 try:r=evaluate(a.traces.resolve(),a.baseline_arm,a.cost_weight,a.latency_weight,a.max_mean_cost_usd,a.beta,a.length_scale,a.noise,a.max_selected_uncertainty)
 except Exception as error:r={"schema_version":"solar.routing_bayesian_evaluation.v1","status":"rejected","errors":[str(error)]}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8");print(json.dumps(r));return 0 if r.get("status")=="accepted" else 2
if __name__=="__main__": raise SystemExit(main())
