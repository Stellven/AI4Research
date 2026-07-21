# Solar Terminal Visual System (TVS) - 架构设计

> **核心理念**: 把"用户意图"编译成"有设计感、有层级、有审美约束的终端视觉"
>
> **不是画画，是 编译 + 排版 + 视觉系统**

---

## 一、设计哲学

### 1.1 关键约束

| 原则 | 说明 |
|------|------|
| **LLM 不画画** | LLM 只生成结构化语义，渲染交给确定性程序 |
| **语义优先** | 描述"是什么"，不是"画什么" |
| **排版驱动** | 所有美感来自 layout，不来自手工对齐 |
| **确定性** | 同一 DSL 永远同一输出 |
| **可组合** | 原子组件 → 复合组件 → 页面 |

### 1.2 类比

```
Web 世界                    Terminal 世界
─────────────────────────────────────────────
HTML (结构)           →     Semantic IR
CSS (样式)            →     Style System
DOM (树)              →     Layout DSL
Browser Render        →     Glyph Renderer
Viewport              →     Terminal Canvas
```

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER INTENT                                │
│         自然语言 / 结构化数据 / API 调用 / Skill 触发                      │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         SEMANTIC COMPILER                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │   Intent    │ →  │  Semantic   │ →  │   Layout    │                 │
│  │   Parser    │    │     IR      │    │  Compiler   │                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│                                                                         │
│  职责: 理解意图 → 选择组件 → 生成版式                                      │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           LAYOUT DSL                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  {                                                               │   │
│  │    "canvas": { "width": 64, "padding": 1 },                     │   │
│  │    "style": "enterprise_minimal",                                │   │
│  │    "root": { "type": "card", "sections": [...] }                │   │
│  │  }                                                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  特点: 纯语义 / 无字符 / 可序列化 / 可缓存                                 │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          RENDER PIPELINE                                │
│                                                                         │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐        │
│  │  Style    │ → │  Layout   │ → │  Glyph    │ → │  Output   │        │
│  │  Resolve  │   │  Engine   │   │  Mapper   │   │  Buffer   │        │
│  └───────────┘   └───────────┘   └───────────┘   └───────────┘        │
│                                                                         │
│  Style Resolve: 合并样式 Token                                          │
│  Layout Engine: 计算盒模型 / 栅格 / 对齐                                  │
│  Glyph Mapper:  语义 → Unicode 字符                                     │
│  Output Buffer: ANSI 颜色 / 流式输出                                     │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          TERMINAL OUTPUT                                │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │               SYSTEM STATUS                                       │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ Service   │ Inference Engine                                      │  │
│  │ Latency   │ 12 ms                                                 │  │
│  │ Load      │ ██████▊░░░░░░░░░░░░░░░░░░░░░░░░ 72%                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 三、Semantic IR (语义中间表示)

### 3.1 设计目标

Semantic IR 是 LLM 输出的目标格式，必须满足：

1. **高层抽象** - 不涉及任何渲染细节
2. **意图驱动** - 表达"要展示什么"，不是"怎么展示"
3. **易于生成** - LLM 能稳定生成正确 JSON
4. **可验证** - JSON Schema 严格校验

### 3.2 IR 结构

```typescript
interface SemanticIR {
  // 元信息
  meta?: {
    title?: string;
    description?: string;
    timestamp?: string;
  };

  // 画布约束
  canvas?: {
    width?: number | "auto" | "full";    // 宽度
    maxWidth?: number;                    // 最大宽度
    minWidth?: number;                    // 最小宽度
  };

  // 样式选择
  style?: string | StyleOverrides;        // 预设名 或 覆盖

  // 根组件 (唯一入口)
  root: Component;
}
```

### 3.3 Component 类型体系

