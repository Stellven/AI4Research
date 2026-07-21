# Solar UI Engine - 本地渲染引擎

> "LLM 说什么，引擎画什么"
> 零 Token 消耗的美观输出

## 核心理念

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   ❌ 传统方式 (消耗 Token)                                                      │
│   ════════════════════════                                                      │
│                                                                                 │
│   User ──▶ LLM ──▶ "生成一个漂亮的状态框" ──▶ LLM 输出 ASCII ──▶ 显示          │
│                    (消耗大量 Token 生成字符画)                                  │
│                                                                                 │
│   ✅ Solar 方式 (零 Token)                                                      │
│   ════════════════════════                                                      │
│                                                                                 │
│   User ──▶ LLM ──▶ 写入 UI 指令 ──▶ Daemon ──▶ UI Engine ──▶ 渲染输出         │
│                    { type: "banner",        监控文件       调用脚本              │
│                      data: {...} }          触发渲染       生成 ASCII           │
│                    (仅几十个 Token)                       (本地执行)             │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 架构设计

```
╭─────────────────────────────────────────────────────────────────────────────────╮
│                          🎨 Solar UI Engine                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                         UI Command Queue                                │   │
│   │                                                                         │   │
│   │    LLM writes ──▶  ~/.solar/ui/queue/*.json  ◀── Daemon watches        │   │
│   │                                                                         │   │
│   │    { "id": "...",                                                       │   │
│   │      "type": "banner",                                                  │   │
│   │      "template": "solar-banner",                                        │   │
│   │      "data": { "version": "3.0", "phase": "P3" },                       │   │
│   │      "timestamp": "..." }                                               │   │
│   │                                                                         │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                       │
│                                         ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                        Render Pipeline                                  │   │
│   │                                                                         │   │
│   │   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐           │   │
│   │   │ Template │──▶│  Data    │──▶│  Render  │──▶│  Output  │           │   │
│   │   │ Resolver │   │ Injector │   │  Engine  │   │ Formatter│           │   │
│   │   └──────────┘   └──────────┘   └──────────┘   └──────────┘           │   │
│   │                                                                         │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                       │
│                                         ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                       ASCII Art Libraries                               │   │
│   │                                                                         │   │
│   │   ╭─────────────╮  ╭─────────────╮  ╭─────────────╮  ╭─────────────╮   │   │
│   │   │   FIGlet    │  │   Cowsay    │  │ ascii-art   │  │   boxes     │   │   │
│   │   │  大字标题   │  │  对话气泡   │  │  图像转换   │  │  边框盒子   │   │   │
│   │   ╰─────────────╯  ╰─────────────╯  ╰─────────────╯  ╰─────────────╯   │   │
│   │                                                                         │   │
│   │   ╭─────────────╮  ╭─────────────╮  ╭─────────────╮  ╭─────────────╮   │   │
│   │   │   chalk     │  │   gradient  │  │  terminal   │  │   Custom    │   │   │
│   │   │  终端着色   │  │  渐变色彩   │  │  进度条     │  │   模板      │   │   │
│   │   ╰─────────────╯  ╰─────────────╯  ╰─────────────╯  ╰─────────────╯   │   │
│   │                                                                         │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
╰─────────────────────────────────────────────────────────────────────────────────╯
```

## UI 指令格式

### 基础结构

```typescript
interface UICommand {
  id: string;                    // 唯一标识
  type: UIType;                  // 渲染类型
  template?: string;             // 模板名称
  data: Record<string, any>;     // 动态数据
  style?: StyleOptions;          // 样式选项
  timestamp: string;
  priority?: 'low' | 'normal' | 'high';
}

type UIType =
  | 'banner'        // 大横幅
  | 'box'           // 信息盒子
  | 'status'        // 状态行
  | 'progress'      // 进度条
  | 'table'         // 表格
  | 'tree'          // 树形结构
  | 'figlet'        // 大字标题
  | 'cowsay'        // 对话气泡
  | 'alert'         // 警告框
  | 'list'          // 列表
  | 'card'          // 卡片
  | 'divider'       // 分隔线
  | 'custom';       // 自定义模板
```

