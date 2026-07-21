# Solar 本地处理层设计

> 版本: 1.0 | 日期: 2026-01-29 | 状态: 设计中

## 一、问题分析

### 当前 Token 消耗分布

| 任务类型 | 示例 | Token 消耗 | LLM 必要性 |
|----------|------|------------|------------|
| 字符界面渲染 | banner、status、宣告框 | 500-2000 | ❌ 不需要 |
| 状态读取/显示 | 项目装载、状态恢复 | 1000-3000 | ❌ 不需要 |
| 模式检测 | "我要开发"触发词 | 200-500 | ❌ 不需要 |
| 模板填充 | 固定格式输出 | 300-800 | ❌ 不需要 |
| Git 信息格式化 | branch、status、log | 500-1000 | ❌ 不需要 |
| 代码分析 | 架构理解、Bug定位 | 5000-20000 | ✅ 必须 |
| 代码生成 | 实现功能、修复Bug | 3000-15000 | ✅ 必须 |
| 技术决策 | 方案选择、权衡分析 | 2000-8000 | ✅ 必须 |

**潜在节省: 40-60% 的 routine Token 消耗**

### 核心思路

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户输入                                     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 Local Router (Hook)                                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 1. 解析输入                                                   │   │
│  │ 2. 匹配规则 (模式触发、命令、routine)                        │   │
│  │ 3. 决定路由: Local 处理 | LLM 处理 | 混合                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└───────────────┬───────────────────────────────────┬─────────────────┘
                │                                   │
        ┌───────▼───────┐                   ┌───────▼───────┐
        │  Local Engine │                   │   Claude LLM  │
        │  (无 Token)   │                   │  (需 Token)   │
        └───────┬───────┘                   └───────┬───────┘
                │                                   │
                ▼                                   ▼
        ┌─────────────┐                     ┌─────────────┐
        │ 直接输出    │                     │ AI 响应     │
        │ (界面/状态) │                     │ (分析/代码) │
        └─────────────┘                     └─────────────┘
