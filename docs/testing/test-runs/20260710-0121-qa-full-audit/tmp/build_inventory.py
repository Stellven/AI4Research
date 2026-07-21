from __future__ import annotations

import ast
import csv
import fnmatch
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


STOPWORDS = {
    "about", "actual", "agent", "allowed", "artifact", "atomic", "candidate", "class",
    "command", "component", "config", "contract", "correct", "data", "default", "direct",
    "entrypoint", "evidence", "expected", "feature", "file", "files", "function", "generated",
    "harness", "input", "implementation", "integration", "invalid", "level", "missing", "mode",
    "output", "path", "policy", "provider", "repo", "research", "result", "route", "runtime",
    "schema", "script", "solar", "source", "status", "support", "system", "test", "tests",
    "that", "the", "this", "when", "with", "without", "workflow", "writes", "yields",
}


@dataclass
class Item:
    inventory_id: str
    path: str
    symbol: str
    item_type: str
    language: str
    line: int
    public_entrypoint: str
    entrypoint_kind: str
    source_scope: str
    classification: str = "needs-human-review"
    mapped_feature_id: str = ""
    mapping_confidence: str = "none"
    mapping_score: float = 0.0
    mapping_reason: str = ""


def load_sheet(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload["values"]
    headers = [str(value or "") for value in values[0]]
    return [dict(zip(headers, row + [None] * (len(headers) - len(row)))) for row in values[1:]]


def tokens(value: object) -> set[str]:
    text = str(value or "")
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    found = set(re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower()))
    expanded = set(found)
    for token in list(found):
        expanded.update(part for part in re.split(r"[-_]", token) if len(part) >= 3)
    return {token for token in expanded if token not in STOPWORDS and not token.isdigit()}


def is_test_path(path: str) -> bool:
    name = Path(path).name.lower()
    return (
        "/test" in f"/{path.lower()}"
        or name.startswith("test_")
        or name.startswith("test-")
        or ".test." in name
        or ".spec." in name
        or name.endswith("_test.py")
    )


def source_scope(path: str) -> str:
    lowered = path.lower()
    if is_test_path(path):
        return "test"
    if "/vendor/" in f"/{lowered}" or lowered.startswith("vendor/"):
        return "vendor"
    if any(part in lowered for part in ("/dist/", "/build/", "/generated/")):
        return "generated"
    return "production"


def language_for(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python", ".sh": "shell", ".bash": "shell", ".zsh": "shell",
        ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
        ".mjs": "javascript", ".cjs": "javascript", ".rs": "rust", ".go": "go",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".md": "markdown",
        ".toml": "toml", ".sql": "sql",
    }.get(suffix, suffix.lstrip(".") or "unknown")


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def add_item(items: list[Item], path: str, symbol: str, item_type: str, language: str, line: int,
             public: bool, kind: str) -> None:
    scope = source_scope(path)
    if scope == "test":
        classification = "test-only"
    elif scope == "generated":
        classification = "generated"
    elif scope == "vendor":
        classification = "support-only"
    else:
        classification = "needs-human-review"
    items.append(Item(
        inventory_id=f"INV-{len(items)+1:06d}", path=path, symbol=symbol, item_type=item_type,
        language=language, line=line, public_entrypoint="yes" if public else "no",
        entrypoint_kind=kind, source_scope=scope, classification=classification,
    ))


def parse_python(path: str, text: str, items: list[Item]) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        add_item(items, path, Path(path).stem, "python_module_parse_error", "python", 1, False, "module")
        return
    public_module = path.startswith(("bin/", "harness/bin/")) or path.endswith(("cli.py", "__main__.py"))
    add_item(items, path, Path(path).stem, "python_module", "python", 1, public_module, "module/CLI")
    parents: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            symbol = ".".join(parents + [node.name])
            add_item(items, path, symbol, "python_class", "python", node.lineno, False, "class")
            parents.append(node.name)
            self.generic_visit(node)
            parents.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            symbol = ".".join(parents + [node.name])
            public = not node.name.startswith("_") and not parents and public_module
            add_item(items, path, symbol, "python_function", "python", node.lineno, public, "function")
            parents.append(node.name)
            self.generic_visit(node)
            parents.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

    Visitor().visit(tree)
    if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", text):
        match = re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", text)
        add_item(items, path, "__main__", "python_cli", "python", line_number(text, match.start()), True, "CLI")
    for match in re.finditer(r"\.add_parser\(\s*['\"]([^'\"]+)['\"]", text):
        add_item(items, path, match.group(1), "python_cli_subcommand", "python",
                 line_number(text, match.start()), True, "CLI subcommand")