### 示例指令

```json
// 1. Solar 启动横幅
{
  "id": "banner-001",
  "type": "banner",
  "template": "solar-startup",
  "data": {
    "version": "3.0",
    "mode": "development",
    "project": "ThunderDuck"
  },
  "style": {
    "color": "gradient",
    "gradient": ["#FFD700", "#FFA500"]
  }
}

// 2. Agent 宣告框
{
  "id": "announce-001",
  "type": "box",
  "template": "agent-announcement",
  "data": {
    "agent": "Coder",
    "emoji": "💻",
    "task": "实现 Hash Join 优化",
    "plan": [
      "分析当前实现",
      "设计 SIMD 方案",
      "编写测试用例"
    ]
  },
  "style": {
    "border": "rounded",
    "padding": 1
  }
}

// 3. 状态栏
{
  "id": "status-001",
  "type": "status",
  "data": {
    "phase": "P3",
    "agent": "Coder",
    "tokens": "+1.2K",
    "rate": 45,
    "status": "ok"
  }
}

// 4. 进度条
{
  "id": "progress-001",
  "type": "progress",
  "data": {
    "label": "Token Usage",
    "current": 4500,
    "total": 10000,
    "unit": "tokens"
  },
  "style": {
    "width": 40,
    "complete": "█",
    "incomplete": "░"
  }
}
```

## 模板系统

### 目录结构

```
~/.solar/ui/
├── queue/                    # UI 指令队列
│   └── *.json               # 待渲染指令
├── templates/               # 模板定义
│   ├── banners/
│   │   ├── solar-startup.tpl
│   │   ├── project-load.tpl
│   │   └── mode-switch.tpl
│   ├── boxes/
│   │   ├── agent-announcement.tpl
│   │   ├── status-box.tpl
│   │   ├── error-box.tpl
│   │   └── info-box.tpl
│   ├── components/
│   │   ├── progress-bar.tpl
│   │   ├── status-line.tpl
│   │   ├── table.tpl
│   │   └── tree.tpl
│   └── custom/              # 用户自定义模板
├── fonts/                   # FIGlet 字体
│   ├── standard.flf
│   ├── slant.flf
│   ├── banner.flf
│   └── ...
├── cows/                    # Cowsay 模板
│   ├── default.cow
│   ├── solar.cow
│   └── ...
└── themes/                  # 主题配置
    ├── default.json
    ├── dark.json
    └── light.json
```

### 模板语法

```handlebars
{{!-- templates/banners/solar-startup.tpl --}}

{{figlet "SOLAR" font="slant" color="gradient:#FFD700,#FFA500"}}

╭──────────────────────────────────────────────────────────────╮
│                                                              │
│    ☀️  S O L A R  v{{version}}    ·    {{mode}}              │
│                                                              │
╰──────────────────────────────────────────────────────────────╯

{{#if project}}
   📁 Project: {{project}}
   📍 Path: {{path}}
{{/if}}

{{progress label="Rate Limit" value=rate max=100 width=30}}

{{#each phases}}
   {{#if active}}[{{emoji}}]{{else}} {{emoji}} {{/if}} {{name}}
{{/each}}

─────────────────────────────────────────────────────────────────
 📌 /save    📌 /restore    📌 /status    📌 /commit
─────────────────────────────────────────────────────────────────
```

```handlebars
{{!-- templates/boxes/agent-announcement.tpl --}}

┌─ {{emoji}} {{agent}} {{repeat "─" (sub 45 (len agent))}}┐
│ Task: {{padEnd task 43}}│
│ Plan:                                           │
{{#each plan}}
│   {{add @index 1}}. {{padEnd this 40}}│
{{/each}}
└─────────────────────────────────────────────────┘
```

## 渲染引擎实现

### 核心类

