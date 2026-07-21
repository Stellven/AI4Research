#!/usr/bin/env python3.11
"""
Solar MemPalace L3 - MCP 服务器 (真协议)

提供 5 个工具:
- mempalace_add: 添加文档
- mempalace_search: 语义搜索
- mempalace_delete: 删除文档
- mempalace_stats: 统计信息
- mempalace_diary_write: AAAK 日记

使用 mcp.server SDK 实现 stdio 协议
"""

import sys
import json
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

# D6: 抑制警告
warnings.filterwarnings('ignore', message='.*tokenizer.*')
warnings.filterwarnings('ignore', message='.*PyTorc.*')

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from mempalace_init import MemPalaceInit

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 全局初始化器
_init = None


def get_init():
    """获取初始化器实例"""
    global _init
    if _init is None:
        _init = MemPalaceInit()
        _init.init_chromadb()
        _init.load_models()
    return _init


def mempalace_add(text: str, source: str = "diary", entity_codes: list = None) -> dict:
    """添加文档到 MemPalace"""
    try:
        init = get_init()
        lang = init.detect_language(text)
        doc_id = init.generate_id(text, source)
        model = init.get_model(lang)
        embedding = model.encode(text).tolist()

        metadata = {
            "source": source,
            "lang": lang,
            "created_at": datetime.utcnow().isoformat(),
            "entity_codes": ",".join(entity_codes or [])
        }

        init.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[text]
        )

        return {
            "doc_id": doc_id,
            "success": True,
            "message": f"已添加文档: {doc_id}",
            "lang": lang,
            "embedding_dim": len(embedding)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def mempalace_search(query: str, top_k: int = 5, filter: dict = None) -> dict:
    """语义搜索"""
    try:
        init = get_init()
        lang = init.detect_language(query)
        model = init.get_model(lang)
        query_embedding = model.encode(query).tolist()

        results = init.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter
        )

        formatted_results = []
        if results['ids'] and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                formatted_results.append({
                    "id": doc_id,
                    "document": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "score": 1.0 - results['distances'][0][i]
                })

        return {
            "results": formatted_results,
            "count": len(formatted_results),
            "query_lang": lang
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def mempalace_delete(doc_id: str) -> dict:
    """删除文档"""
    try:
        init = get_init()
        existing = init.collection.get(ids=[doc_id])
        if not existing['ids']:
            return {
                "success": False,
                "error": f"文档不存在: {doc_id}"
            }
        init.collection.delete(ids=[doc_id])
        return {
            "success": True,
            "message": f"已删除文档: {doc_id}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def mempalace_stats() -> dict:
    """获取统计信息"""
    try:
        init = get_init()
        total = init.collection.count()
        all_data = init.collection.get()

        lang_dist = {}
        source_dist = {}
        for meta in all_data['metadatas']:
            lang = meta.get('lang', 'unknown')
            source = meta.get('source', 'unknown')
            lang_dist[lang] = lang_dist.get(lang, 0) + 1
            source_dist[source] = source_dist.get(source, 0) + 1

        last_update = None
        if all_data['metadatas']:
            timestamps = [m.get('created_at') for m in all_data['metadatas'] if m.get('created_at')]
            if timestamps:
                last_update = max(timestamps)

        return {
            "total_docs": total,
            "lang_dist": lang_dist,
            "source_dist": source_dist,
            "last_update": last_update,
            "collection_name": init.config["collection_name"]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def mempalace_diary_write(agent_name: str, entry: str, topic: str = "general") -> dict:
    """
    D4: AAAK 日记写入

    格式: SESSION:YYYY-MM-DD|summary|ALC:xxx|stars
    """
    try:
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        # AAAK 格式
        diary_entry = f"SESSION:{date_str}|{entry}|agent:{agent_name}|topic:{topic}"

        result = mempalace_add(
            text=diary_entry,
            source="diary",
            entity_codes=[agent_name.upper()[:3] if len(agent_name) >= 3 else "SOL"]
        )

        return {
            "success": True,
            "entry": diary_entry,
            "doc_id": result.get("doc_id"),
            "message": "日记已写入"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def mempalace_diary_read(agent_name: str, topic: str = None, limit: int = 10) -> list:
    """
    D4: AAAK 日记读取 (按 agent 和 topic 过滤)

    返回: list[dict] 命中的日记 (按时间倒序)
    """
    try:
        # 用 search 过滤 source=diary, 匹配 agent 字符串
        query = f"agent:{agent_name}"
        if topic:
            query += f" topic:{topic}"
        result = mempalace_search(
            query=query,
            top_k=limit,
            filter={"source": "diary"}
        )
        # 二次过滤: 只返回真正含 agent_name 的
        records = []
        for r in result.get("results", []):
            doc = r.get("document", "")
            if f"agent:{agent_name}" in doc:
                if not topic or f"topic:{topic}" in doc:
                    records.append({
                        "id": r.get("id"),
                        "entry": doc,
                        "agent": agent_name,
                        "topic": topic or "any",
                        "score": r.get("score")
                    })
        return records
    except Exception as e:
        return [{"error": str(e)}]


# MCP Server
app = Server("solar-mempalace")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用工具"""
    return [
        Tool(
            name="mempalace_add",
            description="添加文档到 MemPalace (L3 语义记忆)",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "文档内容"
                    },
                    "source": {
                        "type": "string",
                        "enum": ["diary", "cortex", "favorite"],
                        "description": "来源类型"
                    },
                    "entity_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "AAAK 实体码，如 ['SOL', 'HGR']"
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="mempalace_search",
            description="语义搜索 MemPalace 文档",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数",
                        "default": 5
                    },
                    "filter": {
                        "type": "object",
                        "description": "过滤条件，如 {'source': 'diary'}"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="mempalace_delete",
            description="删除 MemPalace 文档",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "文档 ID"
                    }
                },
                "required": ["doc_id"]
            }
        ),
        Tool(
            name="mempalace_stats",
            description="获取 MemPalace 统计信息",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="mempalace_diary_write",
            description="写入 AAAK 格式日记 (D4)",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Agent 名称"
                    },
                    "entry": {
                        "type": "string",
                        "description": "日记内容 (AAAK 格式简述)"
                    },
                    "topic": {
                        "type": "string",
                        "description": "主题类型",
                        "default": "general"
                    }
                },
                "required": ["agent_name", "entry"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """调用工具"""
    try:
        if name == "mempalace_add":
            result = mempalace_add(**arguments)
        elif name == "mempalace_search":
            # 处理 top_k 默认值
            arguments.setdefault("top_k", 5)
            result = mempalace_search(**arguments)
        elif name == "mempalace_delete":
            result = mempalace_delete(**arguments)
        elif name == "mempalace_stats":
            result = mempalace_stats()
        elif name == "mempalace_diary_write":
            arguments.setdefault("topic", "general")
            result = mempalace_diary_write(**arguments)
        else:
            result = {
                "success": False,
                "error": f"未知工具: {name}"
            }

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False, indent=2))]


async def main():
    """MCP 服务器主入口"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
