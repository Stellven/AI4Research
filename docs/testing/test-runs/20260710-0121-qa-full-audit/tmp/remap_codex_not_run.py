from __future__ import annotations

import ast
import csv
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


STOPWORDS = {
    "about", "action", "actual", "agent", "allowed", "and", "artifact", "atomic", "auto",
    "candidate", "class", "code", "command", "component", "config", "contract", "correct",
    "data", "default", "direct", "entrypoint", "evidence", "expected", "feature", "file", "files",
    "function", "generated", "harness", "input", "implementation", "integration", "invalid", "level",
    "local", "missing", "mode", "operator", "output", "path", "policy", "provider", "repo", "research",
    "result", "route", "runtime", "schema", "script", "solar", "source", "status", "support", "surface",
    "system", "test", "tests", "that", "the", "this", "when", "with", "without", "workflow", "writes",
    "yields", "v1", "only", "from", "into", "becomes", "reports", "emits", "be", "has", "have",
}

GENERIC_SYMBOLS = {
    "main", "run", "load", "save", "build", "validate", "parse", "execute", "handler", "cli",
    "status", "doctor", "list", "get", "set", "read", "write", "create", "update", "check",
}


@dataclass
class TestRecord:
    path: str
    nodeid: str
    name: str
    body: str
    tokens: set[str]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def tokenize(value: str) -> set[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    raw = set(re.findall(r"[a-z0-9][a-z0-9_.-]{1,}", text.lower()))
    expanded = set(raw)
    for token in list(raw):
        expanded.update(part for part in re.split(r"[._/-]", token) if len(part) >= 3)
    return {token for token in expanded if len(token) >= 3 and token not in STOPWORDS and not token.isdigit()}


def is_test_path(path: str) -> bool:
    name = Path(path).name.lower()
    return (
        name.startswith("test_")
        or name.startswith("test-")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
        or "/tests/" in f"/{path.lower()}"
    ) and Path(path).suffix.lower() in {".py", ".sh", ".bash", ".zsh", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def tracked_files(checkout: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=checkout, check=True, stdout=subprocess.PIPE,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def python_test_records(path: str, text: str) -> list[TestRecord]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    records: list[TestRecord] = []
    class_stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            class_stack.append(node.name)
            self.generic_visit(node)
            class_stack.pop()

        def _visit_test(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            if node.name.startswith("test"):
                body = ast.get_source_segment(text, node) or ""
                pieces = [*class_stack, node.name]
                nodeid = path + "::" + "::".join(pieces)
                records.append(TestRecord(path, nodeid, node.name, body, tokenize(path + " " + node.name + " " + body)))
            self.generic_visit(node)

        visit_FunctionDef = _visit_test
        visit_AsyncFunctionDef = _visit_test

    Visitor().visit(tree)
    return records


def shell_test_records(path: str, text: str) -> list[TestRecord]:
    records: list[TestRecord] = []
    function_pattern = re.compile(
        r"(?ms)^\s*(test_[A-Za-z0-9_-]+)\s*\(\s*\)\s*\{(.*?)(?=^\s*\}|\Z)"
    )
    for match in function_pattern.finditer(text):
        name = match.group(1)
        body = match.group(0)
        records.append(TestRecord(path, path, name, body, tokenize(path + " " + name + " " + body)))
    if not records:
        records.append(TestRecord(path, path, Path(path).stem, text, tokenize(path + " " + text)))
    return records


def js_test_records(path: str, text: str) -> list[TestRecord]:
    names = [match.group(2) for match in re.finditer(r"\b(describe|it|test)\s*\(\s*['\"]([^'\"]+)['\"]", text)]
    label = "; ".join(names[:30]) or Path(path).stem
    return [TestRecord(path, path, label, text, tokenize(path + " " + label + " " + text))]


def build_test_records(checkout: Path) -> list[TestRecord]:
    records: list[TestRecord] = []
    for relative in tracked_files(checkout):
        if not is_test_path(relative):
            continue
        path = checkout / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        suffix = path.suffix.lower()
        if suffix == ".py":
            extracted = python_test_records(relative, text)
        elif suffix in {".sh", ".bash", ".zsh"}:
            extracted = shell_test_records(relative, text)
        else:
            extracted = js_test_records(relative, text)
        if not extracted:
            extracted = [TestRecord(relative, relative, Path(relative).stem, text, tokenize(relative + " " + text))]
        records.extend(extracted)
    return records


def split_impl(value: str) -> list[tuple[str, str]]:
    result = []
    for item in value.split(";"):
        item = item.strip()
        if not item:
            continue
        if "::" in item:
            path, symbol = item.rsplit("::", 1)
        else:
            path, symbol = item, ""
        path = path.strip()
        symbol = symbol.strip().split(".")[-1]
        if is_test_path(path) or symbol.startswith("test_") or symbol == "__main__":
            continue
        result.append((path, symbol))
    return result


def surface_keys(feature_path: str) -> list[str]:
    surface = feature_path.split(">", 1)[0].strip()
    label = surface.split(":", 1)[1].strip() if ":" in surface else surface
    keys = []
    for value in (surface, label):
        keys.extend(re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{2,}", value))
    return sorted({key.lower() for key in keys if key.lower() not in STOPWORDS}, key=len, reverse=True)


def main() -> int:
    audit_root = Path(sys.argv[1]).resolve()
    checkout = Path(sys.argv[2]).resolve()
    scope_rows = read_csv(audit_root / "evidence" / "codex-not-run-phase" / "not-run-scope-classification.csv")
    features = [row for row in scope_rows if row["scope_classification"] == "INCLUDED_CODEX_RELEVANT"]
    tests = build_test_records(checkout)

    token_df: Counter[str] = Counter()
    inverted: dict[str, set[int]] = defaultdict(set)
    for index, record in enumerate(tests):
        for token in record.tokens:
            token_df[token] += 1
            inverted[token].add(index)

    output_rows: list[dict[str, object]] = []
    candidate_count = Counter()
    selected_targets: dict[str, set[str]] = defaultdict(set)
    for feature in features:
        feature_text = " ".join((feature["atomic_feature"], feature["feature_path"]))
        feature_tokens = tokenize(feature["atomic_feature"])
        search_tokens = feature_tokens | tokenize(feature["feature_path"])
        implementations = split_impl(feature["implementation_files_functions"])
        entrypoints = split_impl(feature["entrypoints"])
        impl_paths = {path for path, _ in implementations + entrypoints if "/" in path or "." in Path(path).name}
        impl_symbols = {
            symbol for _, symbol in implementations + entrypoints
            if len(symbol) >= 5 and symbol.lower() not in GENERIC_SYMBOLS
        }
        stems = {
            Path(path.rstrip("/*")).stem.lower().replace("-", "_")
            for path in impl_paths
            if len(Path(path.rstrip("/*")).stem) >= 5
        }
        keys = surface_keys(feature["feature_path"])
        schema_keys = set(re.findall(r"\b[a-z][a-z0-9_]+\.v[0-9]+\b", feature_text.lower()))

        candidate_indices: set[int] = set()
        for token in search_tokens:
            if token_df[token] <= 250:
                candidate_indices.update(inverted.get(token, ()))
        for key in keys:
            for token in tokenize(key):
                candidate_indices.update(inverted.get(token, ()))

        scored = []
        for index in candidate_indices:
            record = tests[index]
            body_lower = record.body.lower()
            path_name_lower = (record.path + " " + record.name).lower().replace("-", "_")
            overlap = feature_tokens & record.tokens
            distinctive = {token for token in overlap if token_df[token] <= 80}
            weighted_overlap = sum(math.log((len(tests) + 1) / (token_df[token] + 1)) for token in overlap)
            score = weighted_overlap
            reasons: list[str] = []
            direct_signal = False
            strong_contract_signal = False

            if feature["feature_id"].lower() in body_lower:
                score += 100
                reasons.append("feature_id_in_test")
                direct_signal = True
                strong_contract_signal = True
            for schema in schema_keys:
                if schema in body_lower:
                    score += 45
                    reasons.append(f"schema:{schema}")
                    direct_signal = True
                    strong_contract_signal = True
            for symbol in impl_symbols:
                if re.search(rf"\b{re.escape(symbol.lower())}\b", body_lower):
                    score += 30
                    reasons.append(f"symbol:{symbol}")
                    direct_signal = True
            for path in impl_paths:
                normalized_path = path.lower().replace("\\", "/")
                if normalized_path in body_lower:
                    score += 35
                    reasons.append(f"impl_path:{path}")
                    direct_signal = True
            for stem in stems:
                if stem in path_name_lower:
                    score += 25
                    reasons.append(f"test_path_stem:{stem}")
                    direct_signal = True
                elif stem in body_lower:
                    score += 10
                    reasons.append(f"body_stem:{stem}")
            for key in keys[:8]:
                normalized_key = re.sub(r"[^a-z0-9]+", "_", key.lower())
                key_tokens = tokenize(key)
                key_is_distinctive = bool(key_tokens) and all(token_df[token] <= 80 for token in key_tokens)
                if len(normalized_key) >= 5 and key_is_distinctive and normalized_key in path_name_lower:
                    score += 18
                    reasons.append(f"surface_key:{key}")
                    direct_signal = True
                    break
            assertion_signal = bool(re.search(r"\b(assert|expect\s*\(|assert_|grep\s+-q|jq\s+-e|exit\s+1)\b", record.body))
            if assertion_signal:
                score += 3
            if len(distinctive) >= 2:
                score += 5
            if strong_contract_signal and assertion_signal:
                classification = "direct_candidate"
            elif direct_signal and assertion_signal and len(distinctive) >= 2:
                classification = "direct_candidate"
            elif direct_signal and assertion_signal:
                classification = "partial_candidate"
            elif assertion_signal and len(distinctive) >= 2:
                classification = "indirect_candidate"
            else:
                classification = "weak_candidate"
            if score >= 8:
                scored.append((score, classification, record, sorted(distinctive), reasons, assertion_signal))

        scored.sort(key=lambda item: (item[0], item[1] == "direct_candidate"), reverse=True)
        accepted = [item for item in scored if item[1] in {"direct_candidate", "partial_candidate"}][:5]
        if not accepted:
            accepted = [item for item in scored if item[1] == "indirect_candidate"][:3]

        best_classification = accepted[0][1] if accepted else "unmapped"
        candidate_count[best_classification] += 1
        for _, _, record, _, _, _ in accepted:
            selected_targets[record.path].add(feature["feature_id"])
        output_rows.append(
            {
                "feature_id": feature["feature_id"],
                "parts": feature["parts"],
                "atomic_feature": feature["atomic_feature"],
                "feature_path": feature["feature_path"],
                "prior_coverage_status": feature["coverage_status"],
                "prior_blocker": feature["eligible_phase_scope"],
                "remap_classification": best_classification,
                "selected_test_targets": ";".join(sorted({item[2].path for item in accepted})),
                "selected_testcases": ";".join(item[2].nodeid for item in accepted),
                "mapping_scores": ";".join(f"{item[0]:.2f}" for item in accepted),
                "mapping_reasons": " || ".join(",".join(item[4]) for item in accepted),
                "distinctive_overlap": " || ".join(",".join(item[3]) for item in accepted),
                "manual_review_required": "yes" if best_classification != "direct_candidate" else "no",
            }
        )

    out_dir = audit_root / "evidence" / "codex-not-run-phase"
    feature_fields = list(output_rows[0])
    write_csv(out_dir / "feature-test-remap.csv", output_rows, feature_fields)
    target_rows = [
        {"test_target": path, "linked_feature_count": len(ids), "linked_feature_ids": ";".join(sorted(ids))}
        for path, ids in sorted(selected_targets.items())
    ]
    write_csv(out_dir / "candidate-target-feature-map.csv", target_rows, ["test_target", "linked_feature_count", "linked_feature_ids"])
    summary = {
        "schema": "qa.codex_not_run_remap.v1",
        "feature_count": len(features),
        "test_record_count": len(tests),
        "candidate_target_count": len(selected_targets),
        "classification_counts": dict(sorted(candidate_count.items())),
        "note": "Candidates require assertion-level review before results can promote an atomic feature.",
    }
    (out_dir / "remap-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
