"""Golden-style quality gate for professor-grade DeepResearch reports.

The gate compares a final report against a human-approved HTML artifact. It is
intentionally structural and editorial, not semantic: source/citation gates
already validate evidence. This gate catches reports that are long but still
read like scaffolds, smoke tests, or deterministic summaries.
"""

from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


COMMENTARY_TERMS = (
    "不是",
    "而是",
    "评价",
    "硬伤",
    "怎么读",
    "最终判断",
    "关键",
    "机制",
    "解决",
    "实验意义",
    "tradeoff",
    "failure mode",
    "limitation",
)
TEMPLATE_RESIDUE_PATTERNS = (
    r"this section should",
    r"for `[^`]+`",
    r"architecture gate ledger",
    r"runtime decision rules",
    r"technical architecture matrix",
    r"prompt packet",
    r"pending final section",
    r"smoke test",
)
AUDIENCE_HYGIENE_PATTERNS = (
    ("internal_system_roadmap", r"Solar-Harness\s*改造路线|solar-harness\s+roadmap"),
    ("internal_writer_process", r"Claim-ledger\s*写作|claim[- ]ledger\s+writing|deterministic writer|writer backend"),
    ("internal_eval_process", r"模板污染硬门禁|strict eval|normalized paragraph|golden[_ -]?style|quality gate"),
    ("internal_html_process", r"HTML\s*是审阅界面|Markdown\s*转码|human[- ]readable artifact"),
    ("bad_mode_taxonomy_leak", r"不继续复用的坏模式|章节 ID 泄露|列表伪装洞察|引用率幻觉|HTML 装饰化"),
    ("section_id_leak", r"\bch\d{1,3}(?:#\d+)?::|\bch\d{1,3}/sec\d{1,3}\b"),
)
REPORT_HTML_NAME_PATTERNS = (
    "report",
    "final",
    "rewritten",
    "clean",
    "trend",
    "insight",
)


class _HTMLStatsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.text_parts: list[str] = []
        self.headings: list[tuple[str, str]] = []
        self.tag_counts: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack.append(tag)
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1

    def handle_endtag(self, tag: str) -> None:
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self.stack and self.stack[-1] in {"h1", "h2", "h3", "h4"}:
            self.headings.append((self.stack[-1], text))
        self.text_parts.append(text)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def _candidate_reader_artifacts(root: Path, final_path: Path) -> list[Path]:
    candidates: list[Path] = []
    if final_path.exists():
        candidates.append(final_path)
    for path in [root / "chief_editor_final.md"]:
        if path.exists() and path not in candidates:
            candidates.append(path)
    for path in sorted(root.glob("*.html")):
        name = path.name.lower()
        if name == "quality_golden.html":
            continue
        if any(marker in name for marker in REPORT_HTML_NAME_PATTERNS):
            candidates.append(path)
    if not candidates and final_path.exists():
        candidates.append(final_path)
    return candidates


def assess_audience_hygiene(root: str | Path, *, final_md: str | Path | None = None) -> dict[str, Any]:
    """Reject reader-facing reports that leak harness/editor internals."""
    report_root = Path(root).expanduser()
    final_path = Path(final_md).expanduser() if final_md else report_root / "final.md"
    artifacts = _candidate_reader_artifacts(report_root, final_path)
    matches: list[dict[str, Any]] = []
    for artifact in artifacts:
        text = _read_text(artifact)
        if not text:
            continue
        for code, pattern in AUDIENCE_HYGIENE_PATTERNS:
            found = list(re.finditer(pattern, text, flags=re.I))
            if not found:
                continue
            matches.append({
                "code": code,
                "artifact": str(artifact),
                "count": len(found),
                "examples": [match.group(0)[:120] for match in found[:3]],
            })
    issues = [
        f"audience_hygiene_leak:{item['code']}:{Path(str(item['artifact'])).name}:{item['count']}"
        for item in matches
    ]
    payload = {
        "ok": not issues,
        "artifact_count": len(artifacts),
        "artifacts": [str(path) for path in artifacts],
        "matches": matches,
        "issues": issues,
    }
    (report_root / "survey_audience_hygiene.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def _word_count(text: str) -> int:
    ascii_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text or "")
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text or "")
    return len(ascii_words) + len(cjk_chars) // 2


def _headings_from_markdown(text: str) -> list[tuple[str, str]]:
    headings: list[tuple[str, str]] = []
    for line in (text or "").splitlines():
        match = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if match:
            headings.append((f"h{len(match.group(1))}", match.group(2).strip()))
    return headings


def _duplicate_long_sentence_stats(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"\[[a-z]+:[^\]]+\]", "", text or "")
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"^\s*[#|>-].*$", " ", cleaned, flags=re.M)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    sentences = [item.strip() for item in re.split(r"(?<=[.!?。！？])\s+", cleaned) if len(item.strip()) >= 80]
    counts: dict[str, int] = {}
    for sentence in sentences:
        counts[sentence] = counts.get(sentence, 0) + 1
    repeated = [count for count in counts.values() if count > 1]
    duplicate_occurrences = sum(count - 1 for count in repeated)
    return {
        "long_sentence_count": len(sentences),
        "duplicate_long_sentence_occurrences": duplicate_occurrences,
        "duplicate_long_sentence_ratio": round(duplicate_occurrences / max(len(sentences), 1), 4),
        "max_duplicate_long_sentence_count": max(repeated) if repeated else 0,
    }


