-- Solar Metadata System - Seed Data
-- Version: 1.0
-- Description: 初始化元数据系统 - Agents, Skills, 阶段映射, 互评规则

-- ============================================================================
-- 1. 注册开发 Agents 到 sys_resources + sys_agents
-- ============================================================================

-- 注册到 sys_resources (主表)
INSERT OR REPLACE INTO sys_resources (resource_id, resource_type, name, version, status, description, config, created_at)
VALUES
    ('agent:researcher:1.0', 'agent', 'Researcher', '1.0', 'active', 'P1 研究：需求分析、技术调研、可行性评估', '{"emoji": "🔬", "phase": "P1"}', CURRENT_TIMESTAMP),
    ('agent:architect:1.0', 'agent', 'Architect', '1.0', 'active', 'P2 设计：架构设计、API 设计、技术选型', '{"emoji": "🏗️", "phase": "P2"}', CURRENT_TIMESTAMP),
    ('agent:coder:1.0', 'agent', 'Coder', '1.0', 'active', 'P3 实现：编码、优化、重构', '{"emoji": "💻", "phase": "P3"}', CURRENT_TIMESTAMP),
    ('agent:tester:1.0', 'agent', 'Tester', '1.0', 'active', 'P4 测试：单元测试、集成测试、性能测试', '{"emoji": "🧪", "phase": "P4"}', CURRENT_TIMESTAMP),
    ('agent:reviewer:1.0', 'agent', 'Reviewer', '1.0', 'active', 'P4 审查：代码审查、安全检查、最佳实践', '{"emoji": "👁️", "phase": "P4"}', CURRENT_TIMESTAMP),
    ('agent:docs:1.0', 'agent', 'Docs', '1.0', 'active', 'P5 文档：README、API 文档、使用指南', '{"emoji": "📖", "phase": "P5"}', CURRENT_TIMESTAMP),
    ('agent:ops:1.0', 'agent', 'Ops', '1.0', 'active', 'P5 运维：构建、部署、CI/CD', '{"emoji": "⚙️", "phase": "P5"}', CURRENT_TIMESTAMP),
    ('agent:reporter:1.0', 'agent', 'Reporter', '1.0', 'active', 'P5 报告：技术报告、变更日志', '{"emoji": "📝", "phase": "P5"}', CURRENT_TIMESTAMP),
    ('agent:guard:1.0', 'agent', 'Guard', '1.0', 'active', '全程：安全检查、规范检查、版本完整性', '{"emoji": "🛡️", "phase": "ALL"}', CURRENT_TIMESTAMP),
    ('agent:pm:1.0', 'agent', 'PM', '1.0', 'active', '全程：进度跟踪、产品验收', '{"emoji": "📊", "phase": "ALL"}', CURRENT_TIMESTAMP),
    ('agent:secretary:1.0', 'agent', 'Secretary', '1.0', 'active', '全程：记录、互评、综合评定', '{"emoji": "📋", "phase": "ALL"}', CURRENT_TIMESTAMP),
    ('agent:benchmark-reporter:1.0', 'agent', 'BenchmarkReporter', '1.0', 'active', 'P4：性能基准报告', '{"emoji": "📈", "phase": "P4"}', CURRENT_TIMESTAMP),
    ('agent:skill-market:1.0', 'agent', 'SkillMarket', '1.0', 'active', '按需：Skill 搜索安装', '{"emoji": "🛒", "phase": "ON_DEMAND"}', CURRENT_TIMESTAMP);

