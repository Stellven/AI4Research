import os, sys, json
import time
from pathlib import Path
sleep_seconds=0
if sleep_seconds:
    time.sleep(sleep_seconds)
prompt=sys.stdin.read()
write_deep_proof='True' == 'True'
request_dir=os.environ.get('BROWSER_AGENT_REQUEST_DIR')
if write_deep_proof and request_dir:
    Path(request_dir).mkdir(parents=True, exist_ok=True)
    (Path(request_dir)/'deep-research-state.json').write_text(json.dumps({'ok': True, 'test': True}), encoding='utf-8')
write_mode_proof='True' == 'True'
if write_mode_proof and request_dir:
    Path(request_dir).mkdir(parents=True, exist_ok=True)
    (Path(request_dir)/'chatgpt-mode-state.json').write_text(json.dumps({'ok': True, 'test': True}), encoding='utf-8')
out={'model':os.environ.get('CHATGPT_MODEL'),'effort':os.environ.get('CHATGPT_REASONING_EFFORT'),'model_mode':os.environ.get('BROWSER_AGENT_CHATGPT_MODEL_MODE'),'tool_mode':os.environ.get('BROWSER_AGENT_CHATGPT_TOOL_MODE'),'require_deep_research':os.environ.get('BROWSER_AGENT_CHATGPT_REQUIRE_DEEP_RESEARCH'),'require_ui_mode':os.environ.get('BROWSER_AGENT_CHATGPT_REQUIRE_UI_MODE'),'action':os.environ.get('BROWSER_AGENT_CHATGPT_ACTION'),'project':os.environ.get('BROWSER_AGENT_CHATGPT_PROJECT_NAME'),'profile_directory':os.environ.get('BROWSER_AGENT_PROFILE_DIRECTORY'),'target_account_email':os.environ.get('BROWSER_AGENT_TARGET_ACCOUNT_EMAIL'),'chatgpt_account_email':os.environ.get('BROWSER_AGENT_CHATGPT_ACCOUNT_EMAIL'),'prompt':prompt[:1000]}
print(json.dumps(out, ensure_ascii=False))
