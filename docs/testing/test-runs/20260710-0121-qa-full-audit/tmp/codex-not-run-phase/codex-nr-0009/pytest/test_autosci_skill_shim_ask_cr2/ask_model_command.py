import json
import sys
request = json.loads(sys.stdin.read())
assert request['action'] == 'ask_wiki'
assert request['prompt'] != 'concept:skillgen-support'
assert request['context']['wiki_context']['sources']['context_brief']['status'] == 'present'
assert request['context']['wiki_context']['sources']['open_questions']['status'] == 'present'
assert request['context']['gap_annotations']['status'] == 'matched_open_questions'
print(json.dumps({
    'schema': 'autosci_model_response.v1',
    'status': 'completed',
    'outputs': {
        'answer': 'SkillGen support is grounded in verifier-gated generated skills from the retrieved source.',
        'confidence': 0.87,
        'evidence_ids': ['model:skillgen-concept'],
        'model': 'test-model',
        'provider': 'command',
    },
}))