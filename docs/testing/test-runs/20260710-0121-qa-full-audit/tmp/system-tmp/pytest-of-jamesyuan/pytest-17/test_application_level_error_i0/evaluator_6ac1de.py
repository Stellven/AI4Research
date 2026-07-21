
import sys, json
json.load(sys.stdin)
print(json.dumps({"error": "bad candidate format"}))
