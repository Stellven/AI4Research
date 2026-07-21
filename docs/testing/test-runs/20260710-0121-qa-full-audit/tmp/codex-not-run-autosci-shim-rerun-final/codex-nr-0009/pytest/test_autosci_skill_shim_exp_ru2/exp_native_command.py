#!/usr/bin/env python3
import argparse
from pathlib import Path
import json

parser = argparse.ArgumentParser()
parser.add_argument('--experiment-id', required=True)
parser.add_argument('--marker', required=True)
args = parser.parse_args()
Path(args.marker).write_text('executed', encoding='utf-8')
payload = {
    'schema': 'experiment_result.v1',
    'task_id': 'task-exp-native-run',
    'sprint_id': 'sprint-exp-native-run',
    'node_id': 'node-exp-native-run',
    'status': 'completed',
    'inputs': {'experiment_id': args.experiment_id},
    'outputs': {
        'result': {
            'experiment_id': args.experiment_id,
            'outcome': 'supports',
            'metrics': [
                {'name': 'f1', 'value': 0.88},
            ],
            'evidence_ids': ['runtime:exp-native'],
            'logs': ['native command executed'],
        }
    },
    'artifacts': [
        {'type': 'experiment_runtime_output_json', 'path': str(args.marker), 'label': 'marker'},
    ],
    'provenance': {
        'operator_id': 'test-script',
        'implementation_package': 'test',
        'timestamp': '2026-06-24T00:00:00Z',
    },
    'limitations': [],
}
print(json.dumps(payload))