-- 注册到 sys_agents (Agent 详情表)
INSERT OR REPLACE INTO sys_agents (agent_id, emoji, role, phases, tools, default_model, priority, max_concurrent, timeout_seconds)
VALUES
    ('agent:researcher:1.0', '🔬', 'researcher', '["P1"]', '["Read", "Grep", "Glob", "WebSearch", "WebFetch"]', 'sonnet', 50, 1, 300),
    ('agent:architect:1.0', '🏗️', 'architect', '["P2"]', '["Read", "Write", "Grep", "Glob"]', 'opus', 60, 1, 600),
    ('agent:coder:1.0', '💻', 'coder', '["P3"]', '["Read", "Write", "Edit", "Bash", "Grep", "Glob"]', 'sonnet', 70, 1, 900),
    ('agent:tester:1.0', '🧪', 'tester', '["P4"]', '["Read", "Write", "Bash", "Grep", "Glob"]', 'sonnet', 60, 1, 600),
    ('agent:reviewer:1.0', '👁️', 'reviewer', '["P4"]', '["Read", "Grep", "Glob"]', 'opus', 80, 1, 300),
    ('agent:docs:1.0', '📖', 'docs', '["P5"]', '["Read", "Write", "Edit", "Grep", "Glob"]', 'sonnet', 40, 1, 300),
    ('agent:ops:1.0', '⚙️', 'ops', '["P5"]', '["Read", "Bash", "Grep", "Glob"]', 'haiku', 50, 1, 600),
    ('agent:reporter:1.0', '📝', 'reporter', '["P5"]', '["Read", "Write", "Grep", "Glob"]', 'sonnet', 40, 1, 300),
    ('agent:guard:1.0', '🛡️', 'guard', '["ALL"]', '["Read", "Grep", "Glob"]', 'sonnet', 90, 1, 120),
    ('agent:pm:1.0', '📊', 'pm', '["ALL"]', '["Read", "Grep", "Glob"]', 'sonnet', 50, 1, 300),
    ('agent:secretary:1.0', '📋', 'secretary', '["ALL"]', '["Read", "Write"]', 'sonnet', 30, 1, 600),
    ('agent:benchmark-reporter:1.0', '📈', 'benchmark', '["P4"]', '["Read", "Write", "Bash", "Grep", "Glob"]', 'sonnet', 50, 1, 600),
    ('agent:skill-market:1.0', '🛒', 'skill-market', '["ON_DEMAND"]', '["WebSearch", "WebFetch", "Bash"]', 'haiku', 30, 1, 300);


-- ============================================================================
-- 2. 注册 Skills 到 sys_resources + sys_skills
-- ============================================================================

