#!/usr/bin/env python3.11
"""
Solar MemPalace L3 - ChromaDB 初始化脚本

功能:
- 初始化 ChromaDB Collection
- 加载 Embedding 模型
- 语言检测
"""

import warnings
# D6: 抑制 tokenizer 警告
warnings.filterwarnings('ignore', message='.*tokenizer.*')
warnings.filterwarnings('ignore', message='.*PyTorc.*')

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from langdetect import detect, LangDetectException

# 配置路径
MEMPALACE_DIR = Path.home() / ".solar" / "mempalace"
DATA_DIR = MEMPALACE_DIR / "data"
MODELS_DIR = MEMPALACE_DIR / "models"
CONFIG_FILE = MEMPALACE_DIR / "config.yaml"

# 默认配置
DEFAULT_CONFIG = {
    "data_dir": str(DATA_DIR),
    "models_dir": str(MODELS_DIR),
    "collection_name": "solar_memories",
    "hnsw": {
        "space": "cosine",
        "M": 16,
        "construction_ef": 200,
        "search_ef": 100
    },
    "models": {
        "zh": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "en": "sentence-transformers/all-MiniLM-L6-v2",
        "ja": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "other": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    }
}


class MemPalaceInit:
    """MemPalace 初始化器"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE
        self.config = self._load_config()
        self.client = None
        self.collection = None
        self.models = {}

    def _load_config(self) -> Dict:
        """加载配置文件"""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                # 简单 YAML 解析（仅支持基础格式）
                import yaml
                try:
                    return yaml.safe_load(f)
                except ImportError:
                    # 如果没有 yaml，返回默认配置
                    return DEFAULT_CONFIG
        return DEFAULT_CONFIG

    def _save_config(self):
        """保存配置文件"""
        import yaml
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False)

    def init_chromadb(self):
        """初始化 ChromaDB"""
        self.client = chromadb.PersistentClient(
            path=str(self.config["data_dir"]),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # 获取或创建 Collection
        try:
            self.collection = self.client.get_collection(
                name=self.config["collection_name"]
            )
            print(f"✓ 已存在 Collection: {self.config['collection_name']}")
        except:
            self.collection = self.client.create_collection(
                name=self.config["collection_name"],
                metadata=self.config["hnsw"]
            )
            print(f"✓ 创建新 Collection: {self.config['collection_name']}")

        return self.collection

    def detect_language(self, text: str) -> str:
        """检测语言"""
        try:
            lang = detect(text)
            # 映射到配置中的语言代码
            if lang in ['zh-cn', 'zh-tw', 'zh']:
                return 'zh'
            elif lang in ['ja']:
                return 'ja'
            elif lang in ['en']:
                return 'en'
            else:
                return 'other'
        except LangDetectException:
            return 'other'

    def load_models(self):
        """加载 Embedding 模型"""
        print("加载 Embedding 模型...")
        for lang, model_name in self.config["models"].items():
            try:
                model_path = MODELS_DIR / lang.replace('-', '_')
                if model_path.exists():
                    model = SentenceTransformer(str(model_path))
                else:
                    print(f"  下载模型: {lang} -> {model_name}")
                    model = SentenceTransformer(model_name)
                    # 缓存模型
                    model_path.mkdir(parents=True, exist_ok=True)
                    model.save(str(model_path))
                self.models[lang] = model
                print(f"  ✓ {lang}: {model_name}")
            except Exception as e:
                print(f"  ✗ {lang}: {e}")
                # 使用默认模型作为 fallback
                if 'other' not in self.models:
                    self.models['other'] = SentenceTransformer(
                        self.config["models"]["other"]
                    )

        return self.models

    def get_model(self, lang: str = 'other'):
        """获取指定语言的模型"""
        if lang in self.models:
            return self.models[lang]
        return self.models.get('other')

    def generate_id(self, text: str, source: str) -> str:
        """生成文档 ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"mp_{timestamp}_{source[:3]}_{content_hash}"

    def health_check(self) -> Dict:
        """健康检查"""
        try:
            if not self.client:
                self.init_chromadb()

            count = self.collection.count()
            heartbeat = self.client.heartbeat()

            return {
                "status": "ok",
                "collection": self.config["collection_name"],
                "count": count,
                "heartbeat": heartbeat,
                "models_loaded": list(self.models.keys()) if self.models else []
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Solar MemPalace L3 初始化")
    parser.add_argument("--init", action="store_true", help="初始化 ChromaDB")
    parser.add_argument("--check-models", action="store_true", help="检查模型")
    parser.add_argument("--health", action="store_true", help="健康检查")
    parser.add_argument("--config", type=Path, help="配置文件路径")

    args = parser.parse_args()

    init = MemPalaceInit(config_path=args.config)

    if args.init:
        collection = init.init_chromadb()
        models = init.load_models()
        print(f"\n✓ 初始化完成")
        print(f"  Collection: {collection.name}")
        print(f"  Models: {list(models.keys())}")

    elif args.check_models:
        print("检查 Embedding 模型...")
        init.load_models()

    elif args.health:
        health = init.health_check()
        print(json.dumps(health, indent=2, ensure_ascii=False))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