```

## 二、架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Solar v3.0 架构                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ╔═══════════════════════════════════════════════════════════════╗  │
│  ║                   Layer 0: User Interface                     ║  │
│  ║  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              ║  │
│  ║  │ Banner  │ │ Status  │ │ Progress│ │ Alert   │              ║  │
│  ║  │ Renderer│ │ Display │ │ Bar     │ │ Box     │              ║  │
│  ║  └─────────┘ └─────────┘ └─────────┘ └─────────┘              ║  │
│  ║                    ▲ 100% Local                               ║  │
│  ╚════════════════════╪══════════════════════════════════════════╝  │
│                       │                                             │
│  ╔════════════════════╪══════════════════════════════════════════╗  │
│  ║            Layer 1: Local Processing Engine                   ║  │
│  ║  ┌─────────────────────────────────────────────────────────┐  ║  │
│  ║  │                   Solar Daemon                          │  ║  │
│  ║  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │  ║  │
│  ║  │  │ Command  │ │  State   │ │ Template │ │   UI     │   │  ║  │
│  ║  │  │ Router   │ │ Manager  │ │ Engine   │ │ Renderer │   │  ║  │
│  ║  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │  ║  │
│  ║  └─────────────────────────────────────────────────────────┘  ║  │
│  ║                    ▲ 100% Local (Bun/Deno)                    ║  │
│  ╚════════════════════╪══════════════════════════════════════════╝  │
│                       │                                             │
│  ╔════════════════════╪══════════════════════════════════════════╗  │
│  ║               Layer 2: Hook Integration                       ║  │
│  ║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          ║  │
│  ║  │ Session  │ │ Prompt   │ │ PreTool  │ │  Stop    │          ║  │
│  ║  │ Start    │ │ Submit   │ │ Use      │ │  Hook    │          ║  │
│  ║  └──────────┘ └──────────┘ └──────────┘ └──────────┘          ║  │
│  ║         │           │           │           │                 ║  │
│  ║         └───────────┴───────────┴───────────┘                 ║  │
│  ║                         │                                     ║  │
│  ║                         ▼                                     ║  │
│  ║              ┌─────────────────────┐                          ║  │
│  ║              │   solar-router.ts   │ ◀── 核心路由             ║  │
│  ║              └─────────────────────┘                          ║  │
│  ╚════════════════════════════════════════════════════════════════╝  │
│                       │                                             │
│  ╔════════════════════╪══════════════════════════════════════════╗  │
│  ║               Layer 3: LLM (Claude)                           ║  │
│  ║                       │                                       ║  │
│  ║         ┌─────────────┴─────────────┐                         ║  │
│  ║         ▼                           ▼                         ║  │
│  ║  ┌─────────────┐            ┌─────────────┐                   ║  │
│  ║  │ 思考任务   │            │ 执行任务    │                   ║  │
│  ║  │ (分析/决策)│            │ (代码/文档) │                   ║  │
│  ║  └─────────────┘            └─────────────┘                   ║  │
│  ╚════════════════════════════════════════════════════════════════╝  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 组件职责

| 组件 | 实现 | 职责 | Token 消耗 |
|------|------|------|------------|
| **UI Renderer** | TypeScript | 渲染所有字符界面 | 0 |
| **State Manager** | TypeScript | 读写 .solar/*.json | 0 |
| **Template Engine** | TypeScript | 模板变量替换 | 0 |
| **Command Router** | TypeScript | 命令分发决策 | 0 |
| **Solar Daemon** | Bun | 后台服务 (可选) | 0 |
| **Hooks** | Shell + TS | 事件拦截/注入 | 0 |
| **Claude LLM** | API | 复杂任务处理 | 按需 |

## 三、本地处理引擎设计

### 3.1 技术选型

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Bun** | 快速启动 (<10ms), TS 原生 | 需安装 | ⭐⭐⭐⭐⭐ |
| Deno | 安全, TS 原生 | 启动稍慢 | ⭐⭐⭐⭐ |
| Node.js | 普及度高 | 需编译 TS | ⭐⭐⭐ |
| Shell + jq | 无依赖 | 功能受限 | ⭐⭐ |

**选择: Bun** - 冷启动 <10ms, 原生支持 TypeScript

### 3.2 目录结构

```
~/.claude/solar/
├── engine/
│   ├── index.ts           # 入口
│   ├── router.ts          # 命令路由
│   ├── state.ts           # 状态管理
│   ├── renderer.ts        # UI 渲染
│   └── templates/         # 模板文件
│       ├── banner.txt
│       ├── status.txt
│       ├── agent-box.txt
│       └── project-load.txt
├── hooks/
│   ├── prompt-submit.ts   # 替代 .sh
│   ├── session-start.ts
│   └── pre-tool.ts
└── daemon/                # 可选: 后台服务
    ├── server.ts
    └── socket.ts
```

### 3.3 核心模块

#### 3.3.1 Router (路由器)

```typescript
// engine/router.ts

interface RouteResult {
  type: 'local' | 'llm' | 'hybrid';
  localOutput?: string;      // 本地输出
  systemMessage?: string;    // 注入 LLM
  blockLLM?: boolean;        // 阻止 LLM 调用
}

const PATTERNS = {
  // 完全本地处理 - 不需要 LLM
  local: [
    /^\/banner$/,
    /^\/status(\s+mini)?$/,
    /^\/stats$/,
    /^我要开发\s+(\S+)$/,
    /^我要办公$/,
  ],

  // 混合 - 本地渲染 + LLM 思考
  hybrid: [
    /^\/solar\s+start\s+(.+)$/,
    /^\/phase\s+(\S+)$/,
  ],

  // 纯 LLM
  llm: [
    // 其他所有
  ]
};

export function route(input: string): RouteResult {
  // 检查本地模式
  for (const pattern of PATTERNS.local) {
    const match = input.match(pattern);
    if (match) {
      return handleLocal(input, match);
    }
  }

  // 检查混合模式
  for (const pattern of PATTERNS.hybrid) {
    const match = input.match(pattern);
    if (match) {
      return handleHybrid(input, match);
    }
  }

  // 默认 LLM
  return { type: 'llm' };
}
```

#### 3.3.2 Renderer (UI 渲染器)

```typescript
// engine/renderer.ts

import { readFileSync } from 'fs';

interface RenderContext {
  project?: string;
  branch?: string;
  phase?: string;
  agent?: string;
  changes?: number;
  rateLimit?: number;
  [key: string]: any;
}

export class Renderer {
  private templates: Map<string, string> = new Map();

  constructor() {
    this.loadTemplates();
  }

