# Brain Update Reminder Hook

> 提醒 Solar 定期更新大脑信息

## 触发条件

### 会话开始时检查

```yaml
event: session_start
condition: |
  SELECT CASE 
    WHEN julianday('now') - julianday(MAX(last_updated)) > 14 
    THEN 1 ELSE 0 
  END as need_update
  FROM sys_brain_profiles
action: |
  如果 need_update = 1，提醒:
  "⚠️ 大脑信息已超过 14 天未更新，建议执行 /brain-update"
```

### 定期提醒

```yaml
schedule: "每周日 20:00"
action: "执行 /brain-update 或提醒监护人"
```

### 新闻触发

当在对话中检测到以下关键词时，主动搜索更新:
- "新模型发布"
- "价格调整" 
- "LLM 降价"
- "GPT-6"、"Claude 5"、"Gemini 4" 等新版本号

## 实现方式

由于 Claude Code 的 Hook 系统主要是 shell 命令，
实际的提醒需要在会话开始时由 Solar 主动检查:

```sql
-- 在会话开始时执行此查询
SELECT 
  CASE 
    WHEN julianday('now') - julianday(MAX(last_updated)) > 14 
    THEN '⚠️ 大脑信息需要更新 (已超过14天)'
    WHEN julianday('now') - julianday(MAX(last_updated)) > 7
    THEN '💡 建议本周更新大脑信息'
    ELSE '✓ 大脑信息是最新的'
  END as status,
  MAX(last_updated) as last_update
FROM sys_brain_profiles;
```

---

*Brain Update Reminder Hook*
*保持信息与时俱进*
*Solar*
