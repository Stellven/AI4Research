import json
import sys

request = json.loads(sys.stdin.read())
assert request['schema'] == 'autosci_model_request.v1'
assert request['action'] == 'ask_wiki'
assert request['context']['retrieval_hits']
print(json.dumps({
    'schema': 'autosci_model_response.v1',
    'status': 'completed',
    'outputs': {
        'answer': 'SkillGen is supported by verifier-gated generated skills in the retrieved wiki evidence.',
        'confidence': 0.82,
        'evidence_ids': ['model:skillgen-support'],
        'model': 'test-model',
        'provider': 'command',
    },
}))