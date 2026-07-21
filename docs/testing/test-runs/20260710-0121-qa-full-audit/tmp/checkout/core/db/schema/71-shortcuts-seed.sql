-- Solar Shortcuts Seed Data
-- Version: 1.0
-- Description: 预置的 AI OS Shortcuts

-- ==================== 系统操作类 ====================

INSERT OR REPLACE INTO sys_shortcuts (
    shortcut_id, name, description, category,
    trigger_phrases, siri_phrase, input_schema, output_schema,
    permission_level, requires_confirmation, supports_siri
) VALUES
-- 设置提醒
('solar_set_reminder', '设置提醒', '创建系统提醒事项', 'system',
 '["提醒我", "设个提醒", "别让我忘了"]',
 'Solar 提醒我',
 '{"type":"object","properties":{"title":{"type":"string"},"datetime":{"type":"string"},"notes":{"type":"string"}}}',
 '{"type":"object","properties":{"success":{"type":"boolean"},"reminder_id":{"type":"string"}}}',
 1, FALSE, TRUE),

-- 添加日历
('solar_add_calendar', '添加日历', '创建日历事件', 'system',
 '["安排", "添加日程", "预约", "约一下"]',
 'Solar 安排',
 '{"type":"object","properties":{"title":{"type":"string"},"start":{"type":"string"},"end":{"type":"string"},"location":{"type":"string"}}}',
 '{"type":"object","properties":{"success":{"type":"boolean"},"event_id":{"type":"string"}}}',
 1, FALSE, TRUE),

-- 发送消息
('solar_send_message', '发送消息', '发送 iMessage 或短信', 'system',
 '["发消息", "发短信", "告诉他"]',
 'Solar 发消息',
 '{"type":"object","properties":{"recipient":{"type":"string"},"content":{"type":"string"}}}',
 '{"type":"object","properties":{"success":{"type":"boolean"}}}',
 2, TRUE, TRUE),

-- 打电话
('solar_make_call', '打电话', '拨打电话', 'system',
 '["打电话", "呼叫", "call"]',
 'Solar 打电话',
 '{"type":"object","properties":{"contact":{"type":"string"},"type":{"type":"string","enum":["phone","facetime","facetime-audio"]}}}',
 '{"type":"object","properties":{"success":{"type":"boolean"}}}',
 2, TRUE, TRUE),

-- 控制智能家居
('solar_control_home', '控制智能家居', '控制 HomeKit 设备', 'system',
 '["打开", "关闭", "调节", "设置温度"]',
 'Solar 控制',
 '{"type":"object","properties":{"device":{"type":"string"},"action":{"type":"string"},"value":{"type":"string"}}}',
 '{"type":"object","properties":{"success":{"type":"boolean"}}}',
 1, FALSE, TRUE);

-- ==================== AI 处理类 ====================

INSERT OR REPLACE INTO sys_shortcuts (
    shortcut_id, name, description, category,
    trigger_phrases, siri_phrase, input_schema, output_schema,
    permission_level, requires_confirmation, supports_siri
) VALUES
-- 文本摘要
('solar_summarize', '文本摘要', '使用 AI 生成文本摘要', 'ai',
 '["总结", "摘要", "概括", "帮我看看"]',
 'Solar 总结',
 '{"type":"object","properties":{"text":{"type":"string"},"length":{"type":"string","enum":["short","medium","long"]}}}',
 '{"type":"object","properties":{"summary":{"type":"string"}}}',
 0, FALSE, TRUE),

-- 翻译
('solar_translate', '翻译', 'AI 翻译文本', 'ai',
 '["翻译", "translate", "用英语说"]',
 'Solar 翻译',
 '{"type":"object","properties":{"text":{"type":"string"},"target_language":{"type":"string"}}}',
 '{"type":"object","properties":{"translation":{"type":"string"}}}',
 0, FALSE, TRUE),

-- 图像分析
('solar_analyze_image', '分析图片', 'AI 分析图像内容', 'ai',
 '["看看这张图", "分析图片", "这是什么"]',
 'Solar 分析图片',
 '{"type":"object","properties":{"image":{"type":"string","description":"图片路径或URL"}}}',
 '{"type":"object","properties":{"description":{"type":"string"},"objects":{"type":"array"}}}',
 0, FALSE, TRUE),

-- 语音转文字
('solar_transcribe', '语音转文字', '将音频转为文本', 'ai',
 '["转录", "听写", "音频转文字"]',
 'Solar 转录',
 '{"type":"object","properties":{"audio":{"type":"string","description":"音频文件路径"}}}',
 '{"type":"object","properties":{"text":{"type":"string"}}}',
 0, FALSE, TRUE),

-- 生成文本
('solar_generate_text', '生成文本', 'AI 生成文本内容', 'ai',
 '["写一段", "生成", "帮我写"]',
 'Solar 写',
 '{"type":"object","properties":{"prompt":{"type":"string"},"style":{"type":"string"},"length":{"type":"integer"}}}',
 '{"type":"object","properties":{"text":{"type":"string"}}}',
 0, FALSE, TRUE);

-- ==================== 数据获取类 ====================

