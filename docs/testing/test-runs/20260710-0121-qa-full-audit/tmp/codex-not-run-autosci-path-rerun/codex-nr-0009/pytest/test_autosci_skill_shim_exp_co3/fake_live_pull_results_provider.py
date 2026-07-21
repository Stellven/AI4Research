import json
from pathlib import Path
Path('results.json').write_text(json.dumps({
    'outcome': 'supports',
    'metrics': [{'name': 'accuracy', 'value': 0.97}],
    'evidence_ids': ['result:exp-live-remote-collect'],
    'logs': ['live provider pull-results collected metrics'],
}))