```typescript
// ==================== 基础类型 ====================

type Component =
  | TextComponent
  | HeadingComponent
  | DividerComponent
  | SpacerComponent
  | KVComponent
  | ListComponent
  | TableComponent
  | BarComponent
  | SparklineComponent
  | TreeComponent
  | CodeComponent
  | CardComponent
  | GridComponent
  | StackComponent
  | ConditionalComponent;

// ==================== 原子组件 ====================

interface TextComponent {
  type: "text";
  content: string;
  align?: "left" | "center" | "right";
  wrap?: boolean;
  truncate?: boolean | number;
  emphasis?: "normal" | "bold" | "dim" | "italic";
}

interface HeadingComponent {
  type: "heading";
  level: 1 | 2 | 3;                      // h1 最大，h3 最小
  text: string;
  align?: "left" | "center" | "right";
}

interface DividerComponent {
  type: "divider";
  variant?: "solid" | "dashed" | "double" | "thick";
  label?: string;                         // 分隔线中的文字
}

interface SpacerComponent {
  type: "spacer";
  size?: number;                          // 空行数
}

// ==================== 数据组件 ====================

interface KVComponent {
  type: "kv";
  items: KVItem[];
  layout?: "stacked" | "inline" | "table";
}

interface KVItem {
  key: string;
  value?: string | number;
  bar?: number;                           // 0-1，显示为进度条
  status?: "success" | "warning" | "error" | "info";
  unit?: string;
}

interface ListComponent {
  type: "list";
  items: (string | ListItem)[];
  variant?: "bullet" | "numbered" | "checkbox" | "arrow";
  compact?: boolean;
}

interface ListItem {
  text: string;
  checked?: boolean;                      // checkbox 模式
  indent?: number;                        // 缩进层级
  status?: "success" | "warning" | "error";
}

interface TableComponent {
  type: "table";
  columns: TableColumn[];
  rows: (string | number | null)[][];
  compact?: boolean;
  zebra?: boolean;                        // 斑马纹
}

interface TableColumn {
  key: string;
  label?: string;
  align?: "left" | "center" | "right";
  width?: number | "auto" | "fill";
}

// ==================== 可视化组件 ====================

interface BarComponent {
  type: "bar";
  value: number;                          // 0-1 或 实际值
  max?: number;                           // 若提供则 value/max
  label?: string;
  showPercent?: boolean;
  showValue?: boolean;
  variant?: "block" | "shade" | "braille";
}

interface SparklineComponent {
  type: "sparkline";
  data: number[];
  variant?: "line" | "bar" | "dot";
  width?: number;
  height?: number;                        // 1-4 行高
}

interface TreeComponent {
  type: "tree";
  root: TreeNode;
  expanded?: boolean;                     // 默认展开
  showGuides?: boolean;                   // 显示连接线
}

interface TreeNode {
  label: string;
  children?: TreeNode[];
  icon?: string;
  status?: "success" | "warning" | "error";
}

// ==================== 代码组件 ====================

interface CodeComponent {
  type: "code";
  content: string;
  language?: string;
  lineNumbers?: boolean;
  highlight?: number[];                   // 高亮行
}

// ==================== 容器组件 ====================

interface CardComponent {
  type: "card";
  header?: string | HeadingComponent;
  footer?: string;
  sections: Component[];
  variant?: "bordered" | "minimal" | "elevated";
}

interface GridComponent {
  type: "grid";
  columns: number | number[];             // 等宽列数 或 各列宽度比例
  gap?: number;
  items: Component[];
}

interface StackComponent {
  type: "stack";
  direction?: "vertical" | "horizontal";
  gap?: number;
  items: Component[];
}

// ==================== 逻辑组件 ====================

interface ConditionalComponent {
  type: "conditional";
  condition: string;                      // 条件表达式
  then: Component;
  else?: Component;
}
```

### 3.4 IR 示例

```json
{
  "meta": { "title": "System Dashboard" },
  "canvas": { "width": 64 },
  "style": "enterprise_minimal",
  "root": {
    "type": "card",
    "header": { "type": "heading", "level": 1, "text": "SYSTEM STATUS", "align": "center" },
    "sections": [
      {
        "type": "kv",
        "layout": "table",
        "items": [
          { "key": "Service", "value": "Inference Engine" },
          { "key": "Version", "value": "3.2.1" },
          { "key": "Latency", "value": 12, "unit": "ms", "status": "success" },
          { "key": "Load", "bar": 0.72, "status": "warning" }
        ]
      },
      { "type": "divider" },
      {
        "type": "sparkline",
        "data": [0.2, 0.3, 0.5, 0.4, 0.6, 0.8, 0.7, 0.72],
        "variant": "bar",
        "height": 2
      }
    ]
  }
}
```

---

## 四、Layout DSL (版式领域语言)

### 4.1 从 Semantic IR 到 Layout DSL

Layout DSL 是 Semantic IR 的"编译产物"，加入了具体的排版信息。

```typescript
interface LayoutDSL {
  canvas: CanvasLayout;
  tree: LayoutNode;
}

interface CanvasLayout {
  width: number;                          // 实际宽度 (已计算)
  height: number;                         // 实际高度 (已计算)
  padding: BoxSpacing;
}

interface BoxSpacing {
  top: number;
  right: number;
  bottom: number;
  left: number;
}
```