```typescript
// core/engine/ui-engine.ts

import figlet from 'figlet';
import boxen from 'boxen';
import chalk from 'chalk';
import gradient from 'gradient-string';
import Table from 'cli-table3';
import ora from 'ora';
import { watch } from 'fs';

interface RenderResult {
  output: string;
  width: number;
  height: number;
}

export class UIEngine {
  private templates: Map<string, CompiledTemplate> = new Map();
  private theme: Theme;
  private renderers: Map<string, Renderer> = new Map();

  constructor(config: UIEngineConfig) {
    this.loadTemplates(config.templateDir);
    this.loadTheme(config.theme);
    this.registerBuiltinRenderers();
  }

  // ==================== 渲染器注册 ====================

  private registerBuiltinRenderers() {
    // FIGlet 大字
    this.register('figlet', async (data, style) => {
      const text = await figlet.text(data.text, {
        font: style?.font || 'Standard',
        horizontalLayout: 'default',
      });
      return this.colorize(text, style?.color);
    });

    // 盒子
    this.register('box', async (data, style) => {
      const content = this.renderTemplate(data.template, data);
      return boxen(content, {
        padding: style?.padding || 1,
        borderStyle: style?.border || 'round',
        borderColor: style?.borderColor,
        title: style?.title,
        titleAlignment: 'left',
      });
    });

    // 进度条
    this.register('progress', async (data, style) => {
      const { value, max, label, width = 30 } = data;
      const percent = Math.round((value / max) * 100);
      const filled = Math.round((width * value) / max);
      const empty = width - filled;

      const complete = style?.complete || '█';
      const incomplete = style?.incomplete || '░';

      const bar = complete.repeat(filled) + incomplete.repeat(empty);
      return `${label}: ${bar} ${percent}%`;
    });

    // 表格
    this.register('table', async (data, style) => {
      const table = new Table({
        head: data.headers,
        style: {
          head: style?.headColor ? [style.headColor] : ['cyan'],
        },
        ...style,
      });
      data.rows.forEach((row: any) => table.push(row));
      return table.toString();
    });

    // 状态行
    this.register('status', async (data) => {
      const { phase, agent, tokens, rate, status } = data;
      const statusIcon = this.getStatusIcon(status);
      const bar = this.miniProgressBar(rate, 10);
      return `[Solar] ${phase} | ${agent} | ${tokens} | Rate ${bar} ${rate}% ${statusIcon}`;
    });

    // 分隔线
    this.register('divider', async (data, style) => {
      const char = style?.char || '─';
      const width = style?.width || 60;
      const label = data.label;

      if (label) {
        const padding = Math.floor((width - label.length - 2) / 2);
        return char.repeat(padding) + ` ${label} ` + char.repeat(padding);
      }
      return char.repeat(width);
    });

    // Cowsay
    this.register('cowsay', async (data, style) => {
      const cowsay = await import('cowsay');
      return cowsay.say({
        text: data.text,
        f: style?.cow || 'default',
      });
    });

    // 树形结构
    this.register('tree', async (data, style) => {
      return this.renderTree(data.root, '', true, style);
    });

    // 列表
    this.register('list', async (data, style) => {
      const bullet = style?.bullet || '•';
      const indent = style?.indent || 2;
      return data.items
        .map((item: string, i: number) => {
          const prefix = style?.numbered ? `${i + 1}.` : bullet;
          return ' '.repeat(indent) + prefix + ' ' + item;
        })
        .join('\n');
    });

    // 警告框
    this.register('alert', async (data, style) => {
      const icons = {
        info: 'ℹ️',
        warning: '⚠️',
        error: '❌',
        success: '✅',
      };
      const colors = {
        info: 'blue',
        warning: 'yellow',
        error: 'red',
        success: 'green',
      };
      const type = data.type || 'info';
      const icon = icons[type];
      const color = colors[type];

      return boxen(`${icon}  ${data.message}`, {
        padding: 1,
        borderColor: color,
        borderStyle: 'round',
      });
    });
  }

  // ==================== 核心渲染 ====================

  async render(command: UICommand): Promise<RenderResult> {
    const renderer = this.renderers.get(command.type);
    if (!renderer) {
      throw new Error(`Unknown UI type: ${command.type}`);
    }

    // 如果有模板，先渲染模板
    let data = command.data;
    if (command.template) {
      const template = this.templates.get(command.template);
      if (template) {
        data = { ...data, _rendered: template(data) };
      }
    }

    const output = await renderer(data, command.style);

    // 计算尺寸
    const lines = output.split('\n');
    const height = lines.length;
    const width = Math.max(...lines.map(l => this.stripAnsi(l).length));

    return { output, width, height };
  }

  // ==================== 辅助方法 ====================

  private colorize(text: string, color?: string): string {
    if (!color) return text;

    if (color.startsWith('gradient:')) {
      const colors = color.replace('gradient:', '').split(',');
      return gradient(colors)(text);
    }

    if (color.startsWith('#')) {
      return chalk.hex(color)(text);
    }

    const chalkColor = (chalk as any)[color];
    return chalkColor ? chalkColor(text) : text;
  }

  private miniProgressBar(percent: number, width: number): string {
    const filled = Math.round(width * percent / 100);
    return '█'.repeat(filled) + '░'.repeat(width - filled);
  }

  private getStatusIcon(status: string): string {
    const icons: Record<string, string> = {
      ok: '🟢',
      warning: '🟡',
      error: '🔴',
      active: '🔵',
    };
    return icons[status] || '⚪';
  }

  private renderTree(
    node: TreeNode,
    prefix: string,
    isLast: boolean,
    style?: any
  ): string {
    const connector = isLast ? '└── ' : '├── ';
    const extension = isLast ? '    ' : '│   ';

    let result = prefix + connector + node.name + '\n';

    if (node.children) {
      node.children.forEach((child, index) => {
        const childIsLast = index === node.children!.length - 1;
        result += this.renderTree(child, prefix + extension, childIsLast, style);
      });
    }

    return result;
  }

  private stripAnsi(str: string): string {
    return str.replace(/\x1B\[[0-9;]*m/g, '');
  }

  // ==================== 模板方法 ====================

  register(type: string, renderer: Renderer) {
    this.renderers.set(type, renderer);
  }

  private loadTemplates(dir: string) {
    // 加载所有 .tpl 文件并编译
    // 使用 Handlebars 或自定义模板引擎
  }

  private loadTheme(themeName: string) {
    // 加载主题配置
  }
}

type Renderer = (data: any, style?: any) => Promise<string>;

interface TreeNode {
  name: string;
  children?: TreeNode[];
}
```

