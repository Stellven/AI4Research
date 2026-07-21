
import json, sys
data = json.load(sys.stdin)
print(json.dumps({"score": len(data["candidate"]) / 100.0, "info": "ok"}))