### 4.2 Layout Node

```typescript
interface LayoutNode {
  // 身份
  id: string;
  componentType: string;                  // 原始组件类型

  // 盒模型 (已计算)
  box: {
    x: number;                            // 相对父容器
    y: number;
    width: number;
    height: number;
    padding: BoxSpacing;
    margin: BoxSpacing;
  };

  // 边框
  border?: {
    style: "none" | "single" | "double" | "rounded" | "thick" | "dashed";
    sides: { top: boolean; right: boolean; bottom: boolean; left: boolean };
  };

  // 内容 (根据类型不同)
  content?: LayoutContent;

  // 子节点
  children?: LayoutNode[];
}

// 内容类型
type LayoutContent =
  | { type: "text"; lines: TextLine[] }
  | { type: "bar"; segments: BarSegment[] }
  | { type: "divider"; char: string; label?: LabelPosition }
  | { type: "empty" };

interface TextLine {
  text: string;
  align: "left" | "center" | "right";
  emphasis?: "normal" | "bold" | "dim";
}

interface BarSegment {
  char: string;                           // █ ▊ ░ etc
  count: number;
  color?: string;
}

interface LabelPosition {
  text: string;
  position: number;                       // 起始位置
}
```

### 4.3 Layout 算法

```
┌─────────────────────────────────────────────────────────────┐
│                    LAYOUT ALGORITHM                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Measure Pass (测量)                                      │
│     └─ 计算每个节点的 intrinsic size                         │
│        └─ 文本: 行数 × max(行宽)                            │
│        └─ 容器: 子节点尺寸 + padding + border               │
│                                                             │
│  2. Constraint Pass (约束)                                   │
│     └─ 从根节点向下传播 available width                       │
│        └─ 处理 auto / fill / fixed 宽度                     │
│        └─ 计算 grid 列宽分配                                 │
│                                                             │
│  3. Layout Pass (定位)                                       │
│     └─ 计算每个节点的 (x, y) 坐标                           │
│        └─ Stack: 垂直/水平堆叠                              │
│        └─ Grid: 栅格定位                                    │
│        └─ 对齐: left/center/right                           │
│                                                             │
│  4. Finalize (完成)                                         │
│     └─ 生成 LayoutDSL                                       │
│     └─ 计算 canvas.height                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、Style System (样式系统)

### 5.1 设计 Token

Style 不是"换字符"，是一整套设计约束。

```typescript
interface StyleDefinition {
  // ===== 元信息 =====
  name: string;
  description?: string;

  // ===== 字符集 =====
  charset: {
    // 边框字符
    border: {
      single:  { tl: "┌", tr: "┐", bl: "└", br: "┘", h: "─", v: "│", cross: "┼", ... };
      double:  { tl: "╔", tr: "╗", bl: "╚", br: "╝", h: "═", v: "║", cross: "╬", ... };
      rounded: { tl: "╭", tr: "╮", bl: "╰", br: "╯", h: "─", v: "│", ... };
      thick:   { tl: "┏", tr: "┓", bl: "┗", br: "┛", h: "━", v: "┃", ... };
      dashed:  { h: "┄", v: "┆", ... };
    };

    // 密度块
    blocks: {
      full:    ["█"];
      shade:   ["░", "▒", "▓", "█"];
      eighth:  ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"];
      braille: ["⠀", "⣀", "⣤", "⣶", "⣿"];               // 点阵
    };

    // 列表符号
    bullets: {
      bullet:   "•";
      arrow:    "→";
      check:    "✓";
      cross:    "✗";
      dash:     "─";
    };

    // 状态图标
    status: {
      success: "✓";
      warning: "⚠";
      error:   "✗";
      info:    "ℹ";
      pending: "○";
      active:  "●";
    };
  };

  // ===== 排版 =====
  typography: {
    headingTransform: "uppercase" | "none";
    headingAlign: "left" | "center";
    textWrap: boolean;
    maxLineWidth: number;
  };

  // ===== 间距 =====
  spacing: {
    density: "compact" | "normal" | "airy";
    sectionGap: number;
    itemGap: number;
    padding: {
      card: BoxSpacing;
      section: BoxSpacing;
    };
  };

  // ===== 边框 =====
  borders: {
    card: "single" | "double" | "rounded" | "thick" | "none";
    table: "single" | "minimal" | "none";
    divider: "solid" | "dashed" | "double";
  };

  // ===== 颜色 (ANSI) =====
  colors?: {
    heading: string;
    text: string;
    muted: string;
    border: string;
    success: string;
    warning: string;
    error: string;
    accent: string;
  };