def benchmark_html_stats(path: str | Path) -> dict[str, Any]:
    html_path = Path(path).expanduser()
    parser = _HTMLStatsParser()
    raw = _read_text(html_path)
    parser.feed(raw)
    plain = " ".join(parser.text_parts)
    headings = parser.headings
    unique_headings = {title for _, title in headings}
    chars_k = max(len(plain) / 10000.0, 1.0)
    return {
        "path": str(html_path),
        "exists": html_path.exists(),
        "html_chars": len(raw),
        "plain_chars": len(plain),
        "word_count": _word_count(plain),
        "heading_count": len(headings),
        "unique_heading_count": len(unique_headings),
        "section_count": int(parser.tag_counts.get("section", 0)),
        "svg_count": int(parser.tag_counts.get("svg", 0)),
        "table_count": int(parser.tag_counts.get("table", 0)),
        "figure_count": int(parser.tag_counts.get("figure", 0)),
        "commentary_term_count": sum(plain.lower().count(term.lower()) for term in COMMENTARY_TERMS),
        "commentary_terms_per_10k_chars": round(sum(plain.lower().count(term.lower()) for term in COMMENTARY_TERMS) / chars_k, 4),
    }


def _benchmark_path(root: Path, explicit: str | Path | None = None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("SOLAR_DEEPRESEARCH_GOLDEN_HTML", "").strip()
    if env:
        return Path(env).expanduser()
    local = root / "quality_golden.html"
    if local.exists():
        return local
    return None


def assess_golden_style(
    root: str | Path,
    *,
    final_md: str | Path | None = None,
    benchmark_html: str | Path | None = None,
    require_benchmark: bool = False,
) -> dict[str, Any]:
    report_root = Path(root).expanduser()
    report_root.mkdir(parents=True, exist_ok=True)
    final_path = Path(final_md).expanduser() if final_md else report_root / "final.md"
    benchmark_path = _benchmark_path(report_root, benchmark_html)
    text = _read_text(final_path)
    headings = _headings_from_markdown(text)
    heading_titles = [title for _, title in headings]
    unique_heading_ratio = round(len(set(heading_titles)) / max(len(heading_titles), 1), 4)
    chars = len(text)
    words = _word_count(text)
    chars_k = max(chars / 10000.0, 1.0)
    commentary_count = sum(text.lower().count(term.lower()) for term in COMMENTARY_TERMS)
    commentary_density = round(commentary_count / chars_k, 4)
    template_residue = sum(len(re.findall(pattern, text, flags=re.I)) for pattern in TEMPLATE_RESIDUE_PATTERNS)
    duplicate_stats = _duplicate_long_sentence_stats(text)
    audience_hygiene = assess_audience_hygiene(report_root, final_md=final_path)
    benchmark = benchmark_html_stats(benchmark_path) if benchmark_path else {}

    if benchmark.get("exists"):
        min_chars = max(30000, int(float(benchmark.get("plain_chars") or 0) * 0.45))
        min_words = max(8000, int(float(benchmark.get("word_count") or 0) * 0.55))
        min_headings = max(35, int(float(benchmark.get("heading_count") or 0) * 0.35))
        min_commentary_density = max(10.0, float(benchmark.get("commentary_terms_per_10k_chars") or 0.0) * 0.35)
    else:
        min_chars = 30000
        min_words = 8000
        min_headings = 35
        min_commentary_density = 10.0

    issues: list[str] = []
    if require_benchmark and not benchmark_path:
        issues.append("golden_benchmark_required_missing")
    if benchmark_path and not benchmark.get("exists"):
        issues.append(f"golden_benchmark_missing:{benchmark_path}")
    if not final_path.exists():
        issues.append(f"golden_final_md_missing:{final_path}")
    if chars < min_chars:
        issues.append(f"golden_final_chars_low:{chars}<{min_chars}")
    if words < min_words:
        issues.append(f"golden_word_count_low:{words}<{min_words}")
    if len(headings) < min_headings:
        issues.append(f"golden_heading_count_low:{len(headings)}<{min_headings}")
    if unique_heading_ratio < 0.45:
        issues.append(f"golden_unique_heading_ratio_low:{unique_heading_ratio:.4f}<0.4500")
    if commentary_density < min_commentary_density:
        issues.append(f"golden_commentary_density_low:{commentary_density:.4f}<{min_commentary_density:.4f}")
    if template_residue > 0:
        issues.append(f"golden_template_residue_count:{template_residue}>0")
    if duplicate_stats["duplicate_long_sentence_ratio"] > 0.20:
        issues.append(f"golden_duplicate_long_sentence_ratio_high:{duplicate_stats['duplicate_long_sentence_ratio']:.4f}>0.2000")

    payload = {
        "ok": not issues,
        "enabled": bool(benchmark_path),
        "required": require_benchmark,
        "benchmark": benchmark,
        "final_md": str(final_path),
        "char_count": chars,
        "word_count": words,
        "heading_count": len(headings),
        "unique_heading_ratio": unique_heading_ratio,
        "commentary_term_count": commentary_count,
        "commentary_terms_per_10k_chars": commentary_density,
        "template_residue_count": template_residue,
        "audience_hygiene": audience_hygiene,
        **duplicate_stats,
        "thresholds": {
            "min_chars": min_chars,
            "min_words": min_words,
            "min_headings": min_headings,
            "min_commentary_terms_per_10k_chars": min_commentary_density,
        },
        "issues": issues,
    }
    (report_root / "survey_golden_style.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