  private loadTemplates() {
    const dir = '~/.claude/solar/engine/templates';
    const files = ['banner', 'status', 'agent-box', 'project-load'];
    for (const name of files) {
      this.templates.set(name, readFileSync(`${dir}/${name}.txt`, 'utf-8'));
    }
  }

  render(template: string, ctx: RenderContext): string {
    let output = this.templates.get(template) || '';

    // 变量替换
    for (const [key, value] of Object.entries(ctx)) {
      output = output.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), String(value));
    }

    // 条件块处理
    output = this.processConditionals(output, ctx);

    // 循环处理
    output = this.processLoops(output, ctx);

    return output;
  }

  // 进度条渲染
  progressBar(percent: number, width: number = 20): string {
    const filled = Math.round(width * percent / 100);
    const empty = width - filled;
    return '█'.repeat(filled) + '░'.repeat(empty);
  }

  // 状态颜色
  statusColor(status: string): string {
    const colors: Record<string, string> = {
      'ok': '🟢',
      'warning': '🟡',
      'error': '🔴',
      'active': '🔵'
    };
    return colors[status] || '⚪';
  }
}
```

#### 3.3.3 State Manager (状态管理)

```typescript
// engine/state.ts

import { readFileSync, writeFileSync, existsSync } from 'fs';

interface FlowState {
  version: string;
  active: boolean;
  task?: {
    description: string;
    complexity: 'simple' | 'medium' | 'complex';
  };
  flow: {
    current_phase: string;
    current_agent: string;
  };
  agent_announcement: {
    announced: boolean;
  };
}

interface ProjectState {
  project: string;
  version: string;
  phase: string;
  todos: string[];
}

export class StateManager {
  private basePath: string;

  constructor(projectPath: string = process.cwd()) {
    this.basePath = `${projectPath}/.solar`;
  }

  // 读取流程状态
  getFlowState(): FlowState | null {
    const path = `${this.basePath}/flow-state.json`;
    if (!existsSync(path)) return null;
    return JSON.parse(readFileSync(path, 'utf-8'));
  }

  // 更新流程状态
  updateFlowState(updates: Partial<FlowState>) {
    const current = this.getFlowState() || this.defaultFlowState();
    const merged = { ...current, ...updates };
    writeFileSync(`${this.basePath}/flow-state.json`, JSON.stringify(merged, null, 2));
  }

  // 读取项目状态
  getProjectState(): ProjectState | null {
    const path = `${this.basePath}/project-state.md`;
    if (!existsSync(path)) return null;
    return this.parseProjectStateMd(readFileSync(path, 'utf-8'));
  }

  // 获取 Git 信息
  async getGitInfo(): Promise<{branch: string, changes: number, lastCommit: string}> {
    const { execSync } = await import('child_process');
    const branch = execSync('git branch --show-current').toString().trim();
    const statusLines = execSync('git status --short').toString().split('\n').filter(Boolean);
    const lastCommit = execSync('git log --oneline -1').toString().trim();
    return { branch, changes: statusLines.length, lastCommit };
  }
}
```

### 3.4 模板文件

#### banner.txt

```
╭──────────────────────────────────────────────────────────────╮
│                                                              │
│    ☀️  S O L A R  v2.0    ·    Multi-Agent Dev Framework     │
│                                                              │
╰──────────────────────────────────────────────────────────────╯

     🔬 P1        🏗️ P2        💻 P3        🧪 P4        📦 P5
    Research     Design       Code        Verify       Final
       {{p1_mark}}            {{p2_mark}}            {{p3_mark}}            {{p4_mark}}            {{p5_mark}}

─────────────────────────────────────────────────────────────────
 📌 /save    📌 /restore    📌 /status    📌 /commit
─────────────────────────────────────────────────────────────────

 ⚡ Rate: {{rate_bar}} {{rate_percent}}%  {{rate_status}}