  // ===== 进度条 =====
  bars: {
    variant: "block" | "shade" | "braille";
    width: number;
    showPercent: boolean;
  };
}
```

### 5.2 预设样式

#### enterprise_minimal
```
┌──────────────────────────────────────────────────────────────┐
│                       SYSTEM STATUS                          │
├──────────────────────────────────────────────────────────────┤
│ Service   │ Inference Engine                                 │
│ Latency   │ 12 ms                                      ✓     │
│ Load      │ ██████████████████████░░░░░░░░░░░░░░░░░░   72%  │
└──────────────────────────────────────────────────────────────┘
```

```json
{
  "name": "enterprise_minimal",
  "charset": {
    "border": "single",
    "blocks": "eighth"
  },
  "typography": {
    "headingTransform": "uppercase",
    "headingAlign": "center"
  },
  "spacing": {
    "density": "normal",
    "padding": { "card": { "top": 0, "right": 1, "bottom": 0, "left": 1 } }
  },
  "borders": {
    "card": "single",
    "table": "minimal"
  }
}
```

#### research_report
```
SYSTEM STATUS
────────────────────────────────────────────────────────────────

  Service     Inference Engine
  Latency     12 ms ✓
  Load        ██████████████████████░░░░░░░░░░░░░░░░░░ 72%

────────────────────────────────────────────────────────────────
```

```json
{
  "name": "research_report",
  "typography": {
    "headingTransform": "uppercase",
    "headingAlign": "left"
  },
  "spacing": {
    "density": "airy"
  },
  "borders": {
    "card": "none",
    "divider": "solid"
  }
}
```

#### cyber
```
╔══════════════════════════════════════════════════════════════╗
║                    ▓▓ SYSTEM STATUS ▓▓                       ║
╠══════════════════════════════════════════════════════════════╣
║ Service   ║ Inference Engine                                 ║
║ Latency   ║ 12 ms                                            ║
║ Load      ║ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░  72%   ║
╚══════════════════════════════════════════════════════════════╝
```

#### solar_default
```
╭──────────────────────────────────────────────────────────────╮
│                    ☀️ SYSTEM STATUS                          │
├──────────────────────────────────────────────────────────────┤
│ Service   │ Inference Engine                                 │
│ Latency   │ 12 ms                                      ✓     │
│ Load      │ ████████████████░░░░░░░░░░░░░░░░░░░░░░░░   72%  │
╰──────────────────────────────────────────────────────────────╯
```

### 5.3 样式继承与覆盖

```typescript
// 样式可以继承
interface StyleDefinition {
  extends?: string;                       // 基础样式
  overrides?: Partial<StyleDefinition>;   // 覆盖项
}

// 运行时合并
function resolveStyle(name: string, overrides?: StyleOverrides): StyleDefinition {
  const base = styleRegistry.get(name);
  if (base.extends) {
    const parent = resolveStyle(base.extends);
    return deepMerge(parent, base, overrides);
  }
  return deepMerge(base, overrides);
}
```

---

## 六、Glyph Renderer (字形渲染器)

### 6.1 渲染流水线

```
LayoutDSL + ResolvedStyle
         │
         ▼
┌─────────────────────┐
│   Canvas Allocator  │  ← 分配字符画布 (2D array)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   Node Renderer     │  ← 递归渲染每个 LayoutNode
│   ┌───────────────┐ │
│   │ Border        │ │  ← 先画边框
│   │ Content       │ │  ← 再填内容
│   │ Children      │ │  ← 递归子节点
│   └───────────────┘ │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   Glyph Mapper      │  ← 语义 → 实际 Unicode
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   ANSI Colorizer    │  ← 添加颜色转义码 (可选)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   String Builder    │  ← 输出最终字符串
└─────────────────────┘
```

### 6.2 Canvas (画布)

```typescript
class Canvas {
  private cells: Cell[][];
  readonly width: number;
  readonly height: number;

  constructor(width: number, height: number) {
    this.width = width;
    this.height = height;
    this.cells = Array(height).fill(null).map(() =>
      Array(width).fill(null).map(() => ({ char: " ", color: null }))
    );
  }

  // 写入字符
  set(x: number, y: number, char: string, color?: string): void {
    if (x >= 0 && x < this.width && y >= 0 && y < this.height) {
      this.cells[y][x] = { char, color };
    }
  }

