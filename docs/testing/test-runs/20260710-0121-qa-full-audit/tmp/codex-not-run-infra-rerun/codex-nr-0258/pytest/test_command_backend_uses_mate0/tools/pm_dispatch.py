#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if len(sys.argv) >= 4 and sys.argv[1] == "complete" and sys.argv[2] == "--task-id":
    task_id = sys.argv[3]
    log = Path(__file__).resolve().parent.parent / "run" / "pm-complete.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"task_id": task_id}, ensure_ascii=False), encoding="utf-8")
    print(f"✅ 任务 {task_id} 已标记为 completed")
    raise SystemExit(0)
raise SystemExit(2)
