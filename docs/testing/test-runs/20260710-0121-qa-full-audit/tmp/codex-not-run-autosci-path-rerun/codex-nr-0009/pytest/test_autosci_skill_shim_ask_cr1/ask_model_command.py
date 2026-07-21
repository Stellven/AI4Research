import json
import sys
request = json.loads(sys.stdin.read())
assert request['context']['retrieval_hits']
print(json.dumps({
    'schema': 'autosci_model_response.v1',
    'status': 'completed',
    'outputs': {
        'answer': 'SkillGen is supported by verifier-gated generated skills in the retrieved wiki source.',
        'confidence': 0.88,
        'evidence_ids': ['model:skillgen-policy-crystallize'],
        'model': 'test-model',
        'provider': 'command',
    },
}))