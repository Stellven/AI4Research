import json
import sys
request = json.loads(sys.stdin.read())
paths = [
    ('A:landscape-driven', 'Landscape gap benchmark'),
    ('B:incremental', 'Incremental verifier ablation'),
    ('C:combination', 'Skill memory and verifier fusion'),
    ('D:innovation', 'Novel adaptive skill audit'),
    ('E:cross-domain-transfer', 'Cross-domain skill transfer probe'),
]
ideas = []
for index, (path, title) in enumerate(paths, start=1):
    ideas.append({
        'idea_id': f'idea-model-path-{index:03d}',
        'title': title,
        'hypothesis': f'{title} improves source-grounded agent skill learning evaluation.',
        'approach': f'Run a bounded pilot for {title} against cited SkillGen baselines.',
        'novelty_hypothesis': f'{title} is novel relative to supplied external novelty evidence.',
        'origin_evidence_ids': ['wiki:papers/skillgen', 'external:web:ideate-001'],
        'duplicate_status': 'new',
        'generation_path': path,
    })
payload = {
    'schema': 'autosci_model_response.v1',
    'status': 'completed',
    'outputs': {
        'answer': 'Five-path model brainstorm grounded in SkillGen paper evidence.',
        'confidence': 0.82,
        'provider': 'test-model-provider',
        'model': 'gpt-5.5-test-double',
        'evidence_ids': ['wiki:papers/skillgen', 'external:web:ideate-001'],
        'ideas': ideas,
    },
}
print(json.dumps(payload))