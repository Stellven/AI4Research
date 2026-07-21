#!/bin/bash
# Solar SES Session End Hook
# Records session completion and updates skill proficiencies

DB_PATH="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/logs/ses-session.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "Session ended, updating skill proficiencies..."

# Update skill proficiencies from recent tool calls
sqlite3 "$DB_PATH" "
-- Update skill proficiencies from evo_tool_calls
INSERT INTO ses_skill_proficiency (
    skill_name, tool_name, category, usage_count, success_count, failure_count,
    dreyfus_level, level_evidence, last_used_at, updated_at
)
SELECT
    tool_name,
    tool_name,
    CASE
        WHEN tool_name IN ('Read', 'Write', 'Edit', 'Glob') THEN 'file_ops'
        WHEN tool_name IN ('Grep', 'WebSearch', 'WebFetch') THEN 'search'
        WHEN tool_name IN ('Bash', 'NotebookEdit') THEN 'code'
        ELSE 'other'
    END,
    COUNT(*),
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END),
    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END),
    1,
    'Auto-initialized',
    MAX(created_at),
    datetime('now')
FROM evo_tool_calls
WHERE tool_name IS NOT NULL
GROUP BY tool_name
ON CONFLICT(skill_name) DO UPDATE SET
    usage_count = (SELECT COUNT(*) FROM evo_tool_calls WHERE tool_name = excluded.skill_name),
    success_count = (SELECT SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) FROM evo_tool_calls WHERE tool_name = excluded.skill_name),
    failure_count = (SELECT SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) FROM evo_tool_calls WHERE tool_name = excluded.skill_name),
    last_used_at = excluded.last_used_at,
    updated_at = datetime('now');
" 2>/dev/null

# Calculate Dreyfus levels
sqlite3 "$DB_PATH" "
UPDATE ses_skill_proficiency
SET
    previous_level = dreyfus_level,
    dreyfus_level = CASE
        WHEN usage_count >= 200 AND (success_count * 100.0 / usage_count) >= 95 THEN 5
        WHEN usage_count >= 100 AND (success_count * 100.0 / usage_count) >= 90 THEN 4
        WHEN usage_count >= 50 AND (success_count * 100.0 / usage_count) >= 80 THEN 3
        WHEN usage_count >= 10 AND (success_count * 100.0 / usage_count) >= 60 THEN 2
        ELSE 1
    END,
    level_evidence = 'usage=' || usage_count || ', success_rate=' || ROUND(success_count * 100.0 / NULLIF(usage_count, 0), 1) || '%',
    level_changed_at = CASE
        WHEN dreyfus_level != (
            CASE
                WHEN usage_count >= 200 AND (success_count * 100.0 / usage_count) >= 95 THEN 5
                WHEN usage_count >= 100 AND (success_count * 100.0 / usage_count) >= 90 THEN 4
                WHEN usage_count >= 50 AND (success_count * 100.0 / usage_count) >= 80 THEN 3
                WHEN usage_count >= 10 AND (success_count * 100.0 / usage_count) >= 60 THEN 2
                ELSE 1
            END
        ) THEN datetime('now')
        ELSE level_changed_at
    END;
" 2>/dev/null

log "Skill proficiencies updated"

exit 0
