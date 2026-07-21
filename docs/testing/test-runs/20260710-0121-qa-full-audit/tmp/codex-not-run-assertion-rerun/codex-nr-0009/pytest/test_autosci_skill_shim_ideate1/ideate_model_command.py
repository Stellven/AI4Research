import json
import sys
request = json.loads(sys.stdin.read())
assert request['action'] == 'generate_ideas'
assert request['context']['topic'] == 'agent skill learning'
payload = {
    'schema': 'autosci_model_response.v1',
    'status': 'completed',
    'outputs': {
        'answer': 'Model brainstorm grounded in SkillGen paper evidence.',
        'confidence': 0.72,
        'provider': 'test-model-provider',
        'model': 'gpt-5.5-test-double',
        'evidence_ids': ['wiki:papers/skillgen'],
        'ideas': [
            {
                'idea_id': 'idea-model-skillgen-001',
                'title': 'Verifier-gated skill transfer benchmark',
                'hypothesis': 'Verifier-gated generated skills transfer more reliably across held-out agent tasks.',
                'approach': 'Build a benchmark that compares generated skills with and without verifier gates across held-out tasks.',
                'novelty_hypothesis': 'The contribution is a source-grounded transfer benchmark for generated agent skills.',
                'origin_evidence_ids': ['wiki:papers/skillgen'],
                'duplicate_status': 'unknown',
            }
        ],
    },
}
print(json.dumps(payload))