INSERT OR REPLACE INTO sys_shortcuts (
    shortcut_id, name, description, category,
    trigger_phrases, siri_phrase, input_schema, output_schema,
    permission_level, requires_confirmation, supports_siri
) VALUES
-- 获取剪贴板
('solar_get_clipboard', '获取剪贴板', '读取剪贴板内容', 'data',
 '["剪贴板", "刚才复制的"]',
 'Solar 剪贴板',
 '{}',
 '{"type":"object","properties":{"content":{"type":"string"},"type":{"type":"string"}}}',
 0, FALSE, TRUE),

-- 获取位置
('solar_get_location', '获取位置', '获取当前地理位置', 'data',
 '["我在哪", "当前位置", "这是哪"]',
 'Solar 位置',
 '{}',
 '{"type":"object","properties":{"address":{"type":"string"},"latitude":{"type":"number"},"longitude":{"type":"number"}}}',
 0, FALSE, TRUE),

-- 获取天气
('solar_get_weather', '获取天气', '查询天气信息', 'data',
 '["天气", "今天天气", "会下雨吗"]',
 'Solar 天气',
 '{"type":"object","properties":{"location":{"type":"string"},"days":{"type":"integer"}}}',
 '{"type":"object","properties":{"current":{"type":"object"},"forecast":{"type":"array"}}}',
 0, FALSE, TRUE),

-- 搜索文件
('solar_search_files', '搜索文件', '在系统中搜索文件', 'data',
 '["找一下", "搜索文件", "文件在哪"]',
 'Solar 搜索文件',
 '{"type":"object","properties":{"query":{"type":"string"},"type":{"type":"string"}}}',
 '{"type":"object","properties":{"files":{"type":"array"}}}',
 0, FALSE, TRUE);

-- ==================== 工作流类 ====================

INSERT OR REPLACE INTO sys_shortcuts (
    shortcut_id, name, description, category,
    trigger_phrases, siri_phrase, input_schema, output_schema,
    permission_level, requires_confirmation, supports_siri
) VALUES
-- 早间简报
('solar_morning_briefing', '早间简报', '播报今日天气、日程、邮件摘要', 'workflow',
 '["早安", "早上好", "今天有什么"]',
 'Solar 早安',
 '{}',
 '{"type":"object","properties":{"weather":{"type":"object"},"events":{"type":"array"},"emails":{"type":"array"}}}',
 0, FALSE, TRUE),

-- 日终总结
('solar_end_of_day', '日终总结', '总结今天完成的任务', 'workflow',
 '["今天完成了什么", "日终", "收工"]',
 'Solar 日终',
 '{}',
 '{"type":"object","properties":{"completed":{"type":"array"},"pending":{"type":"array"}}}',
 0, FALSE, TRUE),

-- 会议准备
('solar_meeting_prep', '会议准备', '准备即将到来的会议', 'workflow',
 '["准备会议", "下个会议"]',
 'Solar 会议',
 '{"type":"object","properties":{"meeting_id":{"type":"string"}}}',
 '{"type":"object","properties":{"meeting":{"type":"object"},"participants":{"type":"array"},"docs":{"type":"array"}}}',
 0, FALSE, TRUE),

-- 出行模式
('solar_travel_mode', '出行模式', '启动出行相关自动化', 'workflow',
 '["我要出门", "出发", "导航到"]',
 'Solar 出行',
 '{"type":"object","properties":{"destination":{"type":"string"}}}',
 '{"type":"object","properties":{"eta":{"type":"string"},"route":{"type":"object"}}}',
 1, FALSE, TRUE),

-- Solar 路由器 (核心)
('solar_router', 'Solar 路由器', '自然语言意图路由到具体 Shortcut', 'workflow',
 '["Solar", "帮我"]',
 'Solar',
 '{"type":"object","properties":{"query":{"type":"string"}}}',
 '{"type":"object","properties":{"routed_to":{"type":"string"},"result":{"type":"object"}}}',
 0, FALSE, TRUE);

-- ==================== 意图映射 ====================

INSERT OR REPLACE INTO sys_intent_shortcut_map (intent_pattern, shortcut_id, priority, param_mapping) VALUES
-- 提醒类
('remind:*', 'solar_set_reminder', 100, '{"title":"$object","datetime":"$time"}'),
('remind_me:*', 'solar_set_reminder', 100, '{"title":"$object","datetime":"$time"}'),

-- 日程类
('schedule:*', 'solar_add_calendar', 100, '{"title":"$object","start":"$time"}'),
('arrange:*', 'solar_add_calendar', 90, '{"title":"$object","start":"$time"}'),

-- 通信类
('send_message:*', 'solar_send_message', 100, '{"recipient":"$target","content":"$content"}'),
('call:*', 'solar_make_call', 100, '{"contact":"$target"}'),

-- AI 类
('summarize:*', 'solar_summarize', 100, '{"text":"$object"}'),
('translate:*', 'solar_translate', 100, '{"text":"$object","target_language":"$target"}'),
('write:*', 'solar_generate_text', 100, '{"prompt":"$object"}'),

-- 查询类
('weather:*', 'solar_get_weather', 100, '{"location":"$location"}'),
('search_file:*', 'solar_search_files', 100, '{"query":"$object"}'),

-- 工作流类
('morning:*', 'solar_morning_briefing', 100, '{}'),
('end_day:*', 'solar_end_of_day', 100, '{}');