def parse_shell(path: str, text: str, items: list[Item]) -> None:
    public = path.startswith(("bin/", "harness/bin/", "hooks/")) or Path(path).name in {
        "install.sh", "uninstall.sh", "setup.sh", "run.sh",
    }
    add_item(items, path, Path(path).name, "shell_script", "shell", 1, public, "script/hook")
    pattern = re.compile(r"(?m)^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_-]*)\s*(?:\(\s*\))?\s*\{")
    for match in pattern.finditer(text):
        add_item(items, path, match.group(1), "shell_function", "shell", line_number(text, match.start()),
                 public and not match.group(1).startswith("_"), "shell function")


def parse_js_ts(path: str, text: str, items: list[Item]) -> None:
    language = language_for(path)
    add_item(items, path, Path(path).stem, f"{language}_module", language, 1,
             path.startswith(("bin/", "core/daemon/")), "module")
    patterns = [
        (r"\b(export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", "function"),
        (r"\b(export\s+)?class\s+([A-Za-z_$][\w$]*)", "class"),
        (r"\bexport\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)", "export"),
        (r"\b(?:router|app|server)\.(get|post|put|patch|delete|use)\s*\(\s*['\"]([^'\"]+)", "route"),
        (r"\bexports\.([A-Za-z_$][\w$]*)\s*=", "export"),
    ]
    for pattern, kind in patterns:
        for match in re.finditer(pattern, text):
            groups = match.groups()
            if kind in {"function", "class"}:
                exported = bool(groups[0])
                symbol = groups[1]
            elif kind == "route":
                exported = True
                symbol = f"{groups[0].upper()} {groups[1]}"
            else:
                exported = True
                symbol = groups[-1]
            add_item(items, path, symbol, f"{language}_{kind}", language, line_number(text, match.start()),
                     exported, "HTTP route" if kind == "route" else kind)


def parse_rust_go(path: str, text: str, items: list[Item]) -> None:
    language = language_for(path)
    add_item(items, path, Path(path).stem, f"{language}_module", language, 1, False, "module")
    if language == "rust":
        pattern = r"(?m)^\s*(pub\s+)?(?:async\s+)?(?:fn|struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)"
    else:
        pattern = r"(?m)^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)"
    for match in re.finditer(pattern, text):
        groups = match.groups()
        public = bool(groups[0]) if language == "rust" else groups[0][:1].isupper()
        symbol = groups[-1]
        add_item(items, path, symbol, f"{language}_symbol", language, line_number(text, match.start()), public, "symbol")


def config_kind(path: str, text: str) -> tuple[str, str, bool]:
    lowered = path.lower()
    if lowered.startswith(".github/workflows/"):
        return "github_action", "CI workflow", True
    if Path(path).name == "SKILL.md" or "/commands/" in lowered:
        return "skill_spec", "slash command/skill", True
    if "schema" in lowered:
        return "schema", "schema", True
    if "manifest" in lowered or "component" in lowered:
        return "component_manifest", "component manifest", True
    if "route" in lowered or '"routes"' in text[:10000]:
        return "route_config", "route config", True
    if "capability" in lowered or "capsule" in lowered:
        return "capability_spec", "capability", True
    return "configuration", "config", False


