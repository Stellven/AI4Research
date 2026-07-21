"""PaperClassifier — rule-based taxonomy classification.

Per interfaces §4: classify_paper, infer_domain, infer_research_route.
Uses enrichment metadata (title, abstract, tags, categories) for classification.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from schema import PaperEnrichment, PaperTaxonomy, _gen_id, _utc_now


_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "nlp": ["language model", "nlp", "text generation", "translation", "summarization",
            "tokenizer", "sentiment", "question answering", "chat", "dialogue", "llm"],
    "cv": ["image", "vision", "detection", "segmentation", "generation",
           "diffusion", "video", "visual", "recognition", "gan", "vae"],
    "audio": ["audio", "speech", "voice", "music", "tts", "asr", "speaker"],
    "multimodal": ["multimodal", "vision-language", "vlm", "image-text",
                   "cross-modal", "clip", "vqa"],
    "rl": ["reinforcement learning", "rlhf", "reward", "policy", "agent",
           "rl", "decision", "game"],
    "systems": ["training", "inference", "optimization", "distributed", "quantization",
                "pruning", "distillation", "compilation", "runtime", "serving",
                "efficiency", "accelerat", "gpu", "hardware", "on-device"],
    "data": ["dataset", "data", "benchmark", "evaluation", "annotation",
             "labeling", "synthetic", "augmentation"],
    "safety": ["safety", "alignment", "red-team", "jailbreak", "toxicity",
               "bias", "fairness", "guardrail"],
}

_METHOD_KEYWORDS: dict[str, list[str]] = {
    "pretraining": ["pretrain", "self-supervised", "foundation model", "base model"],
    "finetuning": ["finetun", "fine-tun", "lora", "qlora", "adapter", "peft",
                   "instruction", "sft", "rlhf", "dpo"],
    "in_context": ["prompt", "in-context", "few-shot", "zero-shot", "chain-of-thought",
                   "cot", "reasoning", "rag", "retrieval"],
    "architecture": ["transformer", "attention", "mamba", "ssm", "cnn", "rnn",
                     "moe", "mixture of expert", "hybrid"],
    "compression": ["quantiz", "pruning", "distill", "sparsit", "low-rank",
                    "compression", "speculativ"],
    "generation": ["diffusion", "gan", "vae", "flow", "autoregressive", "decoding"],
}

_TASK_KEYWORDS: dict[str, list[str]] = {
    "generation": ["generation", "generation", "synthesis", "completion"],
    "understanding": ["understanding", "comprehension", "analysis", "interpretation"],
    "retrieval": ["retrieval", "search", "ranking", "embedding"],
    "classification": ["classification", "detection", "recognition", "categorization"],
    "reasoning": ["reasoning", "planning", "problem solving", "math", "code"],
}

_MATURITY_MAP: dict[str, str] = {
    "preprint": "early",
    "conference": "peer_reviewed",
    "journal": "peer_reviewed",
    "workshop": "early",
    "demo": "prototype",
}


def _match_keywords(text: str, keyword_map: dict[str, list[str]]) -> str:
    text_lower = text.lower()
    best_match = ""
    best_count = 0
    for category, keywords in keyword_map.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > best_count:
            best_count = count
            best_match = category
    return best_match or "other"


class PaperClassifier:
    """Rule-based paper taxonomy classifier."""

    def classify_paper(self, enrichment: PaperEnrichment) -> PaperTaxonomy:
        text = self._build_text(enrichment)
        domain = self.infer_domain(text, "")
        method = _match_keywords(text, _METHOD_KEYWORDS)
        task = _match_keywords(text, _TASK_KEYWORDS)
        stack_layer = self._infer_stack_layer(text)
        asset = self._infer_asset(enrichment)
        maturity = self._infer_maturity(enrichment)

        taxonomy = PaperTaxonomy(
            taxonomy_id=_gen_id("tax-"),
            paper_id=enrichment.paper_id,
            domain=domain,
            method=method,
            task=task,
            asset=asset,
            stack_layer=stack_layer,
            maturity=maturity,
            research_route="",
            labels_json="[]",
            confidence=self._compute_confidence(text, domain, method),
        )
        taxonomy.research_route = self.infer_research_route(taxonomy)
        return taxonomy

    def infer_domain(self, title: str, summary: str) -> str:
        text = f"{title} {summary}"
        return _match_keywords(text, _DOMAIN_KEYWORDS)

    def infer_research_route(self, taxonomy: PaperTaxonomy) -> str:
        if taxonomy.domain == "systems" and taxonomy.method in ("compression", "architecture"):
            return "engineering"
        if taxonomy.domain in ("nlp", "cv", "multimodal") and taxonomy.method in ("pretraining", "finetuning"):
            return "model_development"
        if taxonomy.domain == "safety":
            return "safety_alignment"
        if taxonomy.domain == "data":
            return "data_engineering"
        return "applied_research"

    def _build_text(self, enrichment: PaperEnrichment) -> str:
        parts = []
        hf = json.loads(enrichment.hf_metadata_json)
        if isinstance(hf, dict):
            card = hf.get("card_data", {})
            if isinstance(card, dict):
                parts.append(card.get("description", ""))
            tags = hf.get("tags", [])
            if isinstance(tags, list):
                parts.extend(tags)
        arxiv = json.loads(enrichment.arxiv_metadata_json)
        if isinstance(arxiv, dict):
            parts.append(arxiv.get("title", ""))
            parts.append(arxiv.get("abstract", ""))
        return " ".join(p for p in parts if p)

    def _infer_stack_layer(self, text: str) -> str:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["hardware", "gpu", "chip", "accelerat", "on-device", "edge"]):
            return "hardware"
        if any(kw in text_lower for kw in ["inference", "serving", "runtime", "compil", "kernel"]):
            return "inference"
        if any(kw in text_lower for kw in ["training", "distributed", "pipeline parallel"]):
            return "training"
        if any(kw in text_lower for kw in ["finetun", "lora", "adapter", "peft"]):
            return "adaptation"
        return "model"

    def _infer_asset(self, enrichment: PaperEnrichment) -> str:
        assets = json.loads(enrichment.hf_assets_json)
        if isinstance(assets, dict):
            datasets = assets.get("linked_datasets", [])
            spaces = assets.get("linked_spaces", [])
            models = assets.get("linked_models", [])
            if datasets and spaces:
                return "full_suite"
            if spaces:
                return "demo"
            if datasets:
                return "dataset"
            if models:
                return "model"
        return "paper_only"

    def _infer_maturity(self, enrichment: PaperEnrichment) -> str:
        arxiv = json.loads(enrichment.arxiv_metadata_json)
        if isinstance(arxiv, dict) and arxiv.get("published"):
            return "early"
        assets = json.loads(enrichment.hf_assets_json)
        if isinstance(assets, dict) and assets.get("linked_spaces"):
            return "prototype"
        return "early"

    def _compute_confidence(self, text: str, domain: str, method: str) -> float:
        score = 0.3
        if domain != "other":
            score += 0.3
        if method != "other":
            score += 0.2
        if len(text) > 100:
            score += 0.1
        if len(text) > 500:
            score += 0.1
        return min(score, 1.0)
