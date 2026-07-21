#!/usr/bin/env python3
"""
Solar Shortcut Generator
分析需求、生成、验证并执行 Apple Shortcuts
"""

import json
import subprocess
import sys
import re
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from enum import Enum

class ActionType(Enum):
    GET_CLIPBOARD = "get_clipboard"
    SET_CLIPBOARD = "set_clipboard"
    GET_WEATHER = "get_weather"
    SPEAK_TEXT = "speak_text"
    SHOW_NOTIFICATION = "show_notification"
    OPEN_APP = "open_app"
    OPEN_URL = "open_url"
    ADD_REMINDER = "add_reminder"
    ADD_CALENDAR = "add_calendar"
    SEND_MESSAGE = "send_message"
    MAKE_CALL = "make_call"
    RUN_SHELL = "run_shell"
    GET_LOCATION = "get_location"

@dataclass
class ShortcutAction:
    action_type: ActionType
    params: Dict

@dataclass
class ShortcutDefinition:
    name: str
    description: str
    actions: List[ShortcutAction]
    trigger: Optional[Dict] = None
    siri_phrase: Optional[str] = None

# 关键词到动作的映射
KEYWORD_ACTION_MAP = {
    # 高优先级 - 系统操作
    ("提醒", "reminder", "别忘了", "记得"): ActionType.ADD_REMINDER,
    ("日历", "日程", "安排", "预约", "calendar"): ActionType.ADD_CALENDAR,
    ("消息", "短信", "发送", "告诉", "message", "sms"): ActionType.SEND_MESSAGE,
    ("电话", "打给", "呼叫", "call", "facetime"): ActionType.MAKE_CALL,
    ("天气", "weather", "温度", "下雨"): ActionType.GET_WEATHER,
    ("剪贴板", "clipboard", "复制的", "粘贴"): ActionType.GET_CLIPBOARD,
    ("播报", "说", "speak", "朗读", "读出"): ActionType.SPEAK_TEXT,
    ("通知", "notification", "提示"): ActionType.SHOW_NOTIFICATION,
    ("打开", "启动", "open", "launch"): ActionType.OPEN_APP,
    ("位置", "location", "在哪", "定位"): ActionType.GET_LOCATION,
}

# 触发类型关键词
TRIGGER_KEYWORDS = {
    "time": ["每天", "每周", "每月", "daily", "weekly", "点", "时", "早上", "晚上", "中午"],
    "location": ["到达", "离开", "arrive", "leave", "到家", "到公司", "回家"],
    "event": ["当", "如果", "when", "收到", "完成"],
}

def analyze_request(request: str) -> Tuple[bool, int, List[ActionType], Optional[Dict]]:
    """
    分析用户请求
    返回: (是否适合Shortcut, 分数, 动作列表, 触发配置)
    """
    request_lower = request.lower()
    score = 0
    actions = []
    trigger = None

    # 检测动作
    for keywords, action_type in KEYWORD_ACTION_MAP.items():
        for keyword in keywords:
            if keyword in request_lower:
                score += 3
                if action_type not in actions:
                    actions.append(action_type)
                break

    # 检测触发类型
    for trigger_type, keywords in TRIGGER_KEYWORDS.items():
        for keyword in keywords:
            if keyword in request_lower:
                trigger = {"type": trigger_type, "keyword": keyword}
                score += 2
                break
        if trigger:
            break

    # 如果有语音播报需求，添加 speak 动作
    if any(kw in request_lower for kw in ["告诉我", "播报", "说"]):
        if ActionType.SPEAK_TEXT not in actions:
            actions.append(ActionType.SPEAK_TEXT)

    suitable = score >= 3 and len(actions) > 0
    return suitable, score, actions, trigger

def generate_applescript(definition: ShortcutDefinition) -> str:
    """生成 AppleScript 代码"""
    script_parts = []

    for action in definition.actions:
        if action.action_type == ActionType.GET_CLIPBOARD:
            script_parts.append('set clipContent to the clipboard')

        elif action.action_type == ActionType.GET_WEATHER:
            # 使用 curl 获取天气
            script_parts.append('''
set weatherInfo to do shell script "curl -s 'wttr.in?format=3' 2>/dev/null || echo '无法获取天气'"
''')

        elif action.action_type == ActionType.SPEAK_TEXT:
            text = action.params.get("text", "")
            if text:
                script_parts.append(f'say "{text}"')
            else:
                # 使用之前获取的内容
                script_parts.append('say result')

        elif action.action_type == ActionType.SHOW_NOTIFICATION:
            title = action.params.get("title", "Solar")
            message = action.params.get("message", "")
            script_parts.append(f'''
display notification "{message}" with title "{title}"
''')

        elif action.action_type == ActionType.OPEN_APP:
            app_name = action.params.get("app", "")
            if app_name:
                script_parts.append(f'''
tell application "{app_name}" to activate
''')

        elif action.action_type == ActionType.ADD_REMINDER:
            title = action.params.get("title", "提醒")
            script_parts.append(f'''
tell application "Reminders"
    make new reminder with properties {{name:"{title}"}}
end tell
''')

        elif action.action_type == ActionType.GET_LOCATION:
            script_parts.append('''
set locationInfo to do shell script "curl -s 'ipinfo.io/json' | grep -E '(city|region|country)' || echo '无法获取位置'"
''')

        elif action.action_type == ActionType.RUN_SHELL:
            cmd = action.params.get("command", "echo 'Hello'")
            script_parts.append(f'''
set shellResult to do shell script "{cmd}"
''')

    return "\n".join(script_parts)