INSERT OR REPLACE INTO sys_resources (resource_id, resource_type, name, version, status, description, config, created_at)
VALUES
    ('skill:solar:1.0', 'skill', 'solar', '1.0', 'active', '启动 Solar 开发流程', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:phase:1.0', 'skill', 'phase', '1.0', 'active', '阶段转换控制', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:commit:1.0', 'skill', 'commit', '1.0', 'active', 'Git 提交流程', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:pr:1.0', 'skill', 'pr', '1.0', 'active', '创建 Pull Request', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:benchmark:1.0', 'skill', 'benchmark', '1.0', 'active', '运行性能基准测试', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:review:1.0', 'skill', 'review', '1.0', 'active', '代码审查流程', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:test:1.0', 'skill', 'test', '1.0', 'active', '运行测试套件', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:build:1.0', 'skill', 'build', '1.0', 'active', '构建项目', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:save:1.0', 'skill', 'save', '1.0', 'active', '保存会话状态', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:restore:1.0', 'skill', 'restore', '1.0', 'active', '恢复会话状态', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:docs:1.0', 'skill', 'docs', '1.0', 'active', '生成/更新文档', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:changelog:1.0', 'skill', 'changelog', '1.0', 'active', '生成变更日志', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:report:1.0', 'skill', 'report', '1.0', 'active', '生成技术报告', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:status:1.0', 'skill', 'status', '1.0', 'active', '显示系统状态', '{"user_invocable": true}', CURRENT_TIMESTAMP),
    ('skill:stats:1.0', 'skill', 'stats', '1.0', 'active', '显示 Token 统计', '{"user_invocable": true}', CURRENT_TIMESTAMP);

INSERT OR REPLACE INTO sys_skills (skill_id, user_invocable, command, category, linked_agent, path, examples)
VALUES
    ('skill:solar:1.0', TRUE, '/solar', 'workflow', 'agent:coder:1.0', 'skills/solar/SKILL.md', '["/solar start", "启动开发"]'),
    ('skill:phase:1.0', TRUE, '/phase', 'workflow', 'agent:pm:1.0', 'skills/phase/SKILL.md', '["/phase next", "/phase P3"]'),
    ('skill:commit:1.0', TRUE, '/commit', 'git', 'agent:coder:1.0', 'skills/commit/SKILL.md', '["/commit", "提交代码"]'),
    ('skill:pr:1.0', TRUE, '/pr', 'git', 'agent:coder:1.0', 'skills/pr/SKILL.md', '["/pr", "创建PR"]'),
    ('skill:benchmark:1.0', TRUE, '/benchmark', 'testing', 'agent:tester:1.0', 'skills/benchmark/SKILL.md', '["/benchmark", "性能测试"]'),
    ('skill:review:1.0', TRUE, '/review', 'quality', 'agent:reviewer:1.0', 'skills/review/SKILL.md', '["/review", "代码审查"]'),
    ('skill:test:1.0', TRUE, '/test', 'testing', 'agent:tester:1.0', 'skills/test/SKILL.md', '["/test", "运行测试"]'),
    ('skill:build:1.0', TRUE, '/build', 'build', 'agent:ops:1.0', 'skills/build/SKILL.md', '["/build", "构建项目"]'),
    ('skill:save:1.0', TRUE, '/save', 'state', 'agent:secretary:1.0', 'skills/save/SKILL.md', '["/save", "保存状态"]'),
    ('skill:restore:1.0', TRUE, '/restore', 'state', 'agent:secretary:1.0', 'skills/restore/SKILL.md', '["/restore", "恢复状态"]'),
    ('skill:docs:1.0', TRUE, '/docs', 'docs', 'agent:docs:1.0', 'skills/docs/SKILL.md', '["/docs", "生成文档"]'),
    ('skill:changelog:1.0', TRUE, '/changelog', 'docs', 'agent:reporter:1.0', 'skills/changelog/SKILL.md', '["/changelog"]'),
    ('skill:report:1.0', TRUE, '/report', 'docs', 'agent:reporter:1.0', 'skills/report/SKILL.md', '["/report", "技术报告"]'),
    ('skill:status:1.0', TRUE, '/status', 'system', NULL, 'skills/status/SKILL.md', '["/status"]'),
    ('skill:stats:1.0', TRUE, '/stats', 'system', NULL, 'skills/stats/SKILL.md', '["/stats"]');


-- ============================================================================
-- 3. 阶段-Agent 映射 (sys_phase_agents)
-- ============================================================================

INSERT OR REPLACE INTO sys_phase_agents (phase, agent_id, is_primary, priority)
VALUES
    -- P1 研究阶段
    ('P1', 'agent:researcher:1.0', TRUE, 100),
    ('P1', 'agent:guard:1.0', FALSE, 50),

    -- P2 设计阶段
    ('P2', 'agent:architect:1.0', TRUE, 100),
    ('P2', 'agent:guard:1.0', FALSE, 50),

    -- P3 实现阶段
    ('P3', 'agent:coder:1.0', TRUE, 100),
    ('P3', 'agent:guard:1.0', FALSE, 50),

    -- P4 验证阶段
    ('P4', 'agent:tester:1.0', TRUE, 100),
    ('P4', 'agent:reviewer:1.0', TRUE, 90),
    ('P4', 'agent:benchmark-reporter:1.0', FALSE, 70),
    ('P4', 'agent:guard:1.0', FALSE, 50),

    -- P5 收尾阶段
    ('P5', 'agent:docs:1.0', TRUE, 100),
    ('P5', 'agent:ops:1.0', TRUE, 90),
    ('P5', 'agent:reporter:1.0', FALSE, 70),
    ('P5', 'agent:pm:1.0', FALSE, 60),

    -- 全程参与
    ('ALL', 'agent:secretary:1.0', FALSE, 30),
    ('ALL', 'agent:guard:1.0', FALSE, 98);


-- ============================================================================
-- 4. 开发 Agents 互评规则 (evo_review_rules)
-- ============================================================================

INSERT OR REPLACE INTO evo_review_rules (
    rule_id, reviewer_role, reviewee_role, review_phase,
    relevance_weight, quality_weight, actionability_weight, efficiency_weight, innovation_weight,
    enabled
)
VALUES
    -- Architect 评价 Researcher 的调研质量
    ('rule:dev:architect_reviews_researcher', 'agent:architect:1.0', 'agent:researcher:1.0', 'P1_to_P2',
     0.35, 0.30, 0.20, 0.10, 0.05, TRUE),

    -- Coder 评价 Architect 的设计可实现性
    ('rule:dev:coder_reviews_architect', 'agent:coder:1.0', 'agent:architect:1.0', 'P2_to_P3',
     0.25, 0.35, 0.25, 0.10, 0.05, TRUE),

    -- Tester 评价 Coder 的代码可测试性
    ('rule:dev:tester_reviews_coder', 'agent:tester:1.0', 'agent:coder:1.0', 'P3_to_P4',
     0.20, 0.35, 0.25, 0.15, 0.05, TRUE),

    -- Reviewer 评价 Coder 的代码质量
    ('rule:dev:reviewer_reviews_coder', 'agent:reviewer:1.0', 'agent:coder:1.0', 'P3_to_P4',
     0.15, 0.45, 0.20, 0.10, 0.10, TRUE),

    -- Docs 评价 Coder 的代码可文档化程度
    ('rule:dev:docs_reviews_coder', 'agent:docs:1.0', 'agent:coder:1.0', 'P4_to_P5',
     0.30, 0.30, 0.25, 0.10, 0.05, TRUE),

    -- Ops 评价 Coder 的代码可部署性
    ('rule:dev:ops_reviews_coder', 'agent:ops:1.0', 'agent:coder:1.0', 'P4_to_P5',
     0.25, 0.30, 0.30, 0.10, 0.05, TRUE),

    -- BenchmarkReporter 评价 Coder 的性能
    ('rule:dev:benchmark_reviews_coder', 'agent:benchmark-reporter:1.0', 'agent:coder:1.0', 'P4',
     0.20, 0.40, 0.20, 0.15, 0.05, TRUE),

    -- PM 评价 Tester 的测试覆盖
    ('rule:dev:pm_reviews_tester', 'agent:pm:1.0', 'agent:tester:1.0', 'P4_to_P5',
     0.30, 0.35, 0.20, 0.10, 0.05, TRUE),

    -- PM 评价 Reviewer 的审查质量
    ('rule:dev:pm_reviews_reviewer', 'agent:pm:1.0', 'agent:reviewer:1.0', 'P4_to_P5',
     0.25, 0.40, 0.20, 0.10, 0.05, TRUE),

    -- Secretary 评价所有 Agent (综合评定)
    ('rule:dev:secretary_reviews_researcher', 'agent:secretary:1.0', 'agent:researcher:1.0', 'final',
     0.30, 0.30, 0.20, 0.15, 0.05, TRUE),
    ('rule:dev:secretary_reviews_architect', 'agent:secretary:1.0', 'agent:architect:1.0', 'final',
     0.25, 0.35, 0.25, 0.10, 0.05, TRUE),
    ('rule:dev:secretary_reviews_coder', 'agent:secretary:1.0', 'agent:coder:1.0', 'final',
     0.20, 0.40, 0.20, 0.15, 0.05, TRUE),
    ('rule:dev:secretary_reviews_tester', 'agent:secretary:1.0', 'agent:tester:1.0', 'final',
     0.25, 0.35, 0.25, 0.10, 0.05, TRUE),
    ('rule:dev:secretary_reviews_reviewer', 'agent:secretary:1.0', 'agent:reviewer:1.0', 'final',
     0.20, 0.45, 0.20, 0.10, 0.05, TRUE),
    ('rule:dev:secretary_reviews_docs', 'agent:secretary:1.0', 'agent:docs:1.0', 'final',
     0.30, 0.30, 0.25, 0.10, 0.05, TRUE),
    ('rule:dev:secretary_reviews_ops', 'agent:secretary:1.0', 'agent:ops:1.0', 'final',
     0.25, 0.30, 0.30, 0.10, 0.05, TRUE);


-- ============================================================================
-- 5. 依赖关系
-- ============================================================================

INSERT OR REPLACE INTO sys_dependencies (from_resource, to_resource, dependency_type)
VALUES
    -- Agent 依赖 (流程顺序)
    ('agent:architect:1.0', 'agent:researcher:1.0', 'requires'),
    ('agent:coder:1.0', 'agent:architect:1.0', 'requires'),
    ('agent:tester:1.0', 'agent:coder:1.0', 'requires'),
    ('agent:reviewer:1.0', 'agent:coder:1.0', 'requires'),
    ('agent:docs:1.0', 'agent:coder:1.0', 'requires'),
    ('agent:ops:1.0', 'agent:coder:1.0', 'requires'),

    -- Skill 依赖 (enhances 表示增强关系)
    ('skill:commit:1.0', 'agent:coder:1.0', 'enhances'),
    ('skill:pr:1.0', 'skill:commit:1.0', 'requires'),
    ('skill:benchmark:1.0', 'agent:tester:1.0', 'enhances'),
    ('skill:test:1.0', 'agent:tester:1.0', 'enhances'),
    ('skill:review:1.0', 'agent:reviewer:1.0', 'enhances'),
    ('skill:build:1.0', 'agent:ops:1.0', 'enhances'),
    ('skill:docs:1.0', 'agent:docs:1.0', 'enhances');
