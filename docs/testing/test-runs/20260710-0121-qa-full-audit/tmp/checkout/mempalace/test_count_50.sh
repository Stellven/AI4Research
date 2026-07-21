#!/bin/bash
# D3: collection >= 50 docs 验证
set -e
python3.11 -c "
import warnings; warnings.filterwarnings('ignore')
import sys
sys.path.insert(0, '~/.solar/mempalace')
from mempalace_mcp_server import mempalace_stats
s = mempalace_stats()
count = s.get('total_docs', 0)
sys.exit(0 if count >= 50 else 1)
"