### Daemon 集成

```typescript
// core/daemon/ui-watcher.ts

import { watch, readFileSync, unlinkSync, existsSync, readdirSync } from 'fs';
import { UIEngine } from '../engine/ui-engine';

export class UIWatcher {
  private engine: UIEngine;
  private queueDir: string;

  constructor(engine: UIEngine, queueDir: string) {
    this.engine = engine;
    this.queueDir = queueDir;
  }

  start() {
    // 处理已存在的指令
    this.processExisting();

    // 监听新指令
    watch(this.queueDir, async (event, filename) => {
      if (!filename?.endsWith('.json')) return;

      const filepath = `${this.queueDir}/${filename}`;
      if (!existsSync(filepath)) return;

      try {
        await this.processCommand(filepath);
      } catch (e) {
        console.error(`UI render error: ${e}`);
      }
    });
  }

  private async processExisting() {
    const files = readdirSync(this.queueDir)
      .filter(f => f.endsWith('.json'))
      .sort(); // 按时间排序

    for (const file of files) {
      await this.processCommand(`${this.queueDir}/${file}`);
    }
  }

  private async processCommand(filepath: string) {
    const content = readFileSync(filepath, 'utf-8');
    const command = JSON.parse(content);

    // 渲染
    const result = await this.engine.render(command);

    // 输出到终端
    console.log(result.output);

    // 删除已处理的指令
    unlinkSync(filepath);

    // 记录到数据库
    // this.state.logMessage('ui', 'renderer', { command: command.id, type: command.type });
  }
}
```