  // 写入字符串 (处理宽字符)
  write(x: number, y: number, text: string, color?: string): void {
    let offset = 0;
    for (const char of text) {
      const width = getCharWidth(char);  // 宽字符返回 2
      this.set(x + offset, y, char, color);
      offset += width;
    }
  }

  // 输出
  toString(): string {
    return this.cells.map(row =>
      row.map(cell => colorize(cell.char, cell.color)).join("")
    ).join("\n");
  }
}

interface Cell {
  char: string;
  color: string | null;
}

// 字符宽度计算 (CJK、Emoji 为 2)
function getCharWidth(char: string): number {
  const code = char.codePointAt(0);
  if (!code) return 1;

  // CJK
  if ((code >= 0x4E00 && code <= 0x9FFF) ||
      (code >= 0x3000 && code <= 0x303F) ||
      (code >= 0xFF00 && code <= 0xFFEF)) {
    return 2;
  }

  // Emoji (简化判断)
  if (code >= 0x1F300 && code <= 0x1FAFF) {
    return 2;
  }

  return 1;
}
```

### 6.3 核心渲染函数

```typescript
class GlyphRenderer {
  private style: ResolvedStyle;
  private canvas: Canvas;

  render(layout: LayoutDSL, style: ResolvedStyle): string {
    this.style = style;
    this.canvas = new Canvas(layout.canvas.width, layout.canvas.height);

    this.renderNode(layout.tree, 0, 0);

    return this.canvas.toString();
  }

  private renderNode(node: LayoutNode, offsetX: number, offsetY: number): void {
    const x = offsetX + node.box.x;
    const y = offsetY + node.box.y;

    // 1. 渲染边框
    if (node.border && node.border.style !== "none") {
      this.renderBorder(node, x, y);
    }

    // 2. 渲染内容
    if (node.content) {
      this.renderContent(node, x, y);
    }

    // 3. 递归渲染子节点
    if (node.children) {
      const innerX = x + node.box.padding.left + (node.border ? 1 : 0);
      const innerY = y + node.box.padding.top + (node.border ? 1 : 0);

      for (const child of node.children) {
        this.renderNode(child, innerX, innerY);
      }
    }
  }

  private renderBorder(node: LayoutNode, x: number, y: number): void {
    const { width, height } = node.box;
    const chars = this.style.charset.border[node.border!.style];

    // 四角
    this.canvas.set(x, y, chars.tl);
    this.canvas.set(x + width - 1, y, chars.tr);
    this.canvas.set(x, y + height - 1, chars.bl);
    this.canvas.set(x + width - 1, y + height - 1, chars.br);

    // 水平线
    for (let i = 1; i < width - 1; i++) {
      this.canvas.set(x + i, y, chars.h);
      this.canvas.set(x + i, y + height - 1, chars.h);
    }

    // 垂直线
    for (let i = 1; i < height - 1; i++) {
      this.canvas.set(x, y + i, chars.v);
      this.canvas.set(x + width - 1, y + i, chars.v);
    }
  }

  private renderContent(node: LayoutNode, x: number, y: number): void {
    const content = node.content!;
    const innerX = x + node.box.padding.left + (node.border ? 1 : 0);
    const innerY = y + node.box.padding.top + (node.border ? 1 : 0);
    const innerWidth = node.box.width - node.box.padding.left - node.box.padding.right
                       - (node.border ? 2 : 0);

    switch (content.type) {
      case "text":
        this.renderText(content.lines, innerX, innerY, innerWidth);
        break;
      case "bar":
        this.renderBar(content.segments, innerX, innerY);
        break;
      case "divider":
        this.renderDivider(content, innerX, innerY, innerWidth);
        break;
    }
  }

  private renderText(lines: TextLine[], x: number, y: number, width: number): void {
    lines.forEach((line, i) => {
      const text = this.alignText(line.text, width, line.align);
      this.canvas.write(x, y + i, text);
    });
  }

  private renderBar(segments: BarSegment[], x: number, y: number): void {
    let offset = 0;
    for (const seg of segments) {
      for (let i = 0; i < seg.count; i++) {
        this.canvas.set(x + offset, y, seg.char, seg.color);
        offset++;
      }
    }
  }

