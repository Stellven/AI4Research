import json
from pathlib import Path
from harness.lib.routing_bandit import evaluate

def write(p:Path,rows:list[dict])->Path:p.write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8");return p
def rows():
 return [{"split":"train","context_id":"t1","arm":"base","reward":.6,"cost_usd":.3,"latency_ms":900,"success":True},{"split":"train","context_id":"t2","arm":"candidate","reward":.8,"cost_usd":.2,"latency_ms":600,"success":True},{"split":"holdout","context_id":"h1","arm":"base","reward":.5,"cost_usd":.3,"latency_ms":900,"success":True},{"split":"holdout","context_id":"h1","arm":"candidate","reward":.8,"cost_usd":.2,"latency_ms":600,"success":True}]
def test_accepts_better_cost_aware_arm(tmp_path):
 r=evaluate(write(tmp_path/'x',rows()),'base',1,.1,1,.1);assert r['status']=='accepted' and r['policy']['selected_arm']=='candidate'
def test_rejects_contamination(tmp_path):
 x=rows();x[2]['context_id']='t1';x[3]['context_id']='t1';r=evaluate(write(tmp_path/'x',x),'base',1,.1,1,.1);assert 'train_holdout_context_contamination' in r['errors']
def test_rejects_cost_budget(tmp_path):
 x=rows();x[1]['cost_usd']=2;r=evaluate(write(tmp_path/'x',x),'base',1,.1,.5,.1);assert r['status']=='rejected'
def test_rejects_success_regression(tmp_path):
 x=rows();x[3]['success']=False;r=evaluate(write(tmp_path/'x',x),'base',1,.1,1,.1);assert 'holdout_success_regression' in r['errors']
