#!/usr/bin/env python3
import argparse
from pathlib import Path
import json

parser = argparse.ArgumentParser()
parser.add_argument('--experiment-id', required=True)
parser.add_argument('--marker', required=True)
args = parser.parse_args()
Path(args.marker).write_text('parity executed', encoding='utf-8')
payload = {
    'schema': 'experiment_result.v1',
    'status': 'completed',
    'outputs': {
        'result': {
            'experiment_id': args.experiment_id,
            'outcome': 'supports',
            'metrics': [{'name': 'f1', 'value': 0.92}],
            'evidence_ids': ['runtime:exp-parity'],
            'logs': ['parity local command executed'],
        }
    },
}
print(json.dumps(payload))