---
name: mcp-builder
description: 创建 MCP (Model Context Protocol) 服务器
user-invocable: true
disable-model-invocation: false
argument-hint: "[API 或功能描述]"
---

# /mcp-builder - MCP 服务器构建

## 功能

创建符合 MCP 规范的服务器，为 Claude Code 扩展工具能力。

## MCP 服务器结构

```
mcp-server-xxx/
├── package.json
├── tsconfig.json
├── src/
│   └── index.ts      # 主入口
└── README.md
```

## 模板代码

```typescript
#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server(
  { name: "mcp-server-xxx", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

// 定义工具列表
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "tool_name",
      description: "工具描述",
      inputSchema: {
        type: "object",
        properties: {
          param1: { type: "string", description: "参数1说明" }
        },
        required: ["param1"]
      }
    }
  ]
}));

// 实现工具逻辑
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  if (name === "tool_name") {
    // 实现逻辑
    return { content: [{ type: "text", text: "结果" }] };
  }

  throw new Error(`Unknown tool: ${name}`);
});

// 启动服务器
const transport = new StdioServerTransport();
server.connect(transport);
```

## package.json

```json
{
  "name": "mcp-server-xxx",
  "version": "1.0.0",
  "type": "module",
  "bin": { "mcp-server-xxx": "./dist/index.js" },
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
```

## 注册到 Claude Code

编辑 `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "xxx": {
      "command": "node",
      "args": ["/path/to/mcp-server-xxx/dist/index.js"]
    }
  }
}
```

## 执行步骤

1. 确认要封装的 API 或功能
2. 创建项目结构
3. 实现工具定义和逻辑
4. 构建并测试
5. 注册到 Claude Code
