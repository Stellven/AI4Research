#!/usr/bin/env python3
"""Generate a repo-derived QA feature inventory and coverage matrix.

The generator is intentionally conservative:
- It reads tracked files from git, not local caches or generated runtime state.
- It extracts explicit entrypoints: package scripts, CLI commands, shell scripts,
  routes, workflow jobs, SKILL.md files, and test files.
- It does not execute product code, install dependencies, or access the network.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "testing"


@dataclass
class Feature:
    feature_id: str
    l1: str
    l2: str
    l3: str
    source_type: str
    source_paths: str
    entrypoints: str
    existing_tests: str
    coverage_status: str
    pass_criteria: str
    why_testable: str
    notes: str = ""


def git_ls_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def slug(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "item"


def stable_id(*parts: str) -> str:
    return ".".join(slug(p) for p in parts if p)


def uniq_feature_id(base: str, seen: Counter[str]) -> str:
    seen[base] += 1
    if seen[base] == 1:
        return base
    return f"{base}.{seen[base]}"


def tracked_tests(files: Iterable[str]) -> list[str]:
    test_prefixes = (
        "tests/",
        "harness/tests/",
        "distribution/pipx/tests/",
        "skills/fast-browser-use/tests/",
        "skills/email-to-calendar/scripts/tests/",
    )
    tests = []
    for f in files:
        name = Path(f).name
        if f.startswith(test_prefixes):
            tests.append(f)
        elif name.startswith("test-") or name.startswith("test_") or ".test." in name:
            if f.endswith((".py", ".sh", ".ts", ".js", ".ps1", ".rs")):
                tests.append(f)
    return sorted(set(tests))


DOMAIN_RULES: list[tuple[str, tuple[str, str]]] = [
    ("distribution/pipx", ("Packaging", "pipx distribution")),
    ("desktop/", ("Desktop", "Electron shell")),
    ("harness/status-server/react-app", ("Dashboard", "React status dashboard")),
    ("harness/plugins/autosci", ("AutoSci", "AutoSci plugin bridge")),
    ("harness/evaluators/scientific", ("AutoSci", "Scientific evaluators")),
    ("docs/integrations/autosci", ("AutoSci", "Integration docs and evidence")),
    ("harness/lib/symphony/status-server.py", ("Status Server", "Python HTTP status server")),
    ("harness/lib/research/sources", ("Ingestion", "Research source adapters")),
    ("harness/lib/research/extractors", ("Ingestion", "Research source extractors")),
    ("harness/lib/research/survey", ("Research", "Survey workflow")),
    ("harness/lib/research/", ("Research", "DeepResearch core")),
    ("harness/lib/mineru", ("Ingestion", "Document extraction")),
    ("harness/lib/source_", ("Ingestion", "Source data plane")),
    ("harness/lib/hf_paper_insight", ("Ingestion", "Research paper insight")),
    ("harness/lib/youtube", ("Ingestion", "YouTube/video intelligence")),
    ("tools/prepare_paper_source.py", ("Ingestion", "Research paper preparation")),
    ("tools/fetch_arxiv.py", ("Ingestion", "arXiv fetch")),
    ("tools/fetch_s2.py", ("Ingestion", "Semantic Scholar fetch")),
    ("tools/fetch_deepxiv.py", ("Ingestion", "DeepXiv fetch")),
    ("tools/fetch_wikipedia.py", ("Ingestion", "Wikipedia/URL fetch")),
    ("tools/daily_arxiv.py", ("Ingestion", "Daily arXiv discovery")),
    ("tools/discover.py", ("Ingestion", "Research discovery")),
    ("tools/rasterize_latex.py", ("Ingestion", "LaTeX/math rendering")),
    ("harness/lib/ai_influence_youtube_report", ("Reports", "AI influence report")),
    ("harness/lib/github_intelligence", ("Reports", "GitHub intelligence")),
    ("harness/lib/social_browser_backend_x", ("Browser", "Social browser backend")),
    ("harness/lib/browser", ("Browser", "Browser runtime")),
    ("harness/lib/benchmark", ("Benchmarks", "Benchmark runtime")),
    ("harness/lib/graph", ("Harness", "Graph orchestration")),
    ("harness/lib/", ("Harness", "Python runtime library")),
    ("harness/tests/", ("Tests", "Harness test suite")),
    ("harness/", ("Harness", "Solar-Harness shell/runtime")),
    ("core/daemon", ("Core", "Daemon runtime")),
    ("core/orchestrator", ("Core", "Orchestrator")),
    ("core/config", ("Core", "Configuration")),
    ("core/security", ("Security", "Security daemon")),
    ("core/dashboard", ("Dashboard", "Core dashboard")),
    ("core/tvs", ("TVS", "Terminal visual system")),
    ("core/", ("Core", "TypeScript runtime")),
    ("skills/", ("Skills", "Shipped skills")),
    (".agents/skills/", ("Skills", "Agent skill wrappers")),
    ("components.d/", ("Components", "Component manifests")),
    ("lib/installer/", ("Installer", "Installer library")),
    ("scripts/", ("QA Gates", "Repository scripts")),
    ("hooks/", ("Hooks", "Runtime hooks")),
    ("runtime/", ("Runtime", "Schemas and policies")),
    ("docs/", ("Docs", "Documentation")),
    ("templates/", ("Templates", "Renderable templates")),
]


def classify_path(path: str) -> tuple[str, str]:
    for prefix, pair in DOMAIN_RULES:
        if path.startswith(prefix):
            return pair
    top = path.split("/", 1)[0] if "/" in path else path
    return ("Repository", top)


def test_tokens(path: str) -> set[str]:
    base = Path(path).stem.lower()
    pieces = re.split(r"[^a-z0-9]+", path.lower())
    return {p for p in pieces + re.split(r"[^a-z0-9]+", base) if len(p) >= 3}


def map_tests(feature: Feature, tests: list[str], limit: int = 10) -> list[str]:
    hay = " ".join(
        [
            feature.feature_id,
            feature.l1,
            feature.l2,
            feature.l3,
            feature.source_paths,
            feature.entrypoints,
        ]
    ).lower()
    wanted = {p for p in re.split(r"[^a-z0-9]+", hay) if len(p) >= 4}
    scored: list[tuple[int, str]] = []
    for t in tests:
        toks = test_tokens(t)
        score = len(wanted & toks)
        if feature.source_paths and feature.source_paths.split(";")[0]:
            first = feature.source_paths.split(";")[0]
            if first.split("/", 2)[:2] == t.split("/", 2)[:2]:
                score += 1
        if score >= 2:
            scored.append((score, t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:limit]]


def workflow_evidence(files: list[str]) -> dict[str, list[str]]:
    workflows = [f for f in files if f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))]
    evidence: dict[str, list[str]] = defaultdict(list)
    candidates = [f for f in files if f.endswith((".sh", ".py", ".ts", ".js", ".ps1")) or f in {"package.json", "install.sh", "get-solar.sh"}]
    workflow_text = {wf: read_text(wf) for wf in workflows}
    for path in candidates:
        name = Path(path).name
        for wf, text in workflow_text.items():
            if path in text or (name and name in text and len(name) >= 8):
                evidence[path].append(wf)
    return evidence


def coverage_status_for(feature: Feature, matched_tests: list[str]) -> str:
    if matched_tests:
        return "covered"
    if feature.source_type in {"documentation", "manifest", "template", "workflow"}:
        return "static-validation-required"
    if "vendor" in feature.source_paths:
        return "not-owned-vendor"
    if feature.source_type in {"skill", "shell-script", "python-cli", "route", "package-script", "package-bin"}:
        return "missing-or-indirect"
    return "partial-or-unmapped"


def pass_criteria_for(l1: str, l2: str, l3: str, source_type: str) -> str:
    if source_type == "route":
        return "Route returns the documented status, content type, auth behavior, and schema for success and failure cases."
    if source_type == "python-cli":
        return "CLI help parses, fixture invocation exits 0, JSON mode validates when offered, and bad inputs fail with actionable errors."
    if source_type == "shell-script":
        return "Script passes syntax/shell lint where applicable, runs with sandboxed HOME when stateful, and produces expected artifacts or diagnostics."
    if source_type == "package-script":
        return "Package script exits 0 in its intended cwd and produces the expected build/test/report artifact."
    if source_type == "skill":
        return "SKILL.md parses, referenced scripts/assets exist, and behavior-bearing scripts pass their smoke tests or are explicitly integration-gated."
    if source_type == "workflow":
        return "Workflow job commands are mirrored locally or pass in CI, with logs/artifacts captured."
    if source_type in {"manifest", "template", "documentation"}:
        return "Static validation passes: schema/render/link/command checks produce no unexplained errors."
    if "Ingestion" in l1:
        return "Representative fixture input produces structurally valid extracted output and explicit errors for unsupported/corrupt inputs."
    return "Existing test bench or validation command exits 0, expected artifacts are present, and failures are traceable to this feature."


def package_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    out: list[Feature] = []
    for path in sorted(f for f in files if f.endswith("package.json")):
        try:
            payload = json.loads(read_text(path))
        except Exception:
            continue
        l1, l2 = classify_path(path)
        pkg_name = payload.get("name") or Path(path).parent.name or "package"
        for name, target in sorted((payload.get("scripts") or {}).items()):
            fid = uniq_feature_id(stable_id(l1, pkg_name, "script", name), seen)
            out.append(
                Feature(
                    fid,
                    l1,
                    l2,
                    f"package script: {name}",
                    "package-script",
                    path,
                    f"npm/bun script -> {target}",
                    "",
                    "",
                    "",
                    "Package scripts are executable entrypoints used by developers or CI.",
                )
            )
        bins = payload.get("bin") or {}
        if isinstance(bins, str):
            bins = {pkg_name: bins}
        for name, target in sorted(bins.items()):
            fid = uniq_feature_id(stable_id(l1, pkg_name, "bin", name), seen)
            out.append(
                Feature(
                    fid,
                    l1,
                    l2,
                    f"package bin: {name}",
                    "package-bin",
                    path,
                    str(target),
                    "",
                    "",
                    "",
                    "Package bins are user-facing executable entrypoints.",
                )
            )
    return out


def shell_script_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    prefixes = (
        "scripts/",
        "bin/",
        "lib/installer/",
        "hooks/",
        "components.d/",
        "desktop/runtime/",
        "desktop/",
        "harness/",
        "mempalace/",
        "install.sh",
        "get-solar.sh",
    )
    out: list[Feature] = []
    for path in sorted(f for f in files if f.endswith(".sh") or f in {"install.sh", "get-solar.sh"}):
        if not path.startswith(prefixes):
            continue
        name = Path(path).name
        if path.startswith("harness/tests/") or path.startswith("tests/") or name.startswith("test-") or name.startswith("test_"):
            continue
        if "/vendor/" in path or "/run/" in path or "/logs/" in path:
            continue
        l1, l2 = classify_path(path)
        l3 = Path(path).stem
        fid = uniq_feature_id(stable_id(l1, l2, l3), seen)
        out.append(
            Feature(
                fid,
                l1,
                l2,
                l3,
                "shell-script",
                path,
                path,
                "",
                "",
                "",
                "Shell scripts can mutate install/runtime/release state and need syntax, safety, or smoke validation.",
            )
        )
    return out


def parse_python_cli_commands(text: str) -> list[str]:
    commands = set()
    for m in re.finditer(r"\.add_parser\(\s*['\"]([^'\"]+)['\"]", text):
        commands.add(m.group(1))
    return sorted(commands)


def python_cli_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    out: list[Feature] = []
    for path in sorted(f for f in files if f.endswith(".py")):
        if "/vendor/" in path or path.startswith("harness/tests/") or path.startswith("tests/"):
            continue
        name = Path(path).name
        if name.startswith("test_") or name.startswith("test-") or ".test." in name:
            continue
        text = read_text(path)
        has_main = "if __name__" in text or "def main(" in text or "argparse" in text
        if not has_main:
            continue
        commands = parse_python_cli_commands(text)
        l1, l2 = classify_path(path)
        base = Path(path).stem
        if commands:
            for cmd in commands:
                fid = uniq_feature_id(stable_id(l1, l2, base, cmd), seen)
                out.append(
                    Feature(
                        fid,
                        l1,
                        l2,
                        f"{base}: {cmd}",
                        "python-cli",
                        path,
                        f"python {path} {cmd}",
                        "",
                        "",
                        "",
                        "Python CLI subcommands are executable feature entrypoints.",
                    )
                )
        else:
            fid = uniq_feature_id(stable_id(l1, l2, base), seen)
            out.append(
                Feature(
                    fid,
                    l1,
                    l2,
                    base,
                    "python-cli",
                    path,
                    f"python {path}",
                    "",
                    "",
                    "",
                    "Python main modules are executable feature entrypoints.",
                )
            )
    return out


def explicit_lifecycle_features(seen: Counter[str]) -> list[Feature]:
    out: list[Feature] = []
    solar_cmds = ["version", "status", "doctor", "update", "repair", "backup", "restore", "ui", "harness", "uninstall", "components"]
    for cmd in solar_cmds:
        fid = uniq_feature_id(stable_id("CLI", "solar lifecycle", cmd), seen)
        out.append(
            Feature(
                fid,
                "CLI",
                "solar lifecycle",
                cmd,
                "shell-cli",
                "bin/solar",
                f"solar {cmd}",
                "",
                "",
                "",
                "Lifecycle commands are user-facing CLI behavior.",
            )
        )
    pipx_cmds = ["install", "source"] + solar_cmds
    for cmd in pipx_cmds:
        fid = uniq_feature_id(stable_id("Packaging", "openjiuwen solar wrapper", cmd), seen)
        out.append(
            Feature(
                fid,
                "Packaging",
                "openjiuwen-solar wrapper",
                cmd,
                "python-cli",
                "distribution/pipx/opensolar_cli/cli.py",
                f"openjiuwen-solar {cmd}",
                "",
                "",
                "",
                "pipx wrapper commands are published distribution behavior.",
            )
        )
    return out


def route_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    out: list[Feature] = []
    route_files = [f for f in files if f.endswith((".py", ".ts", ".js", ".mjs")) and ("server" in f or "routes" in f or "dashboard" in f)]
    patterns: set[tuple[str, str]] = set()
    for path in route_files:
        if "/vendor/" in path or path.startswith("tests/") or path.startswith("harness/tests/"):
            continue
        try:
            text = read_text(path)
        except Exception:
            continue
        for m in re.finditer(r"path\s*==\s*['\"]([^'\"]+)['\"]", text):
            patterns.add((path, m.group(1)))
        for m in re.finditer(r"path\.startswith\(\s*['\"]([^'\"]+)['\"]", text):
            patterns.add((path, m.group(1) + "*"))
        for m in re.finditer(r"re\.match\(\s*r?['\"]\^([^'\"]+)['\"]", text):
            patterns.add((path, "^" + m.group(1)))
        for m in re.finditer(r"(?:app|router|server)\.(?:get|post|put|delete|route)\(\s*['\"]([^'\"]+)['\"]", text):
            patterns.add((path, m.group(1)))
        for m in re.finditer(r"if\s*\(\s*(?:url|pathname|req\.url)\s*={2,3}\s*['\"]([^'\"]+)['\"]", text):
            patterns.add((path, m.group(1)))
    for path, route in sorted(patterns):
        l1, l2 = classify_path(path)
        fid = uniq_feature_id(stable_id(l1, l2, "route", route), seen)
        out.append(
            Feature(
                fid,
                l1,
                l2,
                f"route {route}",
                "route",
                path,
                route,
                "",
                "",
                "",
                "HTTP routes are externally observable contracts.",
            )
        )
    return out


def skill_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    out: list[Feature] = []
    for path in sorted(f for f in files if f.endswith("SKILL.md")):
        text = read_text(path)
        desc = ""
        for line in text.splitlines()[:30]:
            if line.lower().startswith("description:"):
                desc = line.split(":", 1)[1].strip()
                break
        if not desc:
            for line in text.splitlines()[:20]:
                if line.strip() and not line.startswith("#") and not line.startswith("---"):
                    desc = line.strip()[:160]
                    break
        l1, l2 = classify_path(path)
        parts = path.split("/")
        skill_name = parts[-2] if len(parts) >= 2 else Path(path).parent.name
        fid = uniq_feature_id(stable_id(l1, l2, skill_name), seen)
        source_type = "skill"
        notes = desc
        if "/vendor/" in path:
            notes = f"vendor skill; owned coverage usually not required. {desc}".strip()
        out.append(
            Feature(
                fid,
                l1,
                l2,
                skill_name,
                source_type,
                path,
                skill_name,
                "",
                "",
                "",
                "Skills are shipped/user-invoked instruction and script surfaces.",
                notes,
            )
        )
    return out


def workflow_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    out: list[Feature] = []
    for path in sorted(f for f in files if f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))):
        text = read_text(path)
        jobs = []
        in_jobs = False
        for line in text.splitlines():
            if line.startswith("jobs:"):
                in_jobs = True
                continue
            if in_jobs:
                m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
                if m:
                    jobs.append(m.group(1))
        if not jobs:
            jobs = [Path(path).stem]
        for job in jobs:
            fid = uniq_feature_id(stable_id("CI", Path(path).stem, job), seen)
            out.append(
                Feature(
                    fid,
                    "CI",
                    Path(path).stem,
                    job,
                    "workflow",
                    path,
                    f"GitHub Actions job {job}",
                    "",
                    "",
                    "",
                    "CI jobs are release gates and must be mirrored or observed.",
                )
            )
    return out


def static_surface_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    rows = [
        ("Components", "components.d", "component manifests", "manifest", "components.d", "Component manifests parse and render expected install payloads."),
        ("Runtime", "schema", "runtime schemas", "manifest", "runtime/schema", "Schemas validate known-good and known-bad fixtures."),
        ("Runtime", "policy", "writer policies", "manifest", "runtime/policy", "Policies parse and enforce write-scope expectations."),
        ("Docs", "canonical docs", "README/INSTALL/user guide", "documentation", "README.md;INSTALL.md;USER-GUIDE.md;docs", "Links, commands, and shipped docs references validate."),
        ("Templates", "rendering", "templates", "template", "templates;harness/templates", "Representative templates render with fixture data and no missing variables."),
        ("Benchmarks", "fixtures", "benchmark definitions", "manifest", "benchmarks;harness/evals", "Benchmark definitions parse and report schemas validate."),
    ]
    out = []
    for l1, l2, l3, stype, path, why in rows:
        if any(f == path or f.startswith(path.rstrip("/") + "/") for f in files):
            fid = uniq_feature_id(stable_id(l1, l2, l3), seen)
            out.append(
                Feature(
                    fid,
                    l1,
                    l2,
                    l3,
                    stype,
                    path,
                    path,
                    "",
                    "",
                    "",
                    why,
                )
            )
    return out


def domain_module_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    rows = [
        (
            "Ingestion",
            "Documents",
            "PDF/PPTX/DOCX and data-plane extraction",
            "harness/lib/mineru_extract.py;harness/lib/source_manifest.py;harness/tests/data_plane",
            "Document fixtures extract into valid text/source manifests; corrupt or scanned-only files produce explicit unsupported/error states.",
        ),
        (
            "Ingestion",
            "URLs",
            "HTML and web/source acquisition",
            "harness/lib/research/sources;tools/fetch_wikipedia.py;harness/lib/ragflow_adapter.py",
            "Mock/local URL fixtures parse into expected source records; live network paths are opt-in and report BLOCKED without credentials.",
        ),
        (
            "Ingestion",
            "Social Media",
            "social/browser source collection",
            "harness/lib/social_browser_backend_x;harness/lib/github_intelligence/adapters",
            "Mocked social/browser adapters preserve metadata, deduplicate records, and avoid credential/profile mutation.",
        ),
        (
            "Ingestion",
            "Research Papers",
            "arXiv/HF paper metadata and paper preparation",
            "harness/lib/hf_paper_insight;tools/fetch_arxiv.py;tools/prepare_paper_source.py;tools/daily_arxiv.py",
            "Paper fixtures preserve title, sections, citations, metadata, and explicit network-disabled behavior.",
        ),
        (
            "Ingestion",
            "Videos",
            "YouTube transcript and audio acquisition",
            "harness/lib/youtube;harness/lib/ai_influence_youtube_report/browser_agent.py",
            "Video fixtures return timestamped transcript/status payloads and explicit deleted/geoblocked/no-subtitle states.",
        ),
        (
            "AutoSci",
            "Workflow Bridge",
            "AutoSci command and capability bridge",
            "harness/plugins/autosci;docs/integrations/autosci/autosci-workflow-map.md",
            "AutoSci routes map to Solar-native capabilities, write expected artifacts, and pass premerge and parity gates.",
        ),
        (
            "AutoSci",
            "Scientific evaluators",
            "scientific lifecycle artifact gates",
            "harness/evaluators/scientific;harness/tests/evaluators/scientific",
            "Pass/fail fixtures validate schemas and gates for idea, paper, experiment, claims, report, publication, and lifecycle artifacts.",
        ),
        (
            "Harness",
            "Solar-Harness Port",
            "ported framework engine and orchestration shell",
            "harness/solar-harness.sh;harness/lib;harness/tests",
            "Harness commands, graph dispatch, runtime status, pane safety, and status surfaces pass deterministic smoke tests.",
        ),
    ]
    out = []
    for l1, l2, l3, source_paths, criteria in rows:
        if any(
            any(f == source or f.startswith(source.rstrip("/") + "/") for f in files)
            for source in source_paths.split(";")
        ):
            fid = uniq_feature_id(stable_id(l1, l2, l3), seen)
            out.append(
                Feature(
                    fid,
                    l1,
                    l2,
                    l3,
                    "domain-module",
                    source_paths,
                    source_paths,
                    "",
                    "",
                    criteria,
                    "Domain module rows preserve product-level feature coverage even when the implementation is spread across libraries, scripts, and tests.",
                )
            )
    return out


def module_summary_features(files: list[str], seen: Counter[str]) -> list[Feature]:
    top_counts = Counter((f.split("/", 1)[0] if "/" in f else ".root") for f in files)
    owned_modules = [
        "core",
        "harness",
        "desktop",
        "distribution",
        "scripts",
        "skills",
        "hooks",
        "runtime",
        "components.d",
        "lib",
        "app",
        "web",
        "mempalace",
        "codex-bridge",
    ]
    out = []
    for mod in owned_modules:
        if top_counts.get(mod, 0) == 0:
            continue
        l1, l2 = classify_path(mod + "/")
        fid = uniq_feature_id(stable_id("module", l1, l2), seen)
        out.append(
            Feature(
                fid,
                l1,
                l2,
                f"module surface ({top_counts[mod]} tracked files)",
                "module",
                mod,
                mod,
                "",
                "",
                "",
                "Module-level row ensures the source tree has an explicit QA owner and coverage summary.",
            )
        )
    return out


def apply_test_mapping(features: list[Feature], tests: list[str], workflow_refs: dict[str, list[str]]) -> None:
    for feature in features:
        matched = map_tests(feature, tests)
        for source in feature.source_paths.split(";"):
            for wf in workflow_refs.get(source, []):
                if wf not in matched:
                    matched.append(wf)
        feature.existing_tests = ";".join(matched)
        feature.coverage_status = coverage_status_for(feature, matched)
        if not feature.pass_criteria:
            feature.pass_criteria = pass_criteria_for(feature.l1, feature.l2, feature.l3, feature.source_type)


def specific_inputs_outputs_for_feature(feature: Feature) -> str:
    group_hint = FEATURE_INPUT_OVERRIDES.get((feature.l1, feature.l2), "")
    action = feature.l3.strip()
    source = feature.source_type

    if source == "python-cli":
        io = "Inputs: CLI args, environment, local files, or stdin; Outputs: stdout/stderr, JSON/text, and generated artifacts when supported"
    elif source == "route":
        io = "Inputs: HTTP method/path/query/body; Outputs: HTTP status plus JSON, HTML, SSE, or static asset response"
    elif source == "workflow":
        io = "Inputs: GitHub Actions event, matrix, secrets, and repo checkout; Outputs: CI status, logs, and workflow artifacts"
    elif source in {"shell-cli", "shell-script"}:
        io = "Inputs: shell args, environment variables, filesystem fixtures; Outputs: exit code, logs, files, and runtime artifacts"
    elif source in {"package-bin", "package-script"}:
        io = "Inputs: package manager command args and environment; Outputs: build/test/dev logs, bundles, or process status"
    elif source == "skill":
        io = "Inputs: natural-language or slash-command skill invocation; Outputs: skill instructions, wrapper calls, and artifacts"
    elif source == "manifest":
        io = "Inputs: manifest/schema/policy files; Outputs: validation result, parsed config, and actionable errors"
    elif source in {"domain-module", "module"}:
        io = "Inputs: module source files and fixture data; Outputs: library behavior, runtime artifacts, and validation results"
    else:
        io = "Inputs: repo-tracked source/config/test fixtures; Outputs: validation results and generated artifacts"

    parts = []
    if action:
        parts.append(f"Feature/action: {action}")
    if group_hint:
        parts.append(f"Formats: {group_hint}")
    parts.append(io)
    return " | ".join(parts)


def feature_inventory_row(feature: Feature) -> dict[str, str]:
    return {
        "feature_id": feature.feature_id,
        "l1": feature.l1,
        "l2": feature.l2,
        "specific_inputs_outputs": specific_inputs_outputs_for_feature(feature),
        "source_type": feature.source_type,
        "source_paths": feature.source_paths,
        "entrypoints": feature.entrypoints,
        "existing_tests": feature.existing_tests,
        "coverage_status": feature.coverage_status,
        "pass_criteria": feature.pass_criteria,
        "why_testable": feature.why_testable,
        "notes": feature.notes,
    }


def write_csv(features: list[Feature], path: Path) -> None:
    fieldnames = [
        "feature_id",
        "l1",
        "l2",
        "specific_inputs_outputs",
        "source_type",
        "source_paths",
        "entrypoints",
        "existing_tests",
        "coverage_status",
        "pass_criteria",
        "why_testable",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in features:
            writer.writerow(feature_inventory_row(row))


def write_markdown(features: list[Feature], path: Path, *, max_rows: int | None = None) -> None:
    rows = features if max_rows is None else features[:max_rows]
    with path.open("w", encoding="utf-8") as f:
        f.write("# Repo-Derived QA Feature Inventory\n\n")
        f.write("Generated from tracked files. This file is evidence for planning; it does not execute tests.\n\n")
        f.write("| Feature ID | L1 | L2 | Specific Inputs / Outputs | Source | Coverage | Pass Criteria |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in rows:
            source = r.source_paths.replace("|", "\\|")
            criteria = r.pass_criteria.replace("|", "\\|")
            io = specific_inputs_outputs_for_feature(r).replace("|", "\\|")
            f.write(
                f"| `{r.feature_id}` | {r.l1} | {r.l2} | {io} | {source} | {r.coverage_status} | {criteria} |\n"
            )


def write_summary(features: list[Feature], files: list[str], tests: list[str], path: Path) -> None:
    by_l1 = Counter(f.l1 for f in features)
    by_type = Counter(f.source_type for f in features)
    by_coverage = Counter(f.coverage_status for f in features)
    missing = [f for f in features if f.coverage_status == "missing-or-indirect"]
    static = [f for f in features if f.coverage_status == "static-validation-required"]
    with path.open("w", encoding="utf-8") as f:
        f.write("# QA Inventory Summary\n\n")
        f.write("## Scope\n\n")
        f.write("- Source: tracked files from `git ls-files`.\n")
        f.write("- Included: package scripts/bins, shell scripts, Python CLIs, HTTP routes, workflows, SKILL.md files, static surfaces, module summary rows, and existing tests.\n")
        f.write("- Excluded from required execution by default: vendor content, local caches, runtime logs, venvs, and generated artifacts not tracked as source.\n\n")
        f.write("## Counts\n\n")
        f.write(f"- Tracked files scanned: {len(files)}\n")
        f.write(f"- Test files detected: {len(tests)}\n")
        f.write(f"- Feature rows generated: {len(features)}\n\n")
        f.write("## Feature Rows by L1\n\n")
        for key, value in sorted(by_l1.items()):
            f.write(f"- {key}: {value}\n")
        f.write("\n## Feature Rows by Source Type\n\n")
        for key, value in sorted(by_type.items()):
            f.write(f"- {key}: {value}\n")
        f.write("\n## Coverage Status\n\n")
        for key, value in sorted(by_coverage.items()):
            f.write(f"- {key}: {value}\n")
        f.write("\n## Rows Needing Explicit Test Mapping\n\n")
        for r in missing[:80]:
            f.write(f"- `{r.feature_id}`: {r.source_paths} ({r.l3})\n")
        if len(missing) > 80:
            f.write(f"- ... {len(missing) - 80} more rows in CSV\n")
        f.write("\n## Static Validation Rows\n\n")
        for r in static[:80]:
            f.write(f"- `{r.feature_id}`: {r.source_paths} ({r.l3})\n")
        if len(static) > 80:
            f.write(f"- ... {len(static) - 80} more rows in CSV\n")
        f.write("\n## Interpretation\n\n")
        f.write("A `covered` row means a repo test file appears to target the feature by path/name heuristics. It still requires execution before claiming PASS.\n")
        f.write("A `missing-or-indirect` row is testable but lacks an obvious direct test mapping; it may be covered through a broader smoke gate, but that must be confirmed before final sign-off.\n")


def master_pass_criteria(l1: str, l2: str, source_types: set[str]) -> str:
    if l1 == "AutoSci":
        return "AutoSci bridge/evaluator workflows pass deterministic fixture gates, artifact schemas validate, and unsupported/live-tool paths are explicitly BLOCKED or opt-in."
    if l1 == "CI":
        return "All workflow jobs in this group either pass in CI or have equivalent local evidence captured in the test report."
    if l1 == "Harness":
        return "Harness commands, graph dispatch, runtime status, pane safety, and generated artifacts pass deterministic smoke tests without mutating real user state."
    if l1 == "Installer":
        return "Installer library behavior is validated through contract, dry-run, sandbox install/uninstall, syntax, and privacy checks without touching the real HOME."
    if l1 == "Desktop":
        return "Desktop scripts/builds pass their intended gate, renderer artifacts exist, and visual/contract screenshots are captured where applicable."
    if l1 == "Status Server":
        return "All discovered routes return expected status/content/schema for normal and error paths, including auth/token behavior where required."
    if l1 == "Research":
        return "Research CLI/workflow commands pass fixture-based tests, JSON outputs validate, and source/evidence/report artifacts meet declared gates."
    if l1 == "Ingestion":
        return "Fixture inputs parse into structurally valid outputs and unsupported/corrupt inputs fail explicitly without silent bad artifacts."
    if l1 == "Skills":
        return "Skill metadata parses, referenced scripts/assets exist, and behavior-bearing skill scripts pass smoke tests or are integration-gated."
    if l1 == "Hooks":
        return "Hooks pass syntax/smoke checks in an isolated environment and do not mutate real user state unexpectedly."
    if l1 == "QA Gates":
        return "Repository gate scripts exit 0 or produce documented BLOCKED status when required external tools are unavailable."
    if l1 == "Packaging":
        return "Package wrapper commands build/import, delegate correctly, and fail with actionable errors for unsupported platforms or missing installs."
    if l1 == "Components":
        return "Component scripts/manifests render, install/remove safely, and generated component docs remain in sync."
    if l1 == "TVS":
        return "Terminal visual system rendering, routing, and server contracts pass existing TS/Python smoke tests."
    if "route" in source_types:
        return "Every route has contract coverage for success and failure responses."
    return "Every raw feature row in this group has PASS evidence or a documented SKIPPED/BLOCKED/N/A reason; no unresolved critical defect remains."


def write_master_table(features: list[Feature], csv_path: Path, md_path: Path) -> None:
    grouped: dict[tuple[str, str], list[Feature]] = defaultdict(list)
    for feature in features:
        grouped[(feature.l1, feature.l2)].append(feature)

    rows = []
    for (l1, l2), items in sorted(grouped.items()):
        source_types = sorted({i.source_type for i in items})
        coverage = Counter(i.coverage_status for i in items)
        tests = sorted({t for i in items for t in i.existing_tests.split(";") if t})
        group_id = stable_id(l1, l2, "acceptance")
        sample_features = ";".join(i.feature_id for i in items[:8])
        rows.append(
            {
                "group_id": group_id,
                "l1": l1,
                "l2": l2,
                "raw_feature_rows": len(items),
                "source_types": ";".join(source_types),
                "covered_rows": coverage.get("covered", 0),
                "missing_or_indirect_rows": coverage.get("missing-or-indirect", 0),
                "static_validation_rows": coverage.get("static-validation-required", 0),
                "partial_or_unmapped_rows": coverage.get("partial-or-unmapped", 0),
                "existing_test_evidence_count": len(tests),
                "sample_existing_test_evidence": ";".join(tests[:8]),
                "sample_raw_feature_ids": sample_features,
                "group_pass_criteria": master_pass_criteria(l1, l2, set(source_types)),
            }
        )

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# Master Pass/Fail Table\n\n")
        f.write("Each row is an execution-level acceptance group. The raw source-of-truth feature rows are in `qa_feature_inventory.csv`.\n\n")
        f.write("| Group ID | L1 | L2 | Raw Rows | Covered | Missing/Indirect | Static | Partial | Pass Criteria |\n")
        f.write("|---|---|---|---:|---:|---:|---:|---:|---|\n")
        for r in rows:
            criteria = r["group_pass_criteria"].replace("|", "\\|")
            f.write(
                f"| `{r['group_id']}` | {r['l1']} | {r['l2']} | {r['raw_feature_rows']} | "
                f"{r['covered_rows']} | {r['missing_or_indirect_rows']} | {r['static_validation_rows']} | "
                f"{r['partial_or_unmapped_rows']} | {criteria} |\n"
            )


FEATURE_INPUT_OVERRIDES: dict[tuple[str, str], str] = {
    ("AutoSci", "AutoSci plugin bridge"): "AutoSci slash/CLI commands; JSON evidence; Markdown reports; provider-gated live paths",
    ("AutoSci", "Scientific evaluators"): "Scientific artifact JSON; claims; experiment plans/results; papers; reports; lifecycle evidence",
    ("AutoSci", "Workflow Bridge"): "research.autosci.v1 workflow contracts; AutoSci capability routes; evidence envelopes",
    ("Benchmarks", "Benchmark runtime"): "Benchmark definitions; Terminal-Bench adapter requests; JSON benchmark reports",
    ("Browser", "Browser runtime"): "Browser jobs; URLs; profile/session metadata; Playwright/Webwright-style tasks",
    ("Browser", "Social browser backend"): "Social/browser source records; profile metadata; collected post/thread payloads",
    ("CLI", "solar lifecycle"): "Natural-language intake; stdin/file requests; solar/solar-harness commands; JSON status output",
    ("Components", "Component manifests"): "component.sh files; component install/remove metadata; generated component docs",
    ("Components", "components.d"): "components.d manifests and shell component entrypoints",
    ("Core", "TypeScript runtime"): "Bun/TypeScript modules; daemon/dashboard runtime imports; TVS module imports",
    ("Dashboard", "React status dashboard"): "React dashboard assets; status JSON payloads; browser UI scenarios",
    ("Desktop", "Electron shell"): "Electron package scripts; renderer assets; Playwright scenarios; macOS/Windows/Linux package targets",
    ("Harness", "Graph orchestration"): "task_graph.json; sprint status JSON; graph dispatch/eval commands; pane lease/status records",
    ("Harness", "Python runtime library"): "Python CLI commands; JSON ledgers; status artifacts; runtime envelopes; fixture files",
    ("Harness", "Solar-Harness Port"): "solar-harness shell commands; tmux pane/runtime state; sprint artifacts",
    ("Harness", "Solar-Harness shell/runtime"): "shell commands; tmux pane state; intake records; task graphs; status JSON; runtime logs",
    ("Hooks", "Runtime hooks"): "shell hooks; environment variables; event JSONL; dispatch files; runtime artifacts",
    ("Ingestion", "Daily arXiv discovery"): "arXiv IDs; arXiv API/search results; paper metadata JSON/Markdown",
    ("Ingestion", "DeepXiv fetch"): "DeepXiv URLs/API payloads; paper metadata; fetched source artifacts",
    ("Ingestion", "Document extraction"): "PDF; PPTX; DOCX; extracted text/tables/layout metadata; source manifests",
    ("Ingestion", "Documents"): "PDF; PPTX; DOCX; local document files",
    ("Ingestion", "LaTeX/math rendering"): "LaTeX expressions; math blocks; rasterized/rendered formula artifacts",
    ("Ingestion", "Research Papers"): "arXiv/Hugging Face paper metadata; PDFs; citations; section text",
    ("Ingestion", "Research discovery"): "research queries; source search results; paper metadata; discovery JSON",
    ("Ingestion", "Research paper preparation"): "paper URLs/IDs; local paper source files; metadata manifests",
    ("Ingestion", "Semantic Scholar fetch"): "Semantic Scholar paper IDs/API payloads; citation metadata",
    ("Ingestion", "Social Media"): "thread/post payloads; browser-collected social records; metadata",
    ("Ingestion", "Source data plane"): "source-manifest JSONL; Knowledge _sources files; QMD/source ledger data",
    ("Ingestion", "URLs"): "HTTP/HTTPS URLs; HTML; web source records",
    ("Ingestion", "Videos"): "YouTube URLs/channels; transcripts; timestamped captions; video metadata",
    ("Ingestion", "Wikipedia/URL fetch"): "Wikipedia URLs/pages; HTML/source text; fetched metadata",
    ("Ingestion", "YouTube/video intelligence"): "YouTube URLs; transcript tracks; channel/video metadata; report artifacts",
    ("Ingestion", "arXiv fetch"): "arXiv IDs; arXiv URLs; paper metadata; PDFs",
    ("Installer", "Installer library"): "install profiles; component lists; sandbox HOME; requirements files; receipts",
    ("Packaging", "openjiuwen-solar wrapper"): "package wrapper commands; install receipts; platform/runtime detection payloads",
    ("Packaging", "pipx distribution"): "pipx package metadata; console scripts; Python package import paths",
    ("QA Gates", "Repository scripts"): "check/smoke shell scripts; TypeScript smoke scripts; JSON/log gate outputs",
    ("Reports", "GitHub intelligence"): "GitHub repository/issue/PR data; digest JSON; Markdown reports",
    ("Research", "DeepResearch core"): "research queries; claims; citations; evidence ledgers; survey/report JSON and Markdown",
    ("Runtime", "Schemas and policies"): "runtime schema/policy manifests; valid/invalid JSON fixtures",
    ("Runtime", "policy"): "writer policy manifests; write-scope fixtures",
    ("Runtime", "schema"): "runtime schema JSON; schema validation fixtures",
    ("Skills", "Agent skill wrappers"): "SKILL.md files; slash command wrappers; skill scripts/assets",
    ("Skills", "Shipped skills"): "SKILL.md files; skill metadata; referenced scripts/assets; wrapper commands",
    ("Status Server", "Python HTTP status server"): "HTTP routes; JSON responses; SSE/events; static status assets",
    ("TVS", "Terminal visual system"): "terminal render payloads; grid/theme/display data; TVS TypeScript imports",
}


def specific_inputs_for_group(l1: str, l2: str, items: list[Feature]) -> str:
    override = FEATURE_INPUT_OVERRIDES.get((l1, l2))
    if override:
        return override

    source_types = sorted({i.source_type for i in items})
    joined = " ".join(
        " ".join(
            [
            " ".join(i.source_paths.split(";")),
            " ".join(i.entrypoints.split(";")),
            i.l3,
            ]
        )
        for i in items[:30]
    ).lower()
    formats: list[str] = []
    hints = [
        ("json", "JSON"),
        ("jsonl", "JSONL"),
        ("yaml", "YAML"),
        ("yml", "YAML"),
        ("markdown", "Markdown"),
        (".md", "Markdown"),
        ("pdf", "PDF"),
        ("pptx", "PPTX"),
        ("docx", "DOCX"),
        ("url", "URLs"),
        ("http", "HTTP/HTTPS"),
        ("route", "HTTP routes"),
        ("workflow", "GitHub Actions workflows"),
        ("skill.md", "SKILL.md"),
        ("shell", "shell commands"),
        (".sh", "shell scripts"),
        ("python", "Python CLI"),
        (".py", "Python modules"),
        ("typescript", "TypeScript"),
        (".ts", "TypeScript"),
        ("package.json", "package.json scripts"),
    ]
    for needle, label in hints:
        if needle in joined and label not in formats:
            formats.append(label)
    if not formats:
        source_type_labels = {
            "domain-module": "domain source modules",
            "manifest": "manifest files",
            "module": "module source files",
            "package-bin": "package bin entries",
            "package-script": "package.json scripts",
            "python-cli": "Python CLI commands",
            "route": "HTTP routes",
            "shell-cli": "shell CLI commands",
            "shell-script": "shell scripts",
            "skill": "SKILL.md files",
            "workflow": "GitHub Actions workflows",
        }
        formats.extend(source_type_labels.get(source_type, source_type) for source_type in source_types)
    return "; ".join(formats)


def write_feature_list(features: list[Feature], path: Path) -> None:
    rows = []
    for feature in features:
        rows.append(
            {
                "Level 1 Feature": feature.l1,
                "Level 2 Feature": feature.l2,
                "Specific Inputs / Outputs Supported": specific_inputs_outputs_for_feature(feature),
            }
        )

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Level 1 Feature",
                "Level 2 Feature",
                "Specific Inputs / Outputs Supported",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    files = git_ls_files()
    tests = tracked_tests(files)
    workflow_refs = workflow_evidence(files)
    seen: Counter[str] = Counter()
    features: list[Feature] = []
    features.extend(module_summary_features(files, seen))
    features.extend(domain_module_features(files, seen))
    features.extend(static_surface_features(files, seen))
    features.extend(package_features(files, seen))
    features.extend(explicit_lifecycle_features(seen))
    features.extend(shell_script_features(files, seen))
    features.extend(python_cli_features(files, seen))
    features.extend(route_features(files, seen))
    features.extend(skill_features(files, seen))
    features.extend(workflow_features(files, seen))
    features.sort(key=lambda f: (f.l1, f.l2, f.l3, f.source_paths, f.feature_id))
    apply_test_mapping(features, tests, workflow_refs)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(features, OUT_DIR / "qa_feature_inventory.csv")
    write_markdown(features, OUT_DIR / "qa_feature_inventory.md")
    write_feature_list(features, OUT_DIR / "qa_feature_list.csv")
    write_summary(features, files, tests, OUT_DIR / "qa_inventory_summary.md")
    write_master_table(features, OUT_DIR / "qa_master_pass_fail_table.csv", OUT_DIR / "qa_master_pass_fail_table.md")

    manifest = {
        "tracked_files": len(files),
        "test_files": len(tests),
        "feature_rows": len(features),
        "by_l1": dict(sorted(Counter(f.l1 for f in features).items())),
        "by_source_type": dict(sorted(Counter(f.source_type for f in features).items())),
        "by_coverage_status": dict(sorted(Counter(f.coverage_status for f in features).items())),
        "outputs": [
            "docs/testing/qa_feature_inventory.csv",
            "docs/testing/qa_feature_inventory.md",
            "docs/testing/qa_feature_list.csv",
            "docs/testing/qa_inventory_summary.md",
            "docs/testing/qa_master_pass_fail_table.csv",
            "docs/testing/qa_master_pass_fail_table.md",
        ],
    }
    (OUT_DIR / "qa_inventory_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
