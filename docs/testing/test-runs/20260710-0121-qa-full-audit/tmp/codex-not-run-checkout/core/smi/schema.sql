-- ============================================================
-- Solar Metadata Index (SMI) Schema
-- 使用 ThunderDuck 作为查询引擎
-- ============================================================

-- ============================================================
-- 1. 文件索引表
-- ============================================================
CREATE TABLE smi_files (
    file_id         VARCHAR PRIMARY KEY,    -- hash(file_path)
    file_path       VARCHAR NOT NULL,       -- 相对于项目根目录的路径
    abs_path        VARCHAR NOT NULL,       -- 绝对路径
    file_type       VARCHAR,                -- md/ts/sql/json/txt/...
    category        VARCHAR,                -- agent/skill/rule/doc/core/test
    feature         VARCHAR,                -- 关联特性 (capsule/backlog/ontology/...)
    project         VARCHAR,                -- 所属项目 (Solar/ThunderDuck/...)
    title           VARCHAR,                -- 文件标题
    description     TEXT,                   -- 简介/摘要
    tags            VARCHAR[],              -- 标签数组
    size_bytes      BIGINT,                 -- 文件大小
    line_count      INTEGER,                -- 行数
    last_modified   TIMESTAMP,              -- 最后修改时间
    content_hash    VARCHAR,                -- 内容哈希 (用于检测变更)
    indexed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_path)
);