  private alignText(text: string, width: number, align: string): string {
    const len = getStringWidth(text);
    if (len >= width) return text.slice(0, width);

    const padding = width - len;
    switch (align) {
      case "center":
        const left = Math.floor(padding / 2);
        return " ".repeat(left) + text + " ".repeat(padding - left);
      case "right":
        return " ".repeat(padding) + text;
      default:
        return text + " ".repeat(padding);
    }
  }
}
```

### 6.4 进度条渲染 (关键细节)

```typescript
class BarRenderer {
  render(value: number, width: number, style: ResolvedStyle): BarSegment[] {
    const variant = style.bars.variant;
    const chars = style.charset.blocks[variant];

    const filledFull = Math.floor(value * width);
    const remainder = (value * width) - filledFull;
    const emptyCount = width - filledFull - (remainder > 0 ? 1 : 0);

    const segments: BarSegment[] = [];

    // 实心部分
    if (filledFull > 0) {
      segments.push({
        char: chars[chars.length - 1],  // █
        count: filledFull,
        color: style.colors?.accent
      });
    }

    // 过渡部分 (如 ▊)
    if (remainder > 0 && chars.length > 2) {
      const index = Math.floor(remainder * (chars.length - 1));
      segments.push({
        char: chars[index],
        count: 1,
        color: style.colors?.accent
      });
    }

    // 空白部分
    if (emptyCount > 0) {
      segments.push({
        char: chars[0],  // ░
        count: emptyCount,
        color: style.colors?.muted
      });
    }

    return segments;
  }
}

// 示例输出:
// 72% with width=20:  ██████████████▊░░░░░
```

### 6.5 Sparkline 渲染 (Braille)

```typescript
class SparklineRenderer {
  // Braille 点阵映射
  private static BRAILLE_BASE = 0x2800;

  // 每个字符是 2x4 的点阵
  // ⡀ ⠄ ⠂ ⠁
  // ⢀ ⠠ ⠐ ⠈

  render(data: number[], width: number, height: number): string[] {
    const normalizedData = this.normalize(data, height * 4);
    const lines: string[] = Array(height).fill("");

    for (let col = 0; col < width; col++) {
      const dataIndex = Math.floor(col * data.length / width);
      const value = normalizedData[dataIndex];

      // 计算每行应该显示多少点
      for (let row = 0; row < height; row++) {
        const rowTop = (height - row - 1) * 4;
        const dots = this.calculateDots(value, rowTop, 4);
        lines[row] += this.dotsToChar(dots);
      }
    }

    return lines;
  }

  private normalize(data: number[], maxHeight: number): number[] {
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min || 1;
    return data.map(v => Math.round((v - min) / range * maxHeight));
  }

  private dotsToChar(dots: number): string {
    return String.fromCharCode(SparklineRenderer.BRAILLE_BASE + dots);
  }
}

// 示例输出 (2 行高):
// ⣀⣤⣶⣿⣿⣶⣤⣀
// ⣿⣿⣿⣿⣿⣿⣿⣿
```

---

## 七、组件注册表 (扩展性)

### 7.1 组件接口

```typescript
interface ComponentDefinition<T = any> {
  // 组件名
  name: string;

  // JSON Schema (用于验证 IR)
  schema: JSONSchema;

  // 测量: 计算 intrinsic size
  measure(data: T, constraints: MeasureConstraints): MeasureResult;

  // 布局: 生成 LayoutNode
  layout(data: T, box: BoxConstraints, style: ResolvedStyle): LayoutNode;
}

interface MeasureConstraints {
  maxWidth?: number;
  maxHeight?: number;
}

interface MeasureResult {
  minWidth: number;
  minHeight: number;
  preferredWidth?: number;
  preferredHeight?: number;
}

interface BoxConstraints {
  x: number;
  y: number;
  width: number;
  maxHeight?: number;
}
```

### 7.2 组件注册

```typescript
class ComponentRegistry {
  private components = new Map<string, ComponentDefinition>();

  register(definition: ComponentDefinition): void {
    this.components.set(definition.name, definition);
  }

  get(name: string): ComponentDefinition | undefined {
    return this.components.get(name);
  }

  // 批量注册内置组件
  registerBuiltins(): void {
    this.register(TextComponent);
    this.register(HeadingComponent);
    this.register(DividerComponent);
    this.register(KVComponent);
    this.register(ListComponent);
    this.register(TableComponent);
    this.register(BarComponent);
    this.register(SparklineComponent);
    this.register(TreeComponent);
    this.register(CardComponent);
    this.register(GridComponent);
    this.register(StackComponent);
    // ...
  }
}

