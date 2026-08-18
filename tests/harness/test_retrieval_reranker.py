import json
from pathlib import Path
from harness.lib.retrieval_reranker import evaluate
def write(p,rs):p.write_text(''.join(json.dumps(x)+'\n' for x in rs));return p
def data():
 def r(s,q,d,rel,b,o,c,a):return {'split':s,'query_id':q,'document_id':d,'provenance_id':'p-'+d,'relevance':rel,'base_score':b,'features':{'term_overlap':o,'citation_match':c,'authority':a,'freshness':.5}}
 return [r('train','t','tp',1,.1,1,1,1),r('train','t','tn',0,.9,.1,0,.1),r('holdout','h','hp',1,.1,1,1,1),r('holdout','h','hn',0,.9,.1,0,.1)]
def test_improves(tmp_path):assert evaluate(write(tmp_path/'d',data()),1)['status']=='accepted'
def test_contamination(tmp_path):
 x=data();x[2]['query_id']='t';x[3]['query_id']='t';assert 'train_holdout_query_contamination' in evaluate(write(tmp_path/'d',x),1)['errors']
def test_provenance(tmp_path):
 x=data();x[2]['provenance_id']='';assert evaluate(write(tmp_path/'d',x),1)['status']=='rejected'
def test_no_improvement(tmp_path):
 x=data();x[2]['base_score']=1;x[3]['base_score']=0;assert evaluate(write(tmp_path/'d',x),1)['status']=='rejected'
