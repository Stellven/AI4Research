#!/usr/bin/env python3
"""Train and holdout-evaluate a provenance-preserving linear reranker."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from typing import Any

FEATURES=("term_overlap","citation_match","authority","freshness")
def rows(path:Path)->list[dict[str,Any]]:
 out=[]
 for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
  if line.strip():
   x=json.loads(line)
   if not isinstance(x,dict):raise ValueError(f'row {n} not object')
   out.append(x)
 return out
def dcg(rels:list[float])->float:return sum((2**r-1)/math.log2(i+2) for i,r in enumerate(rels))
def evaluate(path:Path,k:int)->dict[str,Any]:
 data=rows(path);err=[];train=[x for x in data if x.get('split')=='train'];hold=[x for x in data if x.get('split')=='holdout']
 if not train or not hold or len(train)+len(hold)!=len(data):err.append('train_and_holdout_required')
 tq={str(x.get('query_id') or '') for x in train};hq={str(x.get('query_id') or '') for x in hold}
 if '' in tq|hq or tq&hq:err.append('train_holdout_query_contamination')
 for x in data:
  if not x.get('document_id') or not x.get('provenance_id') or not isinstance(x.get('relevance'),(int,float)):err.append('missing_identity_provenance_or_label');break
 pos=[x for x in train if float(x.get('relevance',0))>0];neg=[x for x in train if float(x.get('relevance',0))<=0]
 if not pos or not neg:err.append('positive_and_negative_labels_required')
 weights={f:(sum(float(x.get('features',{}).get(f,0)) for x in pos)/len(pos) if pos else 0)-(sum(float(x.get('features',{}).get(f,0)) for x in neg)/len(neg) if neg else 0) for f in FEATURES}
 scale=sum(abs(v) for v in weights.values()) or 1;weights={f:v/scale for f,v in weights.items()}
 byq={}
 for x in hold:byq.setdefault(str(x['query_id']),[]).append(x)
 per=[];base_recall=rerank_recall=base_ndcg=rerank_ndcg=0.0;prov=True
 for q,docs in byq.items():
  relevant=sum(float(x['relevance'])>0 for x in docs);top=lambda seq:seq[:min(k,len(seq))]
  base=top(sorted(docs,key=lambda x:float(x.get('base_score',0)),reverse=True));rerank=top(sorted(docs,key=lambda x:sum(weights[f]*float(x.get('features',{}).get(f,0)) for f in FEATURES),reverse=True))
  br=sum(float(x['relevance'])>0 for x in base)/relevant if relevant else 0;rr=sum(float(x['relevance'])>0 for x in rerank)/relevant if relevant else 0
  ideal=dcg(sorted([float(x['relevance']) for x in docs],reverse=True)[:k]) or 1;bn=dcg([float(x['relevance']) for x in base])/ideal;rn=dcg([float(x['relevance']) for x in rerank])/ideal
  base_recall+=br;rerank_recall+=rr;base_ndcg+=bn;rerank_ndcg+=rn;prov &= all(x.get('provenance_id') for x in rerank);per.append({'query_id':q,'base_recall_at_k':br,'rerank_recall_at_k':rr,'base_ndcg_at_k':bn,'rerank_ndcg_at_k':rn,'reranked_document_ids':[x['document_id'] for x in rerank],'provenance_ids':[x['provenance_id'] for x in rerank]})
 n=len(byq) or 1;metrics={'query_count':len(byq),'k':k,'base_recall_at_k':base_recall/n,'rerank_recall_at_k':rerank_recall/n,'base_ndcg_at_k':base_ndcg/n,'rerank_ndcg_at_k':rerank_ndcg/n,'recall_delta':(rerank_recall-base_recall)/n,'ndcg_delta':(rerank_ndcg-base_ndcg)/n,'provenance_preserved':prov}
 if metrics['recall_delta']<0 or metrics['ndcg_delta']<=0:err.append('holdout_quality_not_improved')
 if not prov:err.append('reranked_result_missing_provenance')
 ok=not err
 return {'schema_version':'solar.retrieval_reranker.v1','status':'accepted' if ok else 'rejected','source':{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':len(data)},'model':{'type':'linear_pairwise_mean_difference','features':list(FEATURES),'weights':weights},'metrics':metrics,'queries':per,'promotion':{'promoted':ok,'rollback':'disable learned reranker and restore base_score ordering'},'errors':err,'limitations':['This is a small supervised linear reranker, not neural reranker fine-tuning or Self-RAG.','Metrics apply only to the hash-bound labeled holdout corpus.']}
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('train',nargs='?');ap.add_argument('--dataset',required=True,type=Path);ap.add_argument('--k',type=int,default=1);ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
 try:r=evaluate(a.dataset.resolve(),a.k)
 except Exception as e:r={'schema_version':'solar.retrieval_reranker.v1','status':'rejected','errors':[str(e)]}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(r));return 0 if r.get('status')=='accepted' else 2
if __name__=='__main__':raise SystemExit(main())
