-- TVS Theme System - Seed Data
-- Version: 1.0
-- Description: 内置风格定义

-- ==================== 内置风格 ====================

-- 1. Solar Dark (默认)
INSERT OR REPLACE INTO tvs_themes (
    theme_id, name, description, author, version,
    color_scheme, border_style, colors, charset,
    card_style, table_style, progress_style, sparkline_style,
    is_builtin, is_active
) VALUES (
    'solar-dark',
    'Solar Dark',
    'Solar 默认深色主题 - 专业、现代',
    'Solar',
    '1.0',
    'dark',
    'single',
    '{
        "primary": "cyan",
        "secondary": "white",
        "accent": "yellow",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "muted": "gray",
        "background": "#1a1a2e",
        "foreground": "#eaeaea",
        "border": "white"
    }',
    '{
        "h_line": "─",
        "v_line": "│",
        "top_left": "┌",
        "top_right": "┐",
        "bottom_left": "└",
        "bottom_right": "┘",
        "t_down": "┬",
        "t_up": "┴",
        "t_right": "├",
        "t_left": "┤",
        "cross": "┼"
    }',
    '{"padding": 1, "margin": 0, "title_align": "left"}',
    '{"header_style": "bold", "row_separator": false, "column_padding": 1}',
    '{"fill_char": "█", "empty_char": "░", "show_percent": true}',
    '{"chars": "▁▂▃▄▅▆▇█", "width": 8}',
    TRUE,
    TRUE
);

-- 2. Solar Light
INSERT OR REPLACE INTO tvs_themes (
    theme_id, name, description, author, version,
    color_scheme, border_style, colors, charset,
    card_style, table_style, progress_style, sparkline_style,
    is_builtin, is_active
) VALUES (
    'solar-light',
    'Solar Light',
    'Solar 浅色主题 - 清新、明亮',
    'Solar',
    '1.0',
    'light',
    'single',
    '{
        "primary": "blue",
        "secondary": "black",
        "accent": "magenta",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "muted": "gray",
        "background": "#ffffff",
        "foreground": "#1a1a1a",
        "border": "gray"
    }',
    '{
        "h_line": "─",
        "v_line": "│",
        "top_left": "┌",
        "top_right": "┐",
        "bottom_left": "└",
        "bottom_right": "┘",
        "t_down": "┬",
        "t_up": "┴",
        "t_right": "├",
        "t_left": "┤",
        "cross": "┼"
    }',
    '{"padding": 1, "margin": 0, "title_align": "left"}',
    '{"header_style": "bold", "row_separator": false, "column_padding": 1}',
    '{"fill_char": "█", "empty_char": "░", "show_percent": true}',
    '{"chars": "▁▂▃▄▅▆▇█", "width": 8}',
    TRUE,
    FALSE
);

-- 3. Minimal
INSERT OR REPLACE INTO tvs_themes (
    theme_id, name, description, author, version,
    color_scheme, border_style, colors, charset,
    card_style, table_style, progress_style, sparkline_style,
    is_builtin, is_active
) VALUES (
    'minimal',
    'Minimal',
    '极简主题 - 无边框、纯文本',
    'Solar',
    '1.0',
    'dark',
    'none',
    '{
        "primary": "white",
        "secondary": "gray",
        "accent": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "muted": "gray",
        "background": "default",
        "foreground": "default",
        "border": "none"
    }',
    '{
        "h_line": " ",
        "v_line": " ",
        "top_left": " ",
        "top_right": " ",
        "bottom_left": " ",
        "bottom_right": " ",
        "t_down": " ",
        "t_up": " ",
        "t_right": " ",
        "t_left": " ",
        "cross": " "
    }',
    '{"padding": 0, "margin": 1, "title_align": "left"}',
    '{"header_style": "underline", "row_separator": false, "column_padding": 2}',
    '{"fill_char": "#", "empty_char": "-", "show_percent": true}',
    '{"chars": "▁▂▃▄▅▆▇█", "width": 8}',
    TRUE,
    FALSE
);

