import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument('--experiment-id', required=True)
args = parser.parse_args()
print(json.dumps({
    'experiment_id': args.experiment_id,
    'outcome': 'supports',
    'metrics': [{'name': 'accuracy', 'value': 0.86}],
    'evidence_ids': ['runtime:experiment:shim-executor'],
    'logs': ['approved shim executor produced experiment result'],
}))