### LLM 写入接口

```typescript
// 供 LLM 使用的简化接口
// LLM 只需写入 JSON 文件即可触发渲染

import { writeFileSync } from 'fs';
import { randomUUID } from 'crypto';

export function queueUI(command: Partial<UICommand>): string {
  const id = command.id || randomUUID();
  const fullCommand: UICommand = {
    id,
    type: command.type || 'box',
    data: command.data || {},
    style: command.style,
    timestamp: new Date().toISOString(),
    priority: command.priority || 'normal',
    ...command,
  };

  const filepath = `${process.env.HOME}/.solar/ui/queue/${id}.json`;
  writeFileSync(filepath, JSON.stringify(fullCommand, null, 2));

  return id;
}

// 便捷方法
export const ui = {
  banner: (data: any, style?: any) =>
    queueUI({ type: 'banner', data, style }),

  box: (data: any, style?: any) =>
    queueUI({ type: 'box', data, style }),

  status: (data: any) =>
    queueUI({ type: 'status', data }),

  progress: (label: string, value: number, max: number) =>
    queueUI({ type: 'progress', data: { label, value, max } }),

  alert: (type: string, message: string) =>
    queueUI({ type: 'alert', data: { type, message } }),

  figlet: (text: string, font?: string) =>
    queueUI({ type: 'figlet', data: { text }, style: { font } }),

  cowsay: (text: string, cow?: string) =>
    queueUI({ type: 'cowsay', data: { text }, style: { cow } }),

  table: (headers: string[], rows: any[][]) =>
    queueUI({ type: 'table', data: { headers, rows } }),

  divider: (label?: string) =>
    queueUI({ type: 'divider', data: { label } }),
};
```

## 预置模板

### Solar 启动横幅

```
  ██████╗  ██████╗ ██╗      █████╗ ██████╗
  ██╔════╝ ██╔═══██╗██║     ██╔══██╗██╔══██╗
  ███████╗ ██║   ██║██║     ███████║██████╔╝
  ╚════██║ ██║   ██║██║     ██╔══██║██╔══██╗
  ██████╔╝ ╚██████╔╝███████╗██║  ██║██║  ██║
  ╚═════╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝  v3.0

  ╭──────────────────────────────────────────────────────────────╮
  │                                                              │
  │    ☀️  Multi-Agent Development Framework                     │
  │                                                              │
  │    🧠 Brain    ❤️ Heart    🧬 Nerves    🦾 Limbs             │
  │                                                              │
  ╰──────────────────────────────────────────────────────────────╯

     🔬 P1        🏗️ P2        💻 P3        🧪 P4        📦 P5
    Research     Design       Code        Verify       Final

  ─────────────────────────────────────────────────────────────────
   ⚡ Rate: ████████░░░░░░░░ 45%  🟢 OK   💰 $3.50/$10.00
  ─────────────────────────────────────────────────────────────────
```

### 项目装载

```
  ╭─ ☀️ Solar ──────────────────────────────────────╮
  │                                                 │
  │  📁 Project: ThunderDuck                        │
  │  📍 Path: ~/ThunderDuck                         │
  │                                                 │
  ├─────────────────────────────────────────────────┤
  │  🌿 Branch: main                                │
  │  📝 Changes: 5 files                            │
  │  🕐 Last: feat: V45 TPC-H 优化                  │
  ├─────────────────────────────────────────────────┤
  │  📊 Phase: P3 实现                              │
  │  🤖 Agent: 💻 Coder                             │
  │  📋 Task: 优化加速比 <1.2x 的查询               │
  ├─────────────────────────────────────────────────┤
  │  📌 待办:                                       │
  │     • 实现 Q22 Bitmap Anti-Join                 │
  │     • 测试 V37 性能                             │
  │     • 更新文档                                  │
  ╰─────────────────────────────────────────────────╯
```