def extract_test_cases(path: str, text: str) -> list[str]:
    cases = []
    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
            cases.extend(node.name for node in ast.walk(tree)
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"))
        except SyntaxError:
            pass
    elif Path(path).suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        cases.extend(match.group(2) for match in re.finditer(
            r"\b(describe|it|test)\s*\(\s*['\"]([^'\"]+)['\"]", text))
    elif Path(path).suffix.lower() in {".sh", ".bash", ".zsh"}:
        cases.extend(match.group(1) for match in re.finditer(r"(?m)^\s*(test_[A-Za-z0-9_-]+)\s*\(\s*\)", text))
    return cases[:200]


def candidate_paths(text: str) -> list[str]:
    results = []
    for chunk in re.split(r"[;\n,]", text):
        cleaned = chunk.strip().strip("`'\"")
        if not cleaned or cleaned in {"repo source tree", "coding agent"}:
            continue
        if "/" in cleaned or cleaned.endswith((".py", ".sh", ".ts", ".js", ".json", ".yaml", ".yml", ".md")):
            cleaned = cleaned.split(" ")[0].rstrip(":")
            results.append(cleaned)
    return results


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    checkout = Path(sys.argv[1]).resolve()
    run_root = Path(sys.argv[2]).resolve()
    previews = run_root / "workbook-previews"
    features = load_sheet(previews / "04-Feature_IDs.data.json")
    entrypoint_seed = {str(row["feature_id"]): row for row in load_sheet(previews / "06-Entrypoint_Map.data.json")}
    missing_seed = {str(row["feature_id"]): row for row in load_sheet(previews / "08-Missing_Test_Plan.data.json")}
    criteria_seed = {str(row["feature_id"]): row for row in load_sheet(previews / "09-Pass_Fail_Criteria.data.json")}

    tracked = subprocess.run(["git", "ls-files"], cwd=checkout, text=True, capture_output=True, check=True).stdout.splitlines()
    artifacts = run_root / "evidence" / "inventory"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "tracked-files.txt").write_text("\n".join(tracked) + "\n", encoding="utf-8")
    source_suffixes = {".py", ".sh", ".bash", ".zsh", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".go", ".json", ".yaml", ".yml", ".toml", ".md", ".sql"}
    source_files = [path for path in tracked if Path(path).suffix.lower() in source_suffixes or Path(path).name == "SKILL.md"]
    (artifacts / "source-files.txt").write_text("\n".join(source_files) + "\n", encoding="utf-8")

    items: list[Item] = []
    test_files: list[dict[str, object]] = []
    package_scripts: list[dict[str, str]] = []
    file_text: dict[str, str] = {}
    for relative in source_files:
        path = checkout / relative
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        file_text[relative] = text
        suffix = path.suffix.lower()
        if suffix == ".py":
            parse_python(relative, text, items)
        elif suffix in {".sh", ".bash", ".zsh"} or text.startswith("#!/bin/bash") or text.startswith("#!/usr/bin/env bash"):
            parse_shell(relative, text, items)
        elif suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            parse_js_ts(relative, text, items)
        elif suffix in {".rs", ".go"}:
            parse_rust_go(relative, text, items)
        elif suffix in {".json", ".yaml", ".yml", ".toml", ".md"}:
            kind, entry_kind, public = config_kind(relative, text)
            if public:
                add_item(items, relative, Path(relative).name, kind, language_for(relative), 1, public, entry_kind)

        if Path(relative).name == "package.json":
            try:
                payload = json.loads(text)
                for name, command in (payload.get("scripts") or {}).items():
                    package_scripts.append({"path": relative, "script": name, "command": str(command)})
                    add_item(items, relative, name, "package_script", "json", 1, True, "package script")
            except json.JSONDecodeError:
                pass
        if is_test_path(relative):
            test_files.append({
                "path": relative,
                "language": language_for(relative),
                "cases": extract_test_cases(relative, text),
                "size_bytes": path.stat().st_size,
            })

    (artifacts / "test-files.txt").write_text("\n".join(str(row["path"]) for row in test_files) + "\n", encoding="utf-8")
    (artifacts / "package-scripts.json").write_text(json.dumps(package_scripts, indent=2) + "\n", encoding="utf-8")
    (artifacts / "test-cases.json").write_text(json.dumps(test_files, indent=2) + "\n", encoding="utf-8")

    feature_by_id = {str(feature["feature_id"]): feature for feature in features}
    feature_tokens: dict[str, set[str]] = {}
    feature_hints: dict[str, list[str]] = {}
    token_to_features: dict[str, set[str]] = defaultdict(set)
    for feature_id, feature in feature_by_id.items():
        seed = entrypoint_seed.get(feature_id, {})
        combined = " ".join(str(feature.get(key) or "") for key in (
            "level 1 features", "level 2 feature", "level 3 feature", "level 4 feature",
            "atomic feature", "feature path", "suggested test focus", "source / basis",
        )) + " " + " ".join(str(seed.get(key) or "") for key in (
            "primary entrypoint candidates", "input class", "output contract / evidence schema",
        ))
        current_tokens = tokens(combined)
        feature_tokens[feature_id] = current_tokens
        for token in current_tokens:
            token_to_features[token].add(feature_id)
        feature_hints[feature_id] = candidate_paths(str(feature.get("source / basis") or "")) + candidate_paths(
            str(seed.get("primary entrypoint candidates") or ""))

    token_df = {token: len(ids) for token, ids in token_to_features.items()}
    feature_to_items: dict[str, list[Item]] = defaultdict(list)
    unmapped_public = []
    for item in items:
        item_token_set = tokens(f"{item.path} {item.symbol} {item.item_type} {item.entrypoint_kind}")
        candidates: set[str] = set()
        for token in item_token_set:
            if token_df.get(token, 999999) <= 250:
                candidates.update(token_to_features.get(token, ()))
        scored: list[tuple[float, str, str]] = []
        for feature_id in candidates:
            overlap = item_token_set & feature_tokens[feature_id]
            score = sum(math.log((len(features) + 1) / (token_df[token] + 1)) for token in overlap)
            hint_matches = []
            for hint in feature_hints[feature_id]:
                normalized_hint = hint.lstrip("./").replace("**", "*")
                if normalized_hint and (
                    fnmatch.fnmatch(item.path, normalized_hint)
                    or item.path == normalized_hint
                    or item.path.startswith(normalized_hint.rstrip("/*") + "/")
                    or normalized_hint.rstrip("/*") in item.path
                ):
                    score += 8.0
                    hint_matches.append(hint)
            if score > 0:
                reason = f"token overlap: {', '.join(sorted(overlap)[:8])}"
                if hint_matches:
                    reason += f"; seeded path match: {hint_matches[0]}"
                scored.append((score, feature_id, reason))
        if scored:
            score, feature_id, reason = max(scored)
            item.mapping_score = round(score, 3)
            item.mapping_reason = reason
            if score >= 10:
                item.mapping_confidence = "high"
            elif score >= 5:
                item.mapping_confidence = "medium"
            elif score >= 2.5:
                item.mapping_confidence = "low"
            if item.mapping_confidence != "none":
                item.mapped_feature_id = feature_id
                if item.classification == "needs-human-review":
                    item.classification = "mapped"
                feature_to_items[feature_id].append(item)
        if not item.mapped_feature_id and item.public_entrypoint == "yes" and item.source_scope == "production":
            item.classification = "missing-feature-row"
            unmapped_public.append(item)
        elif not item.mapped_feature_id and item.classification == "needs-human-review":
            item.classification = "support-only"

    function_rows = []
    for item in items:
        row = asdict(item)
        row["mapping_score"] = f"{item.mapping_score:.3f}"
        function_rows.append(row)
    write_csv(run_root / "function-inventory.csv", function_rows)

    test_feature_candidates: dict[str, list[tuple[float, dict[str, object], list[str], bool, str]]] = defaultdict(list)
    for test_file in test_files:
        path = str(test_file["path"])
        text = file_text.get(path, "")
        test_name_text = path + " " + " ".join(test_file["cases"])
        test_token_set = tokens(test_name_text)
        normalized_test_name = re.sub(r"[^a-z0-9]+", "_", test_name_text.lower())
        candidate_ids: set[str] = set()
        for token in test_token_set:
            if token_df.get(token, 999999) <= 120:
                candidate_ids.update(token_to_features.get(token, ()))
        for feature_id in candidate_ids:
            overlap = test_token_set & feature_tokens[feature_id]
            weighted = sum(math.log((len(features) + 1) / (token_df[token] + 1)) for token in overlap)
            direct_reasons = []
            feature = feature_by_id[feature_id]
            atomic_slug = re.sub(r"[^a-z0-9]+", "_", str(feature["atomic feature"]).lower()).strip("_")
            if len(atomic_slug) >= 12 and atomic_slug in normalized_test_name:
                weighted += 12
                direct_reasons.append("atomic feature slug appears in test name/case")
            if feature_id.lower() in text.lower():
                weighted += 20
                direct_reasons.append("feature ID appears in test source")
            implementation_stems = {
                Path(item.path).stem.lower().replace("-", "_")
                for item in feature_to_items.get(feature_id, [])[:10]
                if len(Path(item.path).stem) >= 5
            }
            for hint in feature_hints[feature_id]:
                stem = Path(hint.rstrip("/*")).stem.lower()
                if len(stem) >= 4 and stem in path.lower():
                    weighted += 4
                    direct_reasons.append(f"seeded implementation stem `{stem}` appears in test path")
            for stem in implementation_stems:
                if stem in normalized_test_name:
                    weighted += 4
                    direct_reasons.append(f"mapped implementation stem `{stem}` appears in test name")
                    break
            distinctive_overlap = [token for token in overlap if token_df.get(token, 999999) <= 60]
            direct_signal = bool(direct_reasons) and len(distinctive_overlap) >= 2
            if weighted >= 2.0 and overlap:
                test_feature_candidates[feature_id].append(
                    (weighted, test_file, sorted(overlap), direct_signal, "; ".join(direct_reasons))
                )

    entry_rows = []
    existing_rows = []
    missing_rows = []
    criteria_rows = []
    features_without_mapped_items = []
    stale_candidates = []
    tracked_set = set(tracked)
    for feature in features:
        feature_id = str(feature["feature_id"])
        seed = entrypoint_seed.get(feature_id, {})
        mapped_items = sorted(feature_to_items.get(feature_id, []), key=lambda item: item.mapping_score, reverse=True)
        primary = [item for item in mapped_items if item.public_entrypoint == "yes"][:5]
        implementations = mapped_items[:8]
        if not implementations:
            features_without_mapped_items.append(feature_id)
        hints = feature_hints.get(feature_id, [])
        missing_hints = [hint for hint in hints if not any(
            fnmatch.fnmatch(path, hint.lstrip("./"))
            or path.startswith(hint.lstrip("./").rstrip("/*") + "/")
            or hint.lstrip("./").rstrip("/*") in path
            for path in tracked_set
        )]
        if hints and len(missing_hints) == len(hints) and not implementations:
            stale_candidates.append((feature_id, hints))
        entry_rows.append({
            "feature_id": feature_id,
            "parts": feature["parts"],
            "atomic_feature": feature["atomic feature"],
            "feature_path": feature["feature path"],
            "seeded_entrypoint_candidates": seed.get("primary entrypoint candidates") or "",
            "discovered_entrypoints": "; ".join(f"{item.path}::{item.symbol}" for item in primary),
            "implementation_files_functions": "; ".join(f"{item.path}::{item.symbol}" for item in implementations),
            "entrypoint_type": seed.get("entrypoint type") or "; ".join(sorted({item.entrypoint_kind for item in primary})),
            "input_class": seed.get("input class") or "",
            "output_contract_evidence_schema": seed.get("output contract / evidence schema") or "",
            "side_effect_policy": seed.get("side-effect policy") or "",
            "expected_artifacts": seed.get("expected artifacts") or "",
            "mapping_confidence": primary[0].mapping_confidence if primary else (implementations[0].mapping_confidence if implementations else "none"),
            "mapping_basis": primary[0].mapping_reason if primary else (implementations[0].mapping_reason if implementations else "no static candidate matched"),
        })

        candidates = sorted(test_feature_candidates.get(feature_id, []), key=lambda row: row[0], reverse=True)[:5]
        best_score = candidates[0][0] if candidates else 0.0
        best_direct_signal = candidates[0][3] if candidates else False
        best_direct_basis = candidates[0][4] if candidates else ""
        best_distinctive_overlap = [
            token for token in (candidates[0][2] if candidates else [])
            if token_df.get(token, 999999) <= 60
        ]
        side_effect = str(seed.get("side-effect policy") or "").lower()
        feature_text = str(feature["feature path"]).lower()
        if best_direct_signal and best_score >= 7:
            coverage = "direct"
            confidence = "high"
        elif best_direct_basis and best_score >= 5:
            coverage = "partial"
            confidence = "medium"
        elif len(best_distinctive_overlap) >= 2 and best_score >= 4:
            coverage = "indirect"
            confidence = "low"
        elif any(word in side_effect for word in ("approval", "remote", "network", "provider", "email", "destructive")):
            coverage = "gated"
            confidence = "medium"
        elif any(word in feature_text for word in ("manual", "visual", "desktop", "browser profile", "remote")):
            coverage = "manual-only"
            confidence = "medium"
        else:
            coverage = "missing"
            confidence = "medium"
        existing_rows.append({
            "feature_id": feature_id,
            "parts": feature["parts"],
            "atomic_feature": feature["atomic feature"],
            "feature_path": feature["feature path"],
            "existing_test_files": "; ".join(str(row[1]["path"]) for row in candidates),
            "existing_test_cases": "; ".join(
                ", ".join(str(case) for case in row[1]["cases"][:8]) for row in candidates if row[1]["cases"]
            ),
            "coverage_status": coverage,
            "test_confidence": confidence,
            "direct_test_present": "yes" if coverage == "direct" else "no",
            "indirect_smoke_present": "yes" if coverage in {"direct", "partial", "indirect"} else "no",
            "verification_command": "pytest/shell/package command selected during deterministic execution; see command-log.tsv",
            "mapping_evidence": "; ".join(
                f"score={row[0]:.2f} overlap={','.join(row[2][:8])} direct_signal={str(row[3]).lower()} basis={row[4]}" for row in candidates
            ),
            "gap_to_confirm": "Run/inspect candidate tests and validate output contracts; heuristic mapping is not proof." if candidates else "No candidate existing test found by static scan.",
        })

        missing = missing_seed.get(feature_id, {})
        missing_status = "covered-direct" if coverage == "direct" else "recommended"
        if coverage == "gated":
            missing_status = "gated-test-recommended"
        elif coverage == "manual-only":
            missing_status = "manual-automation-recommended"
        missing_rows.append({
            "feature_id": feature_id,
            "parts": feature["parts"],
            "atomic_feature": feature["atomic feature"],
            "feature_path": feature["feature path"],
            "missing_test_status": missing_status,
            "required_test_type": missing.get("required test type") or ("approval-gate" if coverage == "gated" else "direct deterministic"),
            "suggested_test_name": missing.get("suggested test name") or f"test_{re.sub('[^a-z0-9]+', '_', str(feature['atomic feature']).lower()).strip('_')[:80]}",
            "fixture_needed": missing.get("fixture needed") or feature.get("suggested test focus") or "feature-specific positive and negative fixture",
            "command_entrypoint_to_exercise": missing.get("command / entrypoint to exercise") or seed.get("primary entrypoint candidates") or "needs entrypoint confirmation",
            "expected_result": missing.get("expected result") or f"Meets atomic contract: {feature['base-case rationale']}",
            "priority_risk": missing.get("priority / risk") or "P2",
            "recommendation": "Add a feature-ID-tagged direct test that validates schema/artifact/side-effect contract, not only exit code." if coverage != "direct" else "Retain and strengthen contract assertions when touching this surface.",
        })

        criteria = criteria_seed.get(feature_id, {})
        criteria_rows.append({
            "feature_id": feature_id,
            "parts": feature["parts"],
            "atomic_feature": feature["atomic feature"],
            "feature_path": feature["feature path"],
            "happy_path_pass_criteria": criteria.get("happy-path pass criteria") or f"Feature produces its documented output and artifacts for {feature['suggested test focus']}.",
            "negative_failure_pass_criteria": criteria.get("negative / failure pass criteria") or "Invalid/missing input is rejected with structured evidence and no hidden side effect.",
            "fail_criteria": criteria.get("fail criteria") or "Crash, unstructured success, contract/schema mismatch, unauthorized mutation, hidden provider/live claim, or malformed evidence acceptance.",
            "allowed_result_classifications": criteria.get("allowed result classifications") or "PASS; FAIL; BLOCKED_EXPECTED; INCONCLUSIVE_EXPECTED; SKIPPED_NA; SKIPPED_ENV; FLAKY; NOT_RUN",
            "expected_evidence": criteria.get("expected evidence") or "command log; stdout/stderr; result artifact; schema validation",
            "gated_handling": criteria.get("gated handling") or "Correct typed approval/continuation blocking is BLOCKED_EXPECTED.",
            "priority_risk": criteria.get("priority / risk") or "P2",
        })

    write_csv(run_root / "feature-entrypoint-map.csv", entry_rows)
    write_csv(run_root / "feature-existing-test-map.csv", existing_rows)
    write_csv(run_root / "missing-test-plan.csv", missing_rows)
    write_csv(run_root / "pass-fail-criteria.csv", criteria_rows)

    feature_paths = Counter(str(row["feature path"]).strip().lower() for row in features)
    atomic_names = Counter(str(row["atomic feature"]).strip().lower() for row in features)
    duplicate_paths = [name for name, count in feature_paths.items() if count > 1]
    duplicate_atomic = [name for name, count in atomic_names.items() if count > 1]
    part_counts = Counter(str(row["parts"]) for row in features)
    classification_counts = Counter(item.classification for item in items)
    item_type_counts = Counter(item.item_type for item in items)
    coverage_counts = Counter(row["coverage_status"] for row in existing_rows)
    diff_lines = [
        "# Inventory Diff",
        "",
        "## Control taxonomy baseline",
        "",
        f"- Atomic feature rows: {len(features)}",
        f"- By part: {dict(part_counts)}",
        f"- Duplicate feature paths: {len(duplicate_paths)}",
        f"- Duplicate atomic labels (labels only; paths may differ legitimately): {len(duplicate_atomic)}",
        "",
        "## Repository surfaces discovered",
        "",
        f"- Tracked files at locked SHA: {len(tracked)}",
        f"- Scannable source/config/spec files: {len(source_files)}",
        f"- Function/module/route/script/package/config inventory rows: {len(items)}",
        f"- Existing test files: {len(test_files)}",
        f"- Package scripts: {len(package_scripts)}",
        f"- Inventory classifications: {dict(classification_counts)}",
        f"- Top item types: {dict(item_type_counts.most_common(20))}",
        "",
        "## Taxonomy reconciliation",
        "",
        f"- Feature rows without a static implementation/entrypoint candidate: {len(features_without_mapped_items)}",
        f"- Candidate stale rows (all seeded path hints absent and no mapped implementation): {len(stale_candidates)}",
        f"- Public production entrypoints with no feature mapping (`missing-feature-row`): {len(unmapped_public)}",
        f"- Static existing-test coverage classifications: {dict(coverage_counts)}",
        "",
        "These are static candidate classifications, not execution verdicts. Low-confidence mappings require human review; path or token similarity alone is not proof of implementation coverage.",
        "",
        "## Candidate missing feature rows (first 100)",
        "",
    ]
    diff_lines.extend(f"- `{item.path}::{item.symbol}` ({item.item_type})" for item in unmapped_public[:100])
    diff_lines.extend(["", "## Candidate stale taxonomy rows (first 100)", ""])
    diff_lines.extend(f"- `{feature_id}` — seeded hints absent: {', '.join(hints[:5])}" for feature_id, hints in stale_candidates[:100])
    diff_lines.extend(["", "## Duplicate feature paths", ""])
    diff_lines.extend(f"- {name}" for name in duplicate_paths[:100])
    (run_root / "inventory-diff.md").write_text("\n".join(diff_lines) + "\n", encoding="utf-8")

    summary = {
        "features": len(features),
        "part_counts": part_counts,
        "tracked_files": len(tracked),
        "source_files": len(source_files),
        "inventory_items": len(items),
        "test_files": len(test_files),
        "package_scripts": len(package_scripts),
        "classification_counts": classification_counts,
        "coverage_counts": coverage_counts,
        "features_without_mapped_items": len(features_without_mapped_items),
        "candidate_stale_rows": len(stale_candidates),
        "unmapped_public_entrypoints": len(unmapped_public),
        "duplicate_feature_paths": len(duplicate_paths),
        "duplicate_atomic_labels": len(duplicate_atomic),
    }
    (artifacts / "inventory-summary.json").write_text(json.dumps(summary, indent=2, default=dict) + "\n", encoding="utf-8")
    print(json.dumps(summary, default=dict))


if __name__ == "__main__":
    main()
