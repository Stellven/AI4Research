import json
import sys

request = json.loads(sys.stdin.read())
target = request["inputs"].get("target", "N/A")
print(json.dumps({
    "schema": "artifact_review.v1",
    "status": "completed",
    "outputs": {
        "review": {
            "artifact_id": "artifact:" + target,
            "target": target,
            "review_mode": "review_llm",
            "review_available": True,
            "difficulty": request.get("difficulty", "standard"),
            "focus": request.get("focus", "writing"),
            "score": 0.92,
            "recommendation": "pass_with_review_required",
            "evidence_ids": ["review-llm:refine-command"]
        },
        "findings": []
    }
}))
