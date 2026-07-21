#!/usr/bin/env bash
# test-harness-graph.sh — verify harness graph JSON + Mermaid outputs
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GRAPH_PY="$HARNESS_DIR/lib/harness_graph.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[[ -f "$GRAPH_PY" ]] || fail "harness_graph.py not found at $GRAPH_PY"

# Run graph with both outputs
OUTPUT="$(python3 "$GRAPH_PY" --json --mermaid 2>&1)"

# JSON section: extract up to the first } after "generated_at"
JSON_PART="$(echo "$OUTPUT" | python3 -c "
import sys, json
text = sys.stdin.read()
# Find the JSON object (starts with '{')
start = text.find('{')
if start == -1:
    sys.exit(1)
# Find matching close brace
depth = 0
for i, c in enumerate(text[start:], start):
    if c == '{': depth += 1
    elif c == '}':
        depth -= 1
        if depth == 0:
            print(text[start:i+1])
            break
")"

[[ -n "$JSON_PART" ]] || fail "no JSON object found in output"

# Validate JSON structure
python3 -c "
import json, sys
d = json.loads('''$JSON_PART''')
assert 'nodes' in d, 'missing nodes key'
assert 'edges' in d, 'missing edges key'
assert 'stats' in d, 'missing stats key'
nodes = d['nodes']
edges = d['edges']
# Check core dependencies present
node_ids = {n['id'] for n in nodes}
required_nodes = ['solar-harness', 'coordinator', 'pane-launcher', 'solar_skills', 'harness_graph', 'solar_mirage']
for req in required_nodes:
    assert req in node_ids, f'missing required node: {req}'
# Check edges include coordinator->solar_skills
found_inject_edge = any(
    e['from'] == 'coordinator' and e['to'] == 'solar_skills'
    for e in edges
)
assert found_inject_edge, 'missing coordinator->solar_skills edge'
# Check stats
assert d['stats']['total_nodes'] >= 15, 'too few nodes'
assert d['stats']['total_edges'] >= 10, 'too few edges'
print('JSON validation OK')
print(f'  nodes: {len(nodes)}, edges: {len(edges)}')
print(f'  existing: {d[\"stats\"][\"existing_nodes\"]}, missing: {d[\"stats\"][\"missing_nodes\"]}')
" || fail "JSON validation failed"

# Mermaid section: must contain "graph LR" and key nodes
MERMAID_PART="$(echo "$OUTPUT" | grep -A999 "^graph LR")"
[[ -n "$MERMAID_PART" ]] || fail "no Mermaid output found"

echo "$MERMAID_PART" | grep -q "solar-harness" || fail "solar-harness missing from Mermaid"
echo "$MERMAID_PART" | grep -q "coordinator" || fail "coordinator missing from Mermaid"
echo "$MERMAID_PART" | grep -q "solar_skills" || fail "solar_skills missing from Mermaid"
echo "$MERMAID_PART" | grep -q "subgraph" || fail "no subgraph sections in Mermaid"

pass "graph JSON — nodes/edges/stats structure valid"
pass "graph JSON — core dependencies present"
pass "graph Mermaid — key nodes present with subgraphs"
echo "PROBES_PASSED=3 PROBES_FAILED=0"
exit 0
