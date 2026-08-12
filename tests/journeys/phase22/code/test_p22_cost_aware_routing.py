import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

def test_p22_cost_aware_routing(repo_root:Path,tmp_path:Path)->None:
 run_id='p22-routing-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); out=repo_root/'outputs'/'phase22-real-journeys'/run_id;out.mkdir(parents=True)
 rows=[]
 for arm,reward,cost,latency in [('base',.60,.30,900),('candidate',.82,.18,550)]:
  for i in range(3):rows.append({'split':'train','context_id':f't-{arm}-{i}','arm':arm,'reward':reward,'cost_usd':cost,'latency_ms':latency,'success':True})
 for i in range(2):
  rows += [{'split':'holdout','context_id':f'h-{i}','arm':'base','reward':.58,'cost_usd':.31,'latency_ms':920,'success':True},{'split':'holdout','context_id':f'h-{i}','arm':'candidate','reward':.80,'cost_usd':.19,'latency_ms':580,'success':True}]
 traces=out/'routing-traces.jsonl';traces.write_text(''.join(json.dumps(x)+'\n' for x in rows),encoding='utf-8'); result=out/'routing-evaluation.json'; tool=repo_root/'harness/lib/routing_bandit.py'
 proc=subprocess.run([sys.executable,str(tool),'evaluate','--traces',str(traces),'--baseline-arm','base','--cost-weight','1','--latency-weight','.1','--max-mean-cost-usd','.5','--exploration','.1','--output',str(result)],text=True,capture_output=True,timeout=30)
 data=json.loads(result.read_text(encoding='utf-8')); assertions={'cli_accepted':proc.returncode==0 and data['status']=='accepted','candidate_selected':data['policy']['selected_arm']=='candidate','cost_budget_met':data['training_arm_stats']['candidate']['within_cost_budget'],'paired_holdout_positive':data['holdout']['paired_contexts']==2 and data['holdout']['mean_utility_delta']>0,'no_success_regression':not data['holdout']['success_regressions'],'rollback_recorded':data['rollback']=='restore routing arm base'}
 evidence={'schema_version':'phase22.cost_aware_routing.v1','journey_id':'NT-optimization-routing','run_id':run_id,'repo_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo_root,text=True).strip(),'production_entrypoint':str(tool),'command_exit_code':proc.returncode,'result':str(result),'assertions':assertions,'status':'PASS_WITH_KNOWN_LIMITATIONS' if all(assertions.values()) else 'FAIL','limitations':data['limitations']};(out/'journey-result.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8');assert all(assertions.values()),out/'journey-result.json'
