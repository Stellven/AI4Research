#!/usr/bin/env python3
import os
from pathlib import Path

dispatch = Path(os.environ["SOLAR_MULTI_TASK_DISPATCH_FILE"]).read_text(encoding="utf-8")
handoff = Path(os.environ["HANDOFF"])
handoff.parent.mkdir(parents=True, exist_ok=True)
handoff.write_text("# Handoff\n\n" + dispatch, encoding="utf-8")
result_path = os.environ.get("RESULT_PATH") or os.environ.get("PM_RESULT_PATH") or ""
if result_path:
    result = Path(result_path)
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text("# PM Task Result\n\n## 已完成\n- command backend wrote result\n", encoding="utf-8")
print("dispatch_seen=" + str(Path(os.environ["SOLAR_MULTI_TASK_DISPATCH_FILE"]).exists()))
print("handoff_written=" + str(handoff))
