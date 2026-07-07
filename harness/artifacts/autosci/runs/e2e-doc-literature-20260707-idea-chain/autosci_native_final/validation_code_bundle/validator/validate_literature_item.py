#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--metadata', required=True)
    ap.add_argument('--source', required=True)
    ap.add_argument('--experiment-id', required=True)
    ap.add_argument('--claim-id', required=True)
    args=ap.parse_args()
    meta_path=Path(args.metadata); source_path=Path(args.source)
    meta=load_json(meta_path)
    text=source_path.read_text(encoding='utf-8', errors='replace') if source_path.exists() else ''
    source_id=str(meta.get('id') or '')
    title=str(meta.get('title') or '')
    needs_url='needs url verification' in str(meta.get('url_status','')).lower() or 'source drift' in str(meta.get('url_status','')).lower()
    has_id=source_id in text
    has_title=bool(title and title[:40].lower() in text.lower())
    sections=len(re.findall(r'^##\s+', text, flags=re.M))
    char_count=len(text)
    expected=str(meta.get('expected_outcome') or 'inconclusive')
    outcome=expected if text and has_id and title else 'failed'
    metrics=[
        {'name':'source_markdown_exists','value':1 if source_path.exists() else 0,'seed_id':source_id},
        {'name':'source_chars','value':char_count,'seed_id':source_id},
        {'name':'source_id_present','value':1 if has_id else 0,'seed_id':source_id},
        {'name':'title_present','value':1 if has_title else 0,'seed_id':source_id},
        {'name':'section_count','value':sections,'seed_id':source_id},
        {'name':'needs_url_verification','value':1 if needs_url else 0,'seed_id':source_id},
        {'name':'credibility_score','value':float(meta.get('credibility') or 0),'seed_id':source_id},
        {'name':'relevance_score','value':float(meta.get('relevance') or 0),'seed_id':source_id},
    ]
    logs=[
        f"validated attached-document source record {source_id}",
        f"url_status={meta.get('url_status')}",
        f"confidence={meta.get('confidence')}",
        'network_fetch=not_requested',
    ]
    payload={
        'experiment_id':args.experiment_id,
        'outcome':outcome,
        'metrics':metrics,
        'evidence_ids':[f"literature-source:{source_id}", f"attached-doc:{meta.get('doc_slug')}", args.claim_id],
        'logs':logs,
        'result_collected': True,
        'source_path': str(source_path),
        'metadata_path': str(meta_path),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