```

#### project-load.txt

```
┌─ ☀️ Solar ──────────────────────────────────────┐
│ 项目: {{project}}                               │
│ 路径: {{path}}                                  │
├─────────────────────────────────────────────────┤
│ 分支: {{branch}} | 变更: {{changes}}个文件      │
│ 最近: {{last_commit}}                           │
├─────────────────────────────────────────────────┤
{{#if phase}}
│ 阶段: {{phase}} | Agent: {{agent}}              │
│ 任务: {{task}}                                  │
{{/if}}
├─────────────────────────────────────────────────┤
{{#if todos}}
│ 待办:                                           │
{{#each todos}}
│   - {{this}}                                    │
{{/each}}
{{/if}}
├─────────────────────────────────────────────────┤
│ 关键文件:                                        │
{{#each key_files}}
│   - {{this}}                                    │
{{/each}}
└─────────────────────────────────────────────────┘
```

## 四、Hook 集成

### 4.1 UserPromptSubmit Hook (核心路由点)

```typescript
#!/usr/bin/env bun
// hooks/prompt-submit.ts

import { route } from '../engine/router';
import { Renderer } from '../engine/renderer';
import { StateManager } from '../engine/state';

const input = await Bun.stdin.text();
const data = JSON.parse(input);
const userPrompt = data.user_prompt || '';

const result = route(userPrompt);

switch (result.type) {
  case 'local':
    // 完全本地处理，直接输出
    console.log(JSON.stringify({
      continue: true,
      // 使用 systemMessage 输出结果
      systemMessage: `[Local Output]\n\n${result.localOutput}\n\n[不需要 LLM 响应]`
    }));
    break;

  case 'hybrid':
    // 混合模式：本地渲染 + LLM 补充
    console.log(JSON.stringify({
      continue: true,
      systemMessage: result.localOutput + '\n\n' + (result.systemMessage || '')
    }));
    break;

  case 'llm':
  default:
    // 纯 LLM 处理
    console.log(JSON.stringify({
      continue: true,
      systemMessage: result.systemMessage
    }));
}
```

### 4.2 命令拦截示例

```typescript
// engine/handlers/banner.ts

export async function handleBanner(): Promise<string> {
  const renderer = new Renderer();
  const state = new StateManager();

  // 获取动态数据
  const flowState = state.getFlowState();
  const rateLimit = await getRateLimit(); // 读取本地缓存

  const ctx = {
    p1_mark: flowState?.flow.current_phase === 'P1' ? '▼' : '║',
    p2_mark: flowState?.flow.current_phase === 'P2' ? '▼' : '║',
    p3_mark: flowState?.flow.current_phase === 'P3' ? '▼' : '║',
    p4_mark: flowState?.flow.current_phase === 'P4' ? '▼' : '║',
    p5_mark: flowState?.flow.current_phase === 'P5' ? '▼' : '║',
    rate_bar: renderer.progressBar(rateLimit, 16),
    rate_percent: rateLimit,
    rate_status: rateLimit > 80 ? '🔴' : rateLimit > 50 ? '🟡' : '🟢'
  };

  return renderer.render('banner', ctx);
}
```

## 五、"我要开发 <项目名>" 本地处理

### 5.1 完整流程

```typescript
// engine/handlers/project-load.ts

export async function handleProjectLoad(projectName: string): Promise<RouteResult> {
  const renderer = new Renderer();

  // 1. 查找项目路径 (本地)
  const projectPath = await findProjectPath(projectName);
  if (!projectPath) {
    return {
      type: 'local',
      localOutput: `❌ 未找到项目: ${projectName}`
    };
  }

  // 2. 获取 Git 信息 (本地)
  const state = new StateManager(projectPath);
  const git = await state.getGitInfo();

  // 3. 读取 Solar 状态 (本地)
  const projectState = state.getProjectState();
  const flowState = state.getFlowState();

  // 4. 读取关键文件列表 (本地)
  const keyFiles = await getRecentFiles(projectPath);

  // 5. 渲染输出 (本地)
  const output = renderer.render('project-load', {
    project: projectName,
    path: projectPath,
    branch: git.branch,
    changes: git.changes,
    last_commit: git.lastCommit,
    phase: flowState?.flow.current_phase,
    agent: flowState?.flow.current_agent,
    task: projectState?.task || '无',
    todos: projectState?.todos || [],
    key_files: keyFiles
  });

  // 6. 返回结果
  return {
    type: 'hybrid',
    localOutput: output,
    systemMessage: projectState?.todos?.length
      ? '检测到未完成任务，询问用户是否继续。'
      : '项目已装载，等待用户指令。'
  };
}

async function findProjectPath(name: string): Promise<string | null> {
  const paths = [
    `${process.env.HOME}/${name}`,
    `${process.env.HOME}/Projects/${name}`,
    `${process.env.HOME}/Code/${name}`,
  ];

  for (const p of paths) {
    if (await Bun.file(p).exists()) return p;
  }
  return null;
}
```

## 六、Daemon 模式 (可选)

### 6.1 为什么需要 Daemon

| 场景 | 无 Daemon | 有 Daemon |
|------|-----------|-----------|
| Hook 启动 | 每次冷启动 ~50ms | Unix socket ~5ms |
| 状态缓存 | 每次读文件 | 内存缓存 |
| 文件监听 | 不支持 | 实时监听 |
| 后台任务 | 不支持 | 支持 (如构建) |

### 6.2 Daemon 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Solar Daemon                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │   Socket    │    │   State     │    │   File      │             │
│  │   Server    │    │   Cache     │    │   Watcher   │             │
│  │ /tmp/solar  │    │  (Memory)   │    │  (chokidar) │             │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘             │
│         │                  │                  │                     │
│         └──────────────────┴──────────────────┘                     │
│                            │                                        │
│                            ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Request Handler                            │  │
│  │                                                               │  │
│  │  /banner  → render('banner', cache.get())                    │  │
│  │  /status  → render('status', cache.get())                    │  │
│  │  /state   → cache.getState()                                 │  │
│  │  /git     → cache.getGitInfo()                               │  │
│  │                                                               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.3 客户端调用

```typescript
// hooks/prompt-submit.ts (使用 Daemon)

import { connect } from 'net';

async function callDaemon(command: string, args: any): Promise<string> {
  return new Promise((resolve, reject) => {
    const socket = connect('/tmp/solar.sock');
    socket.write(JSON.stringify({ command, args }));
    socket.on('data', (data) => {
      resolve(data.toString());
      socket.end();
    });
    socket.on('error', reject);
  });
}

// 使用
const banner = await callDaemon('banner', {});
const projectInfo = await callDaemon('project-load', { name: 'ThunderDuck' });
```

## 七、可下压任务清单

### 7.1 完全本地 (100% 节省)

| 命令/触发词 | 当前处理 | 本地化后 |
|-------------|----------|----------|
| `/banner` | LLM 生成 | 模板渲染 |
| `/status` | LLM 生成 | 状态读取+渲染 |
| `/stats` | LLM 生成 | 本地统计 |
| `我要开发 <项目>` | LLM 装载 | 本地装载+渲染 |
| `我要办公` | LLM 显示 | 本地渲染 |
| 状态显示 | LLM 格式化 | 模板渲染 |
| Agent 宣告框 | LLM 生成 | 模板填充 |
| 进度条 | LLM 绘制 | 本地计算 |

### 7.2 混合模式 (部分节省)

| 命令 | 本地部分 | LLM 部分 |
|------|----------|----------|
| `/solar start <任务>` | 状态初始化+渲染 | 复杂度分析 |
| `/commit` | Git 信息收集+显示 | 提交信息生成 |
| `/pr` | PR 模板渲染 | 描述生成 |
| 项目装载 | 文件读取+状态显示 | 任务建议 |

### 7.3 必须 LLM

| 任务 | 原因 |
|------|------|
| 代码生成 | 需要理解+创造 |
| 代码分析 | 需要语义理解 |
| Bug 定位 | 需要推理 |
| 架构设计 | 需要决策 |
| 技术调研 | 需要综合分析 |

## 八、实现计划

| 阶段 | 任务 | 优先级 | 预计节省 |
|------|------|--------|----------|
| **Phase 1** | Bun 引擎骨架 + 路由 | P0 | - |
| **Phase 2** | UI 渲染器 + 模板 | P0 | 30% |
| **Phase 3** | 状态管理器 | P0 | 10% |
| **Phase 4** | `/banner`, `/status` 本地化 | P1 | 5% |
| **Phase 5** | `我要开发 <项目>` 本地化 | P1 | 10% |
| **Phase 6** | Agent 宣告框本地化 | P2 | 5% |
| **Phase 7** | Daemon 模式 (可选) | P3 | 响应速度 |

**总预计节省: 40-60% routine Token**

## 九、验收标准

- [ ] `/banner` 本地渲染，0 Token
- [ ] `/status` 本地渲染，0 Token
- [ ] `我要开发 X` 本地装载项目，仅必要时调用 LLM
- [ ] 状态框、宣告框等 UI 元素本地渲染
- [ ] Hook 响应时间 < 100ms
- [ ] 可选 Daemon 模式进一步加速

---

> 设计者: @Architect | 状态: 待审核
