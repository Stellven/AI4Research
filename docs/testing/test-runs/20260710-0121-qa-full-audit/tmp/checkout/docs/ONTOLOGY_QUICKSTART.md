# Solar 本体系统 v2.0 快速指南

## 一键初始化

```bash
~/Solar/core/bootstrap/setup-all.sh
```

这会完成所有初始化工作，包括：
- 创建数据库表
- 初始化 Core Memory (身份/第一规律/核心价值)
- 备份 A 人格 (金刚芭比)
- 初始化 B 人格 Big Five
- 安装 launchd 后台服务

## 常用查询

### 查看 Core Memory

```sql
sqlite3 ~/.solar/solar.db "SELECT category, key, value FROM evo_memory_core;"
```

### 查看 Big Five 人格对比

```sql
sqlite3 -header -column ~/.solar/solar.db "
SELECT
    a.dimension,
    a.current_value as 'A(金刚芭比)',
    b.current_value as 'B(学术派)',
    ROUND(b.current_value - a.current_value, 2) as '差异'
FROM sys_personality_big_five a
JOIN sys_personality_big_five b ON a.dimension = b.dimension
WHERE a.personality_id = 'jingang_barbie'
  AND b.personality_id = 'academic'
ORDER BY a.dimension;
"
```

### 查看记忆统计

```sql
sqlite3 ~/.solar/solar.db "
SELECT 'Core' as type, COUNT(*) FROM evo_memory_core
UNION SELECT 'Episodic', COUNT(*) FROM evo_memory_episodic
UNION SELECT 'Semantic', COUNT(*) FROM evo_memory_semantic
UNION SELECT 'Procedural', COUNT(*) FROM evo_memory_procedural;
"
```

## 手动触发

### 记忆巩固

```bash
~/Solar/core/ontology/memory-consolidator.sh
```

### 人格学习

```bash
~/Solar/core/ontology/personality-learner.sh
```

### 查看日志

```bash
tail -20 ~/.solar/memory-consolidator.log
tail -20 ~/.solar/personality-learner.log
```

## 后台服务状态

```bash
launchctl list | grep com.solar
```

| 服务 | 周期 | 用途 |
|------|------|------|
| memory-consolidator | 每小时 | 记忆巩固 |
| personality-learner | 每天3点 | 人格学习 |
| mail-agent | 2分钟 | 邮件监听 |
| ontology-reflector | 6小时 | 反思 |
| hn-monitor | 1小时 | HN监控 |

## 人格快照

### 创建快照

```sql
sqlite3 ~/.solar/solar.db "
INSERT INTO sys_personality_snapshots (snapshot_id, personality_id, snapshot_data, reason)
SELECT
    'snapshot_' || strftime('%Y%m%d%H%M%S', 'now'),
    'academic',
    json_object(
        'O', (SELECT current_value FROM sys_personality_big_five WHERE personality_id='academic' AND dimension='O'),
        'C', (SELECT current_value FROM sys_personality_big_five WHERE personality_id='academic' AND dimension='C'),
        'E', (SELECT current_value FROM sys_personality_big_five WHERE personality_id='academic' AND dimension='E'),
        'A', (SELECT current_value FROM sys_personality_big_five WHERE personality_id='academic' AND dimension='A'),
        'N', (SELECT current_value FROM sys_personality_big_five WHERE personality_id='academic' AND dimension='N')
    ),
    '手动快照';
"
```

### 查看快照

```sql
sqlite3 ~/.solar/solar.db "SELECT snapshot_id, personality_id, reason, created_at FROM sys_personality_snapshots;"
```

## 文件位置

```
~/Solar/core/bootstrap/
├── setup-all.sh           # 一键初始化
├── startup-check.sh       # 启动检查
└── external-deps.json     # 外部依赖清单

~/Solar/core/ontology/
├── memory-consolidator.sh # 记忆巩固
└── personality-learner.sh # 人格学习

~/.solar/
├── solar.db               # 主数据库
├── memory-consolidator.log
└── personality-learner.log
```

## 当前状态 (2026-02-04)

| 项目 | 状态 |
|------|------|
| Core Memory | 7 条 |
| Semantic Memory | 31 条 |
| A 人格快照 | 已备份 |
| B 人格 Big Five | 已计算 |
| 后台服务 | 已安装 |

### B 人格 Big Five

| 维度 | 值 | 数据来源 |
|------|-----|----------|
| O (开放性) | 0.70 | 21个知识领域 |
| C (尽责性) | 0.95 | 100%执行成功率 |
| E (外向性) | 0.80 | 31条知识*260字符 |
| A (宜人性) | 0.75 | 29%关系知识 |
| N (神经质) | 0.15 | 0%错误率 |