-- ============================================================
-- 2. Agent 索引表
-- ============================================================
CREATE TABLE smi_agents (
    agent_id        VARCHAR PRIMARY KEY,    -- @Coder, @Tester, @Researcher...
    name            VARCHAR NOT NULL,       -- Agent 名称
    emoji           VARCHAR,                -- 表情符号
    role            VARCHAR,                -- 角色定位
    phase           VARCHAR,                -- 所属阶段 P1/P2/P3/P4/P5
    capabilities    VARCHAR[],              -- 能力列表
    file_path       VARCHAR,                -- 定义文件路径
    tools           VARCHAR[],              -- 可用工具
    dependencies    VARCHAR[],              -- 依赖的其他 Agent
    description     TEXT,                   -- Agent 描述
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 3. Skill 索引表
-- ============================================================
CREATE TABLE smi_skills (
    skill_id        VARCHAR PRIMARY KEY,    -- backlog, commit, review...
    command         VARCHAR NOT NULL,       -- /backlog, /commit...
    name            VARCHAR,                -- 技能名称
    description     TEXT,                   -- 描述
    user_invocable  BOOLEAN DEFAULT false,  -- 用户可调用
    category        VARCHAR,                -- dev/office/system/util...
    file_path       VARCHAR,                -- SKILL.md 路径
    impl_path       VARCHAR,                -- 实现文件路径 (.ts/.sh)
    runtime         VARCHAR,                -- bun/bash/python...
    dependencies    VARCHAR[],              -- 依赖 (其他 skill/agent)
    tags            VARCHAR[],              -- 标签
    usage_count     INTEGER DEFAULT 0,      -- 使用次数
    last_used       TIMESTAMP,              -- 最后使用时间
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. 规则索引表
-- ============================================================
CREATE TABLE smi_rules (
    rule_id         VARCHAR PRIMARY KEY,    -- performance-testing, tvs-rendering...
    name            VARCHAR NOT NULL,       -- 规则名称
    file_path       VARCHAR,                -- .claude/rules/*.md
    category        VARCHAR,                -- performance/token/tvs/security...
    priority        INTEGER DEFAULT 50,     -- 优先级 0-100
    mandatory       BOOLEAN DEFAULT false,  -- 是否强制执行
    keywords        VARCHAR[],              -- 关键词
    summary         TEXT,                   -- 规则摘要
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 5. 项目索引表
-- ============================================================
CREATE TABLE smi_projects (
    project_id      VARCHAR PRIMARY KEY,    -- Solar, ThunderDuck, NEXEN...
    name            VARCHAR NOT NULL,       -- 项目名称
    path            VARCHAR,                -- 项目绝对路径
    type            VARCHAR,                -- db/ai/web/cli...
    status          VARCHAR DEFAULT 'active', -- active/archived/paused
    description     TEXT,                   -- 项目描述
    tech_stack      VARCHAR[],              -- 技术栈 ['TypeScript', 'Bun', ...]
    total_files     INTEGER DEFAULT 0,      -- 总文件数
    total_features  INTEGER DEFAULT 0,      -- 总特性数
    total_tasks     INTEGER DEFAULT 0,      -- 总任务数
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 6. 关系图谱表
-- ============================================================
CREATE TABLE smi_relationships (
    id              BIGINT PRIMARY KEY,     -- 自增ID
    source_type     VARCHAR NOT NULL,       -- file/agent/skill/feature/rule
    source_id       VARCHAR NOT NULL,       -- 源实体ID
    target_type     VARCHAR NOT NULL,       -- file/agent/skill/feature/rule
    target_id       VARCHAR NOT NULL,       -- 目标实体ID
    relation_type   VARCHAR NOT NULL,       -- depends_on/implements/used_by/references
    weight          DOUBLE DEFAULT 1.0,     -- 关系权重
    metadata        JSON,                   -- 额外元数据
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 7. 标签系统
-- ============================================================
CREATE TABLE smi_tags (
    tag_id          VARCHAR PRIMARY KEY,    -- uuid
    entity_type     VARCHAR NOT NULL,       -- file/agent/skill/feature/rule
    entity_id       VARCHAR NOT NULL,       -- 实体ID
    tag             VARCHAR NOT NULL,       -- 标签名
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entity_type, entity_id, tag)
);

-- ============================================================
-- 8. 索引历史表 (记录索引操作)
-- ============================================================
CREATE TABLE smi_index_history (
    id              BIGINT PRIMARY KEY,
    operation       VARCHAR,                -- scan/update/delete
    entity_type     VARCHAR,                -- file/agent/skill/...
    entity_id       VARCHAR,
    status          VARCHAR,                -- success/failed
    duration_ms     INTEGER,                -- 耗时
    error_msg       TEXT,                   -- 错误信息
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 9. 搜索视图 (统一搜索接口)
-- ============================================================
CREATE VIEW v_smi_search AS
SELECT
    'file' as entity_type,
    file_id as id,
    title,
    description,
    file_path as path,
    feature,
    project,
    tags
FROM smi_files
UNION ALL
SELECT
    'agent' as entity_type,
    agent_id as id,
    name as title,
    description,
    file_path as path,
    NULL as feature,
    NULL as project,
    capabilities as tags
FROM smi_agents
UNION ALL
SELECT
    'skill' as entity_type,
    skill_id as id,
    name as title,
    description,
    file_path as path,
    NULL as feature,
    NULL as project,
    tags
FROM smi_skills
UNION ALL
SELECT
    'rule' as entity_type,
    rule_id as id,
    name as title,
    summary as description,
    file_path as path,
    NULL as feature,
    NULL as project,
    keywords as tags
FROM smi_rules;

-- ============================================================
-- 10. 项目概览视图
-- ============================================================
CREATE VIEW v_smi_project_overview AS
SELECT
    p.project_id,
    p.name,
    p.status,
    COUNT(DISTINCT f.file_id) as file_count,
    COUNT(DISTINCT a.agent_id) as agent_count,
    COUNT(DISTINCT s.skill_id) as skill_count
FROM smi_projects p
LEFT JOIN smi_files f ON p.project_id = f.project
LEFT JOIN smi_agents a ON p.project_id = a.agent_id -- 简化，实际需要关联表
LEFT JOIN smi_skills s ON p.project_id = s.skill_id -- 简化
GROUP BY p.project_id, p.name, p.status;

-- ============================================================
-- 11. 特性依赖视图
-- ============================================================
CREATE VIEW v_smi_feature_dependencies AS
SELECT
    r.source_id as feature,
    r.target_id as dependency,
    r.relation_type,
    r.weight
FROM smi_relationships r
WHERE r.source_type = 'feature'
  AND r.target_type IN ('feature', 'file', 'agent')
  AND r.relation_type = 'depends_on';

-- ============================================================
-- 索引优化
-- ============================================================
CREATE INDEX idx_files_project ON smi_files(project);
CREATE INDEX idx_files_feature ON smi_files(feature);
CREATE INDEX idx_files_category ON smi_files(category);
CREATE INDEX idx_files_modified ON smi_files(last_modified);

CREATE INDEX idx_relationships_source ON smi_relationships(source_type, source_id);
CREATE INDEX idx_relationships_target ON smi_relationships(target_type, target_id);
CREATE INDEX idx_relationships_type ON smi_relationships(relation_type);

CREATE INDEX idx_tags_entity ON smi_tags(entity_type, entity_id);
CREATE INDEX idx_tags_tag ON smi_tags(tag);