def create_shortcut_via_applescript(definition: ShortcutDefinition) -> bool:
    """通过 AppleScript 执行快捷指令逻辑"""
    script = generate_applescript(definition)

    if not script.strip():
        print(f"Warning: No actions to execute for {definition.name}")
        return False

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"✓ Executed: {definition.name}")
            if result.stdout:
                print(f"  Output: {result.stdout.strip()}")
            return True
        else:
            print(f"✗ Failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def run_existing_shortcut(name: str, input_json: Optional[str] = None) -> Tuple[bool, str]:
    """运行已存在的 Shortcut"""
    try:
        cmd = ["shortcuts", "run", name]
        if input_json:
            cmd.extend(["--input-type", "json"])
            result = subprocess.run(
                cmd,
                input=input_json,
                capture_output=True,
                text=True,
                timeout=60
            )
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr
    except Exception as e:
        return False, str(e)

def check_shortcut_exists(name: str) -> bool:
    """检查 Shortcut 是否存在"""
    try:
        result = subprocess.run(
            ["shortcuts", "list"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return name in result.stdout.split("\n")
    except:
        return False

def format_analysis_result(request: str, suitable: bool, score: int,
                          actions: List[ActionType], trigger: Optional[Dict]) -> str:
    """格式化分析结果"""
    output = []
    output.append("┌─────────────────────────────────────────────────────────────┐")
    output.append("│              🔍 SHORTCUT ANALYSIS                            │")
    output.append("├─────────────────────────────────────────────────────────────┤")
    output.append("│                                                             │")
    output.append(f"│  Request    {request[:45]:<45} │")
    output.append(f"│  Score      {score}/10 {'(推荐 Shortcut)' if suitable else '(可能需要其他方案)':^30} │")
    output.append("│                                                             │")

    if actions:
        output.append("│  Detected Actions:                                          │")
        for action in actions[:5]:
            output.append(f"│    • {action.value:<52} │")

    if trigger:
        output.append("│                                                             │")
        output.append(f"│  Trigger    {trigger['type']}: {trigger['keyword']:<40} │")

    output.append("│                                                             │")
    if suitable:
        output.append("│  Recommendation: ✓ 使用 Shortcut 实现                       │")
    else:
        output.append("│  Recommendation: △ 考虑使用 Skill 或 MCP                    │")
    output.append("│                                                             │")
    output.append("└───────────────────────────── [solar-dark] Powered by Solar ─┘")

    return "\n".join(output)

def main():
    if len(sys.argv) < 2:
        print("Usage: shortcut-generator.py <request> [--analyze] [--execute]")
        print("")
        print("Examples:")
        print("  shortcut-generator.py '告诉我今天天气'")
        print("  shortcut-generator.py '提醒我明天开会' --execute")
        print("  shortcut-generator.py '每天早上播报天气' --analyze")
        sys.exit(1)

    request = sys.argv[1]
    analyze_only = "--analyze" in sys.argv
    execute = "--execute" in sys.argv

    # 分析请求
    suitable, score, actions, trigger = analyze_request(request)

    # 输出分析结果
    print(format_analysis_result(request, suitable, score, actions, trigger))

    if analyze_only:
        sys.exit(0)

    if not suitable:
        print("\n⚠️  此需求可能更适合用 Skill 或 MCP 实现")
        sys.exit(0)

    if execute and actions:
        print("\n执行中...")

        # 创建动作列表
        shortcut_actions = []
        for action_type in actions:
            shortcut_actions.append(ShortcutAction(
                action_type=action_type,
                params={}
            ))

        # 创建定义
        definition = ShortcutDefinition(
            name=f"solar_temp_{hash(request) % 10000}",
            description=request,
            actions=shortcut_actions,
            trigger=trigger
        )

        # 执行
        success = create_shortcut_via_applescript(definition)
        if success:
            print("\n✅ 执行完成")
        else:
            print("\n❌ 执行失败")

if __name__ == "__main__":
    main()
