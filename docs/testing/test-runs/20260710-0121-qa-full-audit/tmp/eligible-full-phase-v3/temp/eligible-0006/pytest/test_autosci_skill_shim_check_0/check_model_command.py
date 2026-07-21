import json
import sys

request = json.loads(sys.stdin.read())
assert request['schema'] == 'autosci_model_request.v1'
assert request['action'] == 'check_wiki_health'
assert request['context']['findings']['markdown_page_count'] == 1
assert request['context']['findings']['lint_report']['issue_counts']['error'] == 0
print(json.dumps({
    'schema': 'autosci_model_response.v1',
    'status': 'completed',
    'outputs': {
        'answer': 'The wiki has the required structural blocks and a valid source-linked graph edge.',
        'confidence': 0.91,
        'evidence_ids': ['model:wiki-health-review'],
        'findings': [{'criterion': 'source graph', 'verdict': 'pass'}],
        'model': 'test-model',
        'provider': 'command',
    },
}))