#!/usr/bin/env python3
import argparse
from pathlib import Path
import json

parser = argparse.ArgumentParser()
parser.add_argument('--experiment-id', required=True)
parser.add_argument('--marker', required=True)
args = parser.parse_args()
Path(args.marker).write_text('pilot executed', encoding='utf-8')
payload = {
    'schema': 'experiment_result.v1',
    'task_id': 'task-pilot-native-run',
    'sprint_id': 'sprint-pilot-native-run',
    'node_id': 'node-pilot-native-run',
    'status': 'completed',
    'inputs': {'experiment_id': args.experiment_id},
    'outputs': {
        'result': {
            'experiment_id': args.experiment_id,
            'outcome': 'supports',
            'metrics': [{'name': 'accuracy', 'value': 0.93}],
            'evidence_ids': ['runtime:pilot-native'],
            'logs': ['pilot native command executed'],
        }
    },
    'provenance': {
        'operator_id': 'pilot-test-script',
        'implementation_package': 'test',
        'timestamp': '2026-06-24T00:00:00Z',
    },
    'limitations': [],
}
print(json.dumps(payload))