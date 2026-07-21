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
            "focus": request.get("focus", "method"),
            "score": 0.52,
            "recommendation": "revise",
            "evidence_ids": ["review-llm:command"]
        },
        "findings": [{
            "finding_id": "review-llm.command-finding",
            "severity": "medium",
            "category": "method",
            "evidence": "Command bridge reviewed the target artifact.",
            "suggestion": "Keep the method evidence attached before promotion."
        }]
    }
}))
