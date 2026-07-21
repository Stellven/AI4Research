-- TVS Theme System - Schema
-- Version: 1.0
-- Description: TVS 风格切换系统 (遵循 IaST 铁律)

-- ==================== 风格注册表 ====================

-- 风格定义表
CREATE TABLE IF NOT EXISTS tvs_themes (
    theme_id TEXT PRIMARY KEY,              -- 'solar-dark', 'solar-light', 'minimal'
    name TEXT NOT NULL,                     -- 显示名称
    description TEXT,
    author TEXT DEFAULT 'Solar',
    version TEXT DEFAULT '1.0',

    -- 颜色方案
    color_scheme TEXT CHECK(color_scheme IN ('dark', 'light', 'auto')),

    -- 边框样式
    border_style TEXT DEFAULT 'single' CHECK(border_style IN ('single', 'double', 'rounded', 'bold', 'ascii', 'none')),

    -- 颜色定义 (ANSI / Hex)
    colors JSON NOT NULL,                   -- {"primary": "cyan", "secondary": "white", ...}

    -- 字符集
    charset JSON,                           -- {"h_line": "─", "v_line": "│", ...}

    -- 组件样式
    card_style JSON,                        -- {"padding": 1, "margin": 0, ...}
    table_style JSON,
    progress_style JSON,
    sparkline_style JSON,

    -- 状态
    is_builtin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 用户风格偏好
CREATE TABLE IF NOT EXISTS tvs_theme_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context TEXT NOT NULL,                  -- 'global', 'agent:coder', 'phase:P1', 'session:xxx'
    theme_id TEXT NOT NULL REFERENCES tvs_themes(theme_id),
    priority INTEGER DEFAULT 50,            -- 优先级，高优先
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(context)
);

-- 风格切换历史
CREATE TABLE IF NOT EXISTS tvs_theme_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_theme TEXT,
    to_theme TEXT NOT NULL,
    trigger_type TEXT,                      -- 'user', 'auto', 'schedule', 'context'
    trigger_source TEXT,                    -- 具体来源
    switched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ==================== 索引 ====================

CREATE INDEX IF NOT EXISTS idx_themes_active ON tvs_themes(is_active);
CREATE INDEX IF NOT EXISTS idx_themes_scheme ON tvs_themes(color_scheme);
CREATE INDEX IF NOT EXISTS idx_prefs_context ON tvs_theme_preferences(context);
CREATE INDEX IF NOT EXISTS idx_history_time ON tvs_theme_history(switched_at);

-- ==================== 视图 ====================

-- 当前激活风格
CREATE VIEW IF NOT EXISTS v_tvs_active_theme AS
SELECT
    t.*,
    COALESCE(p.context, 'global') AS active_context
FROM tvs_themes t
LEFT JOIN tvs_theme_preferences p ON t.theme_id = p.theme_id
WHERE t.is_active = TRUE
LIMIT 1;

-- 风格列表 (带使用统计)
CREATE VIEW IF NOT EXISTS v_tvs_theme_list AS
SELECT
    t.theme_id,
    t.name,
    t.description,
    t.color_scheme,
    t.border_style,
    t.is_builtin,
    t.is_active,
    COALESCE(h.usage_count, 0) AS usage_count,
    h.last_used
FROM tvs_themes t
LEFT JOIN (
    SELECT
        to_theme,
        COUNT(*) AS usage_count,
        MAX(switched_at) AS last_used
    FROM tvs_theme_history
    GROUP BY to_theme
) h ON t.theme_id = h.to_theme
ORDER BY t.is_active DESC, h.usage_count DESC, t.name;

-- ==================== 触发器 ====================

-- 切换风格时自动记录历史
CREATE TRIGGER IF NOT EXISTS tr_theme_switch_history
AFTER UPDATE ON tvs_themes
WHEN NEW.is_active = TRUE AND OLD.is_active = FALSE
BEGIN
    -- 记录切换历史
    INSERT INTO tvs_theme_history (from_theme, to_theme, trigger_type, trigger_source)
    SELECT
        (SELECT theme_id FROM tvs_themes WHERE is_active = TRUE AND theme_id != NEW.theme_id LIMIT 1),
        NEW.theme_id,
        'user',
        'theme_switch';

    -- 将其他风格设为非激活
    UPDATE tvs_themes SET is_active = FALSE WHERE theme_id != NEW.theme_id;
END;

-- 更新时间戳
CREATE TRIGGER IF NOT EXISTS tr_theme_updated
AFTER UPDATE ON tvs_themes
BEGIN
    UPDATE tvs_themes SET updated_at = CURRENT_TIMESTAMP WHERE theme_id = NEW.theme_id;
END;
