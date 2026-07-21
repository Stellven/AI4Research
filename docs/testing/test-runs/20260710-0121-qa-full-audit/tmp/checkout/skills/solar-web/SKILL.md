# Solar Web Dashboard

极简 Web 监控面板 - 无服务器，直接生成 HTML。

## 使用方式

```bash
bun run web/generate.ts              # 生成一次
bun run web/generate.ts --watch      # 持续更新
bun run web/generate.ts --open       # 生成并打开浏览器
bun run web/generate.ts --style cyberpunk  # 指定风格
```

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    极简数据流                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Agent/Hook/Skill/MCP  ──写入──▶  SQLite                   │
│                                    │                        │
│                                    │ 读取                   │
│                                    ▼                        │
│  generate.ts  ──生成──▶  dashboard.html  ◀──打开── 浏览器  │
│       │                      │                              │
│       │ --watch              │ <meta refresh>               │
│       └──定时更新────────────┘                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 文件

| 文件 | 说明 |
|------|------|
| `~/.solar/solar.db` | 数据源 (Agent/Skill 写入) |
| `~/.solar/dashboard.html` | 生成的 HTML (浏览器打开) |

## 可用风格

- `liquid.dark` - 现代玻璃暗色 (默认)
- `zenwhite` - 极简纯白
- `monolith` - 权威静默
- `aurora` - 极光通透
- `cyberpunk` - 赛博霓虹

## 参数

| 参数 | 说明 |
|------|------|
| `--watch`, `-w` | 持续监控模式 |
| `--open`, `-o` | 生成后打开浏览器 |
| `--style`, `-s` | 指定风格 |
| `--output`, `-O` | 指定输出路径 |

## 特点

- **零依赖**: 无需 npm install，直接 bun 运行
- **零服务器**: 纯静态 HTML，浏览器直接打开
- **自动刷新**: HTML 内置 `<meta refresh>`，3秒刷新
- **轻量**: 单文件 ~300 行