// 全局单例
export const componentRegistry = new ComponentRegistry();
componentRegistry.registerBuiltins();
```

### 7.3 自定义组件示例

```typescript
// 自定义: 日历组件
const CalendarComponent: ComponentDefinition<CalendarData> = {
  name: "calendar",

  schema: {
    type: "object",
    properties: {
      month: { type: "number" },
      year: { type: "number" },
      highlighted: { type: "array", items: { type: "number" } }
    },
    required: ["month", "year"]
  },

  measure(data, constraints) {
    return {
      minWidth: 22,   // "Su Mo Tu We Th Fr Sa"
      minHeight: 8,   // header + 6 weeks max
      preferredWidth: 22
    };
  },

  layout(data, box, style) {
    const days = generateCalendarDays(data.year, data.month);
    const lines: TextLine[] = [
      { text: `${MONTHS[data.month]} ${data.year}`, align: "center" },
      { text: "Su Mo Tu We Th Fr Sa", align: "left" },
      ...formatWeeks(days, data.highlighted)
    ];

    return {
      id: crypto.randomUUID(),
      componentType: "calendar",
      box: { ...box, height: lines.length },
      content: { type: "text", lines }
    };
  }
};

// 注册
componentRegistry.register(CalendarComponent);
```

---

## 八、完整流程示例

### 8.1 输入: 用户意图

```
"显示当前系统状态，包括服务名、版本、延迟和负载"
```

### 8.2 LLM 输出: Semantic IR

```json
{
  "canvas": { "width": 60 },
  "style": "enterprise_minimal",
  "root": {
    "type": "card",
    "header": { "type": "heading", "level": 1, "text": "System Status", "align": "center" },
    "sections": [
      {
        "type": "kv",
        "layout": "table",
        "items": [
          { "key": "Service", "value": "Inference Engine" },
          { "key": "Version", "value": "3.2.1" },
          { "key": "Latency", "value": 12, "unit": "ms", "status": "success" },
          { "key": "Load", "bar": 0.72 }
        ]
      }
    ]
  }
}
```

### 8.3 编译: Layout DSL

```json
{
  "canvas": { "width": 60, "height": 7 },
  "tree": {
    "id": "root",
    "componentType": "card",
    "box": { "x": 0, "y": 0, "width": 60, "height": 7, "padding": { "top": 0, "right": 1, "bottom": 0, "left": 1 } },
    "border": { "style": "single", "sides": { "top": true, "right": true, "bottom": true, "left": true } },
    "children": [
      {
        "id": "header",
        "componentType": "heading",
        "box": { "x": 0, "y": 0, "width": 58, "height": 1 },
        "content": { "type": "text", "lines": [{ "text": "SYSTEM STATUS", "align": "center" }] }
      },
      {
        "id": "divider-1",
        "componentType": "divider",
        "box": { "x": 0, "y": 1, "width": 58, "height": 1 },
        "content": { "type": "divider", "char": "─" }
      },
      {
        "id": "kv-section",
        "componentType": "kv",
        "box": { "x": 0, "y": 2, "width": 58, "height": 4 },
        "content": {
          "type": "text",
          "lines": [
            { "text": "Service   │ Inference Engine", "align": "left" },
            { "text": "Version   │ 3.2.1", "align": "left" },
            { "text": "Latency   │ 12 ms                              ✓", "align": "left" },
            { "text": "Load      │ ██████████████████████░░░░░░░░░░ 72%", "align": "left" }
          ]
        }
      }
    ]
  }
}
```

### 8.4 渲染: 最终输出

```
┌──────────────────────────────────────────────────────────┐
│                     SYSTEM STATUS                        │
├──────────────────────────────────────────────────────────┤
│ Service   │ Inference Engine                             │
│ Version   │ 3.2.1                                        │
│ Latency   │ 12 ms                                    ✓   │
│ Load      │ ██████████████████████░░░░░░░░░░░░░░░░ 72%   │
└──────────────────────────────────────────────────────────┘
```

---

## 九、目录结构

```
solar/
├── core/
│   └── tvs/                              # Terminal Visual System
│       ├── index.ts                      # 主入口
│       │
│       ├── ir/                           # Semantic IR
│       │   ├── types.ts                  # IR 类型定义
│       │   ├── schema.json               # JSON Schema
│       │   └── validator.ts              # IR 验证器
│       │
│       ├── compiler/                     # 编译器
│       │   ├── semantic-compiler.ts      # Intent → IR
│       │   ├── layout-compiler.ts        # IR → Layout DSL
│       │   └── measure.ts                # 测量算法
│       │
│       ├── layout/                       # 布局引擎
│       │   ├── engine.ts                 # 布局主引擎
│       │   ├── box-model.ts              # 盒模型计算
│       │   ├── grid.ts                   # 栅格系统
│       │   └── align.ts                  # 对齐算法
│       │
│       ├── renderer/                     # 渲染器
│       │   ├── glyph-renderer.ts         # 字形渲染主类
│       │   ├── canvas.ts                 # 字符画布
│       │   ├── border.ts                 # 边框渲染
│       │   ├── bar.ts                    # 进度条渲染
│       │   ├── sparkline.ts              # 迷你图渲染
│       │   └── text.ts                   # 文本渲染
│       │
│       ├── style/                        # 样式系统
│       │   ├── types.ts                  # 样式类型
│       │   ├── resolver.ts               # 样式解析
│       │   ├── presets/                  # 预设样式
│       │   │   ├── enterprise.json
│       │   │   ├── research.json
│       │   │   ├── cyber.json
│       │   │   └── solar.json
│       │   └── charset.ts                # 字符集定义
│       │
│       ├── components/                   # 组件
│       │   ├── registry.ts               # 组件注册表
│       │   ├── base.ts                   # 基础组件接口
│       │   ├── text.ts
│       │   ├── heading.ts
│       │   ├── divider.ts
│       │   ├── kv.ts
│       │   ├── list.ts
│       │   ├── table.ts
│       │   ├── bar.ts
│       │   ├── sparkline.ts
│       │   ├── tree.ts
│       │   ├── card.ts
│       │   ├── grid.ts
│       │   └── stack.ts
│       │
│       └── utils/                        # 工具函数
│           ├── char-width.ts             # 字符宽度
│           ├── ansi.ts                   # ANSI 颜色
│           └── truncate.ts               # 截断
│
├── templates/
│   └── tvs/
│       └── styles/                       # 用户自定义样式
│
└── docs/
    └── TERMINAL_VISUAL_SYSTEM_DESIGN.md  # 本文档