-- 4. Neon
INSERT OR REPLACE INTO tvs_themes (
    theme_id, name, description, author, version,
    color_scheme, border_style, colors, charset,
    card_style, table_style, progress_style, sparkline_style,
    is_builtin, is_active
) VALUES (
    'neon',
    'Neon',
    '霓虹主题 - 赛博朋克风格',
    'Solar',
    '1.0',
    'dark',
    'double',
    '{
        "primary": "magenta",
        "secondary": "cyan",
        "accent": "yellow",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "muted": "gray",
        "background": "#0d0221",
        "foreground": "#ff00ff",
        "border": "magenta"
    }',
    '{
        "h_line": "═",
        "v_line": "║",
        "top_left": "╔",
        "top_right": "╗",
        "bottom_left": "╚",
        "bottom_right": "╝",
        "t_down": "╦",
        "t_up": "╩",
        "t_right": "╠",
        "t_left": "╣",
        "cross": "╬"
    }',
    '{"padding": 1, "margin": 0, "title_align": "center"}',
    '{"header_style": "bold", "row_separator": true, "column_padding": 1}',
    '{"fill_char": "▓", "empty_char": "░", "show_percent": true}',
    '{"chars": "▁▂▃▄▅▆▇█", "width": 8}',
    TRUE,
    FALSE
);

-- 5. ASCII (兼容模式)
INSERT OR REPLACE INTO tvs_themes (
    theme_id, name, description, author, version,
    color_scheme, border_style, colors, charset,
    card_style, table_style, progress_style, sparkline_style,
    is_builtin, is_active
) VALUES (
    'ascii',
    'ASCII',
    '纯 ASCII 主题 - 最大兼容性',
    'Solar',
    '1.0',
    'dark',
    'ascii',
    '{
        "primary": "white",
        "secondary": "white",
        "accent": "white",
        "success": "white",
        "warning": "white",
        "error": "white",
        "muted": "white",
        "background": "default",
        "foreground": "default",
        "border": "white"
    }',
    '{
        "h_line": "-",
        "v_line": "|",
        "top_left": "+",
        "top_right": "+",
        "bottom_left": "+",
        "bottom_right": "+",
        "t_down": "+",
        "t_up": "+",
        "t_right": "+",
        "t_left": "+",
        "cross": "+"
    }',
    '{"padding": 1, "margin": 0, "title_align": "left"}',
    '{"header_style": "none", "row_separator": true, "column_padding": 1}',
    '{"fill_char": "#", "empty_char": ".", "show_percent": true}',
    '{"chars": ".-~=*#@", "width": 8}',
    TRUE,
    FALSE
);

-- 6. Rounded
INSERT OR REPLACE INTO tvs_themes (
    theme_id, name, description, author, version,
    color_scheme, border_style, colors, charset,
    card_style, table_style, progress_style, sparkline_style,
    is_builtin, is_active
) VALUES (
    'rounded',
    'Rounded',
    '圆角主题 - 柔和、现代',
    'Solar',
    '1.0',
    'dark',
    'rounded',
    '{
        "primary": "cyan",
        "secondary": "white",
        "accent": "green",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "muted": "gray",
        "background": "#1e1e2e",
        "foreground": "#cdd6f4",
        "border": "cyan"
    }',
    '{
        "h_line": "─",
        "v_line": "│",
        "top_left": "╭",
        "top_right": "╮",
        "bottom_left": "╰",
        "bottom_right": "╯",
        "t_down": "┬",
        "t_up": "┴",
        "t_right": "├",
        "t_left": "┤",
        "cross": "┼"
    }',
    '{"padding": 1, "margin": 0, "title_align": "left"}',
    '{"header_style": "bold", "row_separator": false, "column_padding": 1}',
    '{"fill_char": "●", "empty_char": "○", "show_percent": true}',
    '{"chars": "▁▂▃▄▅▆▇█", "width": 8}',
    TRUE,
    FALSE
);

-- 设置默认偏好
INSERT OR REPLACE INTO tvs_theme_preferences (context, theme_id, priority)
VALUES ('global', 'solar-dark', 100);
