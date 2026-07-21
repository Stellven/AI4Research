import json, os
print(json.dumps({
  'profile_directory': os.environ.get('BROWSER_AGENT_PROFILE_DIRECTORY'),
  'headless': os.environ.get('BROWSER_AGENT_HEADLESS'),
  'account_email': os.environ.get('BROWSER_AGENT_TARGET_ACCOUNT_EMAIL'),
  'pad': 'x' * 700
}, ensure_ascii=False))