### Agent 宣告

```
  ┌─ 💻 Coder ─────────────────────────────────────┐
  │                                                │
  │  Task: 优化 Hash Join 性能                     │
  │                                                │
  │  Plan:                                         │
  │    1. 分析当前实现瓶颈                         │
  │    2. 设计 SIMD 加速方案                       │
  │    3. 实现并验证性能提升                       │
  │                                                │
  └────────────────────────────────────────────────┘
```

### 警告/错误框

```
  ╭─ ⚠️ Warning ───────────────────────────────────╮
  │                                                │
  │  G1 Gate 检查失败                              │
  │                                                │
  │  缺少设计文档 docs/*_DESIGN.md                 │
  │  请先完成设计文档再进入实现阶段                │
  │                                                │
  ╰────────────────────────────────────────────────╯

  ╭─ ❌ Error ─────────────────────────────────────╮
  │                                                │
  │  Daily budget exceeded: $10.00 / $10.00        │
  │                                                │
  │  Switching to low-cost model...                │
  │                                                │
  ╰────────────────────────────────────────────────╯
```

### Cowsay Solar 版

```
  ______________________________________
 / Solar: 代码已优化完成！              \
 | 性能提升 2.77x                       |
 \ 继续保持这种节奏 ☀️                  /
  --------------------------------------
         \   ^__^
          \  (oo)\_______
             (__)\       )\/\
              ☀️ ||----w |
                 ||     ||
```

## 依赖清单

```json
{
  "dependencies": {
    "figlet": "^1.7.0",
    "boxen": "^7.1.1",
    "chalk": "^5.3.0",
    "gradient-string": "^2.0.2",
    "cli-table3": "^0.6.3",
    "ora": "^7.0.1",
    "cowsay": "^1.5.0",
    "terminal-kit": "^3.0.1"
  }
}
```

## 安装脚本

```bash
#!/bin/bash
# install-ui-engine.sh

# 安装 Node 依赖
cd ~/.solar
npm init -y 2>/dev/null || true
npm install figlet boxen chalk gradient-string cli-table3 ora cowsay

# 安装 FIGlet 字体
mkdir -p ~/.solar/ui/fonts
cd ~/.solar/ui/fonts
curl -sLO https://github.com/xero/figlet-fonts/archive/refs/heads/master.zip
unzip -q master.zip
mv figlet-fonts-master/*.flf .
rm -rf figlet-fonts-master master.zip

# 创建目录结构
mkdir -p ~/.solar/ui/{queue,templates,cows,themes}
mkdir -p ~/.solar/ui/templates/{banners,boxes,components,custom}

echo "✅ UI Engine installed"
```

## 使用示例

### LLM 端 (写入指令)

```typescript
// LLM 只需要写入简单的 JSON
// 不需要关心如何渲染

// 显示启动横幅
ui.banner({
  version: '3.0',
  project: 'ThunderDuck',
  phase: 'P3',
  rate: 45
});

// 显示 Agent 宣告
ui.box({
  template: 'agent-announcement',
  agent: 'Coder',
  emoji: '💻',
  task: '实现 Hash Join 优化',
  plan: ['分析瓶颈', '设计方案', '编写代码']
});

// 显示进度
ui.progress('Token Usage', 4500, 10000);

// 显示警告
ui.alert('warning', 'G1 Gate 检查失败，请完成设计文档');
```

### Daemon 端 (自动渲染)

```
Daemon 监听 ~/.solar/ui/queue/ 目录
  ↓
发现新 JSON 文件
  ↓
解析 UI 指令
  ↓
调用 UIEngine.render()
  ↓
输出到终端
  ↓
删除已处理文件
```

---

> **核心原则:**
> - LLM 只负责"说什么" (写入数据)
> - 引擎负责"怎么画" (渲染 ASCII)
> - 零 Token 消耗美观输出
