# Solar MemPalace L3

语义记忆层 (L3) - 基于 ChromaDB 的向量数据库，提供跨会话记忆存储和检索。

## 功能

### 4 个核心工具

| 工具 | 功能 | 参数 |
|------|------|------|
| `mempalace_add` | 添加文档 | `text`, `source`, `entity_codes` |
| `mempalace_search` | 语义搜索 | `query`, `top_k`, `filter` |
| `mempalace_delete` | 删除文档 | `doc_id` |
| `mempalace_stats` | 统计信息 | 无 |

### AAAK 日记工具 (D4)

`mempalace_diary_write` - 写入压缩格式的日记

**格式**: `SESSION:YYYY-MM-DD|summary|agent:xxx|topic:yyy`

**示例**:
```
mempalace_diary_write(
    agent_name="solar",
    entry="完成 D1 MCP server 重写",
    topic="development"
)
```

## 安装

### 依赖

```bash
# Python 3.11+ (MCP SDK 要求)
/opt/homebrew/bin/python3.11 -m pip install mcp chromadb sentence-transformers langdetect

# 或用默认 Python 3.9
pip3 install chromadb sentence-transformers langdetect
```

### 配置

配置文件: `~/.solar/mempalace/config.yaml`

```yaml
collection_name: solar_memories
model_name: paraphrase-multilingual-MiniLM-L12-v2
chroma_persist_dir: ~/.solar/mempalace/data
```

## 使用

### 通过 MCP 协议

注册到 Claude Desktop MCP 配置 (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "solar-mempalace": {
      "command": "/opt/homebrew/bin/python3.11",
      "args": ["-m", "mempalace_mcp_server"],
      "cwd": "~/.solar/mempalace"
    }
  }
}
```

### 直接调用

```python
from mempalace_init import MemPalaceInit

init = MemPalaceInit()
init.init_chromadb()
init.load_models()

# 添加文档
result = mempalace_add(
    text="Solar 是一个 AI 编排系统",
    source="cortex",
    entity_codes=["SOL"]
)
```

## AAAK 实体码

| 码 | 含义 |
|----|------|
| SOL | Solar 系统 |
| HGR | 监护人 (昊哥) |
| DRV | DeepSeek-R1 |
| GL5 | GLM-5 |
| COR | Cortex 来源 |

## 迁移

从 Cortex 迁移 50 条高 cred 数据:

```bash
cd ~/.solar/mempalace
python3 migrate_from_cortex.py --limit 50
```

## 测试

```bash
# 测试 4 个工具
bash test_mcp_tools.sh
```

## Doctor 集成

```bash
# 检查 MemPalace 状态
solar-harness doctor --summary
```

输出示例:
```
│ L3:     ✅ 53 docs
```

## 故障排查

### MCP SDK 未找到

```bash
# 检查 Python 版本 (需要 3.10+)
python3 --version

# 用 Python 3.11 安装
/opt/homebrew/bin/python3.11 -m pip install mcp
```

### Tokenizer 警告

已在 `mempalace_init.py` 中抑制：

```python
warnings.filterwarnings('ignore', message='.*tokenizer.*')
warnings.filterwarnings('ignore', message='.*PyTorc.*')
```

### ChromaDB 连接失败

检查目录权限:

```bash
ls -la ~/.solar/mempalace/data
chmod -R u+rw ~/.solar/mempalace/data
```

---

**版本**: L3 v2.0
**更新**: 2026-04-30

## MCP 工具

MemPalace 通过 MCP 协议暴露以下工具供 Claude Code 调用:

| 工具名 | 用途 | 参数 |
|--------|------|------|
| `mempalace_add` | 写入语义记忆 | text, source, entity_codes |
| `mempalace_search` | 语义搜索召回 | query, top_k, filter |
| `mempalace_delete` | 按 doc_id 删除 | doc_id |
| `mempalace_stats` | collection 统计 | (无) |
| `mempalace_diary_write` | AAAK 日记写入 | agent_name, entry, topic |
| `mempalace_diary_read` | AAAK 日记读取 | agent_name, topic, limit |

### 注册

```bash
claude mcp add mempalace -- python3.11 ~/.solar/mempalace/mempalace_mcp_server.py
```

注册后 `claude mcp list` 应看到 `mempalace ✓ Connected`。