```

---

## 十、API 设计

### 10.1 高级 API (推荐)

```typescript
import { tvs } from "solar/core/tvs";

// 方式 1: 直接渲染 IR
const output = tvs.render({
  style: "enterprise_minimal",
  root: {
    type: "card",
    header: "System Status",
    sections: [
      { type: "kv", items: [{ key: "Load", bar: 0.72 }] }
    ]
  }
});

console.log(output);

// 方式 2: 使用 Builder
const output2 = tvs
  .card("System Status")
  .kv([
    { key: "Service", value: "Engine" },
    { key: "Load", bar: 0.72 }
  ])
  .style("research_report")
  .render();

// 方式 3: 队列模式 (LLM 使用)
tvs.queue({
  type: "card",
  header: "Status",
  sections: [...]
});
// Daemon 会监控并渲染
```

### 10.2 底层 API

```typescript
import {
  SemanticCompiler,
  LayoutCompiler,
  GlyphRenderer,
  StyleResolver,
  componentRegistry
} from "solar/core/tvs";

// 手动控制流水线
const ir = parseIR(userInput);
const style = StyleResolver.resolve("enterprise_minimal");
const layout = LayoutCompiler.compile(ir, style);
const output = GlyphRenderer.render(layout, style);
```

---

## 十一、与现有 UI Engine 的关系

### 迁移路径

| 旧 API | 新 API | 说明 |
|--------|--------|------|
| `ui.box()` | `tvs.card()` | Card 是 Box 的语义化版本 |
| `ui.banner()` | `tvs.card().header().style("banner")` | Banner 是 Card 的特殊样式 |
| `ui.progress()` | `{ type: "bar", value: 0.7 }` | Bar 组件 |
| `ui.table()` | `{ type: "table", columns: [...] }` | Table 组件 |
| `ui.tree()` | `{ type: "tree", root: {...} }` | Tree 组件 |

### 兼容层

```typescript
// 保持旧 API 可用
export const ui = {
  box: (data, style) => tvs.render(convertBoxToCard(data), style),
  banner: (data) => tvs.render(convertBannerToCard(data)),
  // ...
};
```

---

## 十二、总结

### 核心创新

1. **编译而非画画** - LLM 只输出语义 IR，渲染完全确定性
2. **设计系统约束** - Style 不是换字符，是完整的设计 Token
3. **组件可扩展** - 注册新组件即可支持新视觉元素
4. **布局引擎** - 真正的盒模型 + 栅格系统

### 性能特征

- **LLM Token**: 只需生成 JSON，极少 Token
- **渲染延迟**: <5ms (纯 CPU 计算)
- **内存占用**: <1MB (字符画布)

### 美学提升

- **现代字符集**: Box Drawing + Density Blocks + Braille
- **一致性**: 同一 Style 保证视觉统一
- **专业感**: 企业级终端 UI，不是玩具
