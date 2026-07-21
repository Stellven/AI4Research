# Solar Harness Brain

Subconscious learning system for harness personas.

## lessons.jsonl Format

Append-only JSONL, each line:

```json
{"ts":"ISO8601","sprint_id":"sprint-xxx","lesson":"教训内容","source":"eval|handoff|seed","confidence":0.0-1.0,"tags":["tag1"]}
```

## How it works

1. **Learn** (Stop hook): After each Sprint, extract lessons from eval.json → append to lessons.jsonl
2. **Whisper** (UserPromptSubmit hook): Before each prompt, find relevant lessons → inject as system-reminder
3. **Improve**: Claude avoids past mistakes → better execution → better lessons → virtuous cycle

## Constraints

- Append-only: never delete or modify existing lines
- Max 3 whispers per prompt, each < 100 chars
- Whisper latency < 2 seconds (pure local grep/jq)
