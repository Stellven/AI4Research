"""Build the reviewed Phase 22 atomic-feature and executable-test matrix.

The source is the canonical workbook's L2 descriptions/WHAT contracts/current
code evidence, exported to ``l2_atomic_source.json``.  Historical atomic rows
are treated as provenance, not as an approved hierarchy.  Each reviewed atomic
feature is one independently observable behavior, rejection branch, evidence
obligation, or explicitly named technology/platform variant.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OVERRIDE_PATH = HERE / "atomic_feature_matrix_overrides.json"
AUDIT_PATH = HERE / "environment_provider_gate_audit.json"
PREFIX_RE = re.compile(
    r"^(?:"
    r"separate atomic contracts for|define separate contracts for|"
    r"separate contracts for|separate tests by|separate|test|"
    r"create separate contracts for|create tests for|before implementation:\s*decide"
    r")\s+",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"^\d+\.\s*")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "case", "cases",
    "contract", "contracts", "current", "each", "feature", "for", "from",
    "in", "into", "is", "it", "l2", "of", "on", "or", "path", "result",
    "test", "tests", "the", "to", "with", "without", "behavior", "valid",
    "invalid", "success", "failure", "present", "absent",
}
GENERIC_PATH_HINTS = {
    "app", "cli", "config", "core", "index", "main", "registry", "runtime",
    "schema", "schemas", "server", "service", "types", "utils",
}
GENERIC_SYMBOL_HINTS = {
    "build", "capture", "check", "create", "evaluate", "execute", "list",
    "load", "query", "read", "resolve", "review", "run", "save", "status",
    "validate", "write",
}
NEGATIVE_TERMS = {
    "absent", "blocked", "conflict", "corrupt", "denied", "deny", "duplicate",
    "empty", "error", "expired", "fail", "failure", "forbidden", "incomplete",
    "invalid", "malformed", "mismatch", "missing", "no", "nonzero", "rejection",
    "rejected", "stale", "timeout", "unauthorized", "unavailable", "unsupported",
}
EVIDENCE_TERMS = {
    "artifact", "audit", "citation", "evidence", "hash", "history", "log",
    "manifest", "metadata", "provenance", "receipt", "record", "report", "trace",
}
ENVIRONMENT_OR_PROVIDER_TERMS = {
    "api", "app", "auth", "browser", "budget", "cluster", "cost", "cuda",
    "desktop", "discord", "external", "github", "gpu", "gui", "install",
    "linux", "live", "macos", "network", "provider", "quota", "remote",
    "resource", "session", "slack", "ssh", "tmux", "token", "tui",
    "uninstall", "web", "webhook", "wechat", "windows", "wsl",
}

# The L2 name itself names these independently testable technologies/surfaces;
# generic lifecycle granularity alone would otherwise hide absent implementations.
ADDITIONAL_ATOMS: dict[str, list[str]] = {
    "Capability Capsule Definition & Assembly": [
        "Missing referenced resource rejection",
    ],
    "User-Supplied Material Import": [
        "Office document import",
        "Dataset import",
        "Repository reference import",
        "URL reference import",
    ],
    "Text-Based Artifacts (GEPA / MIPROv2 / TextGrad)": [
        "GEPA optimization",
        "MIPROv2 optimization",
        "TextGrad optimization",
    ],
    "Runtime and Resource Routing (Bayesian Optimization / Bandits / Cost-Aware RL)": [
        "Bayesian optimization routing",
        "Bandit routing",
        "Cost-aware reinforcement-learning routing",
    ],
    "Capability Capsules and Physical Operators (Trajectory Mining / Code Evolution / CEGIS)": [
        "Trajectory mining",
        "Code evolution",
        "CEGIS synthesis",
    ],
    "DAG and Agent Organization (AFlow / MCTS / ADAS)": [
        "AFlow optimization",
        "MCTS optimization",
        "ADAS optimization",
    ],
    "Evaluator, Reward, Contract, and Governance (Judge Calibration / Reward Modeling / CEGIS)": [
        "Judge calibration",
        "Reward-model training",
        "CEGIS governance synthesis",
    ],
    "Memory, Retrieval, and Evidence (Memory Learning / Self-RAG / Reranker Training)": [
        "Memory learning",
        "Self-RAG",
        "Reranker training",
    ],
    "Model Policies and Weights (SFT / LoRA / DPO / GRPO / Agent RL)": [
        "SFT training",
        "LoRA training",
        "DPO training",
        "GRPO training",
        "Agent reinforcement learning",
    ],
    "Data, Benchmarks, Curriculum, and Observability (Active Learning / Hard-Case Mining / Credit Assignment)": [
        "Active learning",
        "Hard-case mining",
        "Credit assignment",
    ],
}

# Human-reviewed exact bindings for terse atomic labels that cannot be mapped
# safely by vocabulary alone.  Every selector below was inspected against the
# named implementation behavior; these are not fuzzy-search promotions.
CURATED_BINDINGS: dict[tuple[str, str], str] = {
    ("Capability Capsule Definition & Assembly", "Referenced-resource resolution"):
        "tests/harness/test_capability_capsules.py::test_resolution_gate_attaches_guard_and_resource_capsules",
    ("Capability Capsule Definition & Assembly", "Missing referenced resource rejection"):
        "tests/harness/test_capability_capsules.py::test_resolution_gate_blocks_missing_resource",
    ("TaskGraph Persistence & Lifecycle Management", "Node result"):
        "tests/harness/graph/test_task_graph_io.py::test_set_node_result_in_state",
    ("TaskGraph Persistence & Lifecycle Management", "Gate result"):
        "tests/harness/graph/test_task_graph_io.py::test_set_gate_result_in_state",
    ("TaskGraph Persistence & Lifecycle Management", "Missing"):
        "tests/harness/graph/test_task_graph_io.py::test_spec_valid_missing",
    ("TaskGraph Persistence & Lifecycle Management", "Mirror"):
        "tests/harness/graph/test_task_graph_io.py::test_compile_mirror_merges_spec_and_state",
    ("TaskGraph Persistence & Lifecycle Management", "Backfill"):
        "tests/harness/graph/test_task_graph_io.py::test_backfill_state_from_legacy",
    ("TaskGraph Persistence & Lifecycle Management", "Incomplete closure"):
        "tests/harness/graph/test_task_graph_io.py::test_closure_complete_false",
}

PRESERVE_SLASH_PHRASES = {
    # This is a compound versioned-identity uniqueness key, not a claim that
    # semantic versions must be globally unique across different capsules.
    "duplicate identity/version",
}

# Explicit exclusions from the workbook's current-code evidence.  These are
# retained as to-be atomic features but must not receive fabricated executable
# coverage from adjacent implementations.
EXPLICIT_NOT_IMPLEMENTED: dict[str, tuple[str, ...]] = {
    "Multi-Source Signal Discovery": (
        "patent", "standard", "expert", "report", "open web", "internal history", "parallel-agent",
    ),
    "User-Supplied Material Import": (
        "office document", "dataset", "repository reference",
    ),
    "Opportunity Definition": ("unmet need", "unserved user", "missing capability"),
    "Technical Opportunity Screening": ("data reachability", "mechanism", "verification path"),
    "User-Facing Deliverable Generation": (
        "proposal", "roadmap", "investment recommendation", "visualization",
    ),
    "Text-Based Artifacts (GEPA / MIPROv2 / TextGrad)": ("miprov2", "textgrad"),
    "Runtime and Resource Routing (Bayesian Optimization / Bandits / Cost-Aware RL)": (
        "bayesian optimization", "bandit routing", "reinforcement-learning routing",
    ),
    "Capability Capsules and Physical Operators (Trajectory Mining / Code Evolution / CEGIS)": (
        "trajectory mining", "cegis synthesis",
    ),
    "DAG and Agent Organization (AFlow / MCTS / ADAS)": ("aflow", "mcts", "adas"),
    "Evaluator, Reward, Contract, and Governance (Judge Calibration / Reward Modeling / CEGIS)": (
        "judge calibration", "reward-model", "cegis governance",
    ),
    "Memory, Retrieval, and Evidence (Memory Learning / Self-RAG / Reranker Training)": (
        "memory learning", "self-rag", "reranker training",
    ),
    "Data, Benchmarks, Curriculum, and Observability (Active Learning / Hard-Case Mining / Credit Assignment)": (
        "active learning", "hard-case mining", "credit assignment",
    ),
}


def clean_l2(value: object) -> str:
    text = NUMBER_RE.sub("", str(value or "").strip())
    for separator in (" — ", " â€” "):
        if separator in text:
            text = text.rsplit(separator, 1)[-1].strip()
    return text


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def tokens(value: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(value.lower()) if token not in STOPWORDS and len(token) > 1}


def split_csv(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r",\s*|\s+and\s+(?=[^,]+$)", text) if part.strip()]
    return parts or [text.strip()]


def expand_slash_variants(text: str) -> list[str]:
    """Expand slash-delimited independently observable variants.

    ``Token/cost present/absent`` becomes four atomic contracts, while normal
    hyphenated names such as ``no-dispatch`` remain untouched.
    """
    if text.strip().lower() in PRESERVE_SLASH_PHRASES:
        return [text]
    pending = [text]
    expanded: list[str] = []
    while pending:
        candidate = pending.pop(0)
        words = candidate.split()
        slash_index = next((index for index, word in enumerate(words) if "/" in word), None)
        if slash_index is None:
            expanded.append(candidate)
            continue
        alternatives = [part for part in words[slash_index].split("/") if part]
        for alternative in alternatives:
            pending.append(" ".join([*words[:slash_index], alternative, *words[slash_index + 1 :]]))
    return expanded


def atomic_phrases(granularity: object, l2: str) -> list[str]:
    raw = " ".join(str(granularity or "").split()).strip().rstrip(".")
    raw = PREFIX_RE.sub("", raw)
    semicolon_parts = [part.strip() for part in raw.split(";") if part.strip()]
    phrases: list[str] = []
    for part in semicolon_parts:
        part = PREFIX_RE.sub("", part).strip().rstrip(".")
        for csv_part in split_csv(part):
            phrases.extend(expand_slash_variants(csv_part))
    phrases.extend(ADDITIONAL_ATOMS.get(l2, []))

    result: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        phrase = re.sub(r"^(?:add independent future contracts for|whether)\s+", "", phrase, flags=re.I)
        phrase = re.sub(r"\s+cases?$", "", phrase, flags=re.I).strip(" .")
        if not phrase:
            continue
        key = slug(phrase)
        if key and key not in seen:
            seen.add(key)
            result.append(phrase[0].upper() + phrase[1:])
    return result


def scenario_type(phrase: str) -> str:
    phrase_tokens = tokens(phrase)
    if phrase_tokens & NEGATIVE_TERMS:
        return "guardrail_or_failure"
    if phrase_tokens & EVIDENCE_TERMS:
        return "evidence_or_observability"
    if phrase_tokens & {"approve", "approval", "closeout", "demotion", "lifecycle", "promote", "promotion", "release", "resume", "rollback", "transition"}:
        return "lifecycle_or_state_transition"
    return "core_behavior"


def explicit_absence(l2: str, phrase: str, l2_not_implemented: bool) -> bool:
    if l2_not_implemented:
        return True
    lowered = phrase.lower()
    return any(term in lowered for term in EXPLICIT_NOT_IMPLEMENTED.get(l2, ()))


def unresolved_generation_tag(l2: str, phrase: str) -> tuple[str, str]:
    surface_tokens = tokens(f"{l2} {phrase}")
    if surface_tokens & ENVIRONMENT_OR_PROVIDER_TERMS:
        return (
            "TAGGED_NOT_GENERATED_ENVIRONMENT_GATED",
            "No deterministic local oracle was accepted for this provider/platform/session/resource boundary; a controlled fake or opt-in environment is required.",
        )
    return (
        "TAGGED_NOT_GENERATED_MANUAL_ORACLE",
        "Exact generated-selector discovery, curated review, and conservative current-test matching found no defensible assertion-level oracle; generating a meta-test or guessed assertion was rejected.",
    )


AUDIT_DISPOSITION_MAP: dict[str, dict[str, str]] = {
    "ATOMIC_BINDING_GAP_NOT_CONFIG": {
        "test_generation_status": "ATOMIC_BINDING_GAP",
        "coverage_relationship": "UNRESOLVED_ATOMIC_BINDING",
        "current_result": "NOT_RUN_ATOMIC",
    },
    "CONFIG_RESOLVED_EXECUTABLE_EVIDENCE_AVAILABLE": {
        "test_generation_status": "CONFIG_RESOLVED_NEEDS_EXACT_BINDING",
        "coverage_relationship": "RELATED_SUITE_EVIDENCE_ONLY",
        "current_result": "NOT_RUN_ATOMIC",
    },
    "CONFIG_RESOLVED_TEST_FAILED": {
        "test_generation_status": "CONFIG_RESOLVED_RELATED_SUITE_FAILED",
        "coverage_relationship": "RELATED_SUITE_FAILED_NOT_ATOMIC",
        "current_result": "RELATED_SUITE_FAILED",
    },
    "PLATFORM_OR_HARDWARE_REQUIRED": {
        "test_generation_status": "PLATFORM_OR_HARDWARE_REQUIRED",
        "coverage_relationship": "PLATFORM_GATED",
        "current_result": "BLOCKED_PLATFORM",
    },
    "MANUAL_ORACLE_NOT_CONFIG": {
        "test_generation_status": "MANUAL_ORACLE_REQUIRED",
        "coverage_relationship": "MANUAL_ORACLE_REQUIRED",
        "current_result": "MANUAL_ORACLE_REQUIRED",
    },
    "IMPLEMENTATION_BOUNDARY_NOT_CONFIG": {
        "test_generation_status": "BLOCKED_NOT_IMPLEMENTED",
        "implementation_status": "NOT_IMPLEMENTED",
        "coverage_relationship": "CURRENT_IMPLEMENTATION_BOUNDARY",
        "current_result": "BLOCKED_NOT_IMPLEMENTED",
    },
}


ALWAYS_CLEAR_BINDING_STATUSES = {
    "TAGGED_NOT_GENERATED_ENVIRONMENT_GATED",
    "TAGGED_NOT_GENERATED_MANUAL_ORACLE",
    "ATOMIC_BINDING_GAP",
    "CONFIG_RESOLVED_NEEDS_EXACT_BINDING",
    "CONFIG_RESOLVED_RELATED_SUITE_FAILED",
    "MANUAL_ORACLE_REQUIRED",
    "PLATFORM_OR_HARDWARE_REQUIRED",
    "BLOCKED_NOT_IMPLEMENTED",
}


def inventory_case_text(case: dict) -> str:
    return " ".join(
        str(case.get(key) or "")
        for key in ("path", "selector", "case_name", "class_name", "behavior_fingerprint")
    ).lower()


def entrypoint_hints(entrypoints: object) -> tuple[set[str], set[str]]:
    text = str(entrypoints or "")
    path_hints = set()
    symbol_hints = set()
    for match in re.finditer(r"(?:^|[\s;`])([A-Za-z0-9_./-]+\.(?:py|ts|js|sh))", text):
        stem = Path(match.group(1)).stem.lower()
        if stem not in GENERIC_PATH_HINTS:
            path_hints.add(stem)
    for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_]+)\.py\b", text):
        stem = match.group(1).lower()
        if stem not in GENERIC_PATH_HINTS:
            path_hints.add(stem)
    for match in re.finditer(r"::([A-Za-z_][A-Za-z0-9_]*)", text):
        symbol = match.group(1).lower()
        if symbol not in GENERIC_SYMBOL_HINTS:
            symbol_hints.add(symbol)
    for match in re.finditer(r",\s*([A-Za-z_][A-Za-z0-9_]*)", text):
        symbol = match.group(1).lower()
        if symbol not in GENERIC_SYMBOL_HINTS:
            symbol_hints.add(symbol)
    return path_hints, symbol_hints


def candidate_score(
    phrase: str,
    l2: str,
    path_hints: set[str],
    symbol_hints: set[str],
    representative_path: str,
    case: dict,
) -> tuple[int, str, bool]:
    case_name_text = f"{case.get('class_name', '')} {case.get('case_name', '')}".lower()
    phrase_tokens = tokens(phrase)
    l2_tokens = tokens(l2)
    case_tokens = case["_tokens"]
    atom_overlap = phrase_tokens & case_tokens
    name_overlap = phrase_tokens & case["_name_tokens"]
    l2_overlap = l2_tokens & case_tokens
    path = str(case.get("path") or "").lower()
    path_matches = {hint for hint in path_hints if hint and hint in path}
    symbol_matches = {hint for hint in symbol_hints if hint and hint in case_name_text}
    same_representative_file = bool(representative_path and path == representative_path.lower())
    exact_phrase = bool(
        slug(phrase)
        and re.search(rf"(?:^|_){re.escape(slug(phrase))}(?:_|$)", slug(case_name_text))
    )
    exact_l2 = bool(
        len(l2_tokens) >= 2
        and re.search(rf"(?:^|_){re.escape(slug(l2))}(?:_|$)", slug(case_name_text))
    )
    surface_signal = bool(same_representative_file or path_matches or symbol_matches or exact_l2)
    score = (
        len(atom_overlap) * 3
        + len(name_overlap) * 4
        + min(len(l2_overlap), 3)
        + len(path_matches) * 5
        + len(symbol_matches) * 6
        + (6 if same_representative_file else 0)
        + (5 if exact_l2 else 0)
        + (8 if exact_phrase else 0)
    )
    basis = (
        f"atom_tokens={sorted(atom_overlap)}; name_tokens={sorted(name_overlap)}; "
        f"l2_tokens={sorted(l2_overlap)}; path_hints={sorted(path_matches)}; "
        f"symbol_hints={sorted(symbol_matches)}; representative_file={same_representative_file}; "
        f"exact_atom={exact_phrase}; exact_l2={exact_l2}"
    )
    return score, basis, surface_signal


def choose_existing_binding(
    phrase: str,
    l2: str,
    path_hints: set[str],
    symbol_hints: set[str],
    representative_path: str,
    inventory: list[dict],
    token_index: dict[str, set[int]],
    selector_use: Counter,
) -> tuple[dict | None, str, int]:
    ranked = []
    candidate_indices: set[int] = set()
    for token in tokens(phrase):
        candidate_indices.update(token_index.get(token, set()))
    for case_index in sorted(candidate_indices):
        case = inventory[case_index]
        score, basis, surface_signal = candidate_score(
            phrase, l2, path_hints, symbol_hints, representative_path, case
        )
        if surface_signal and score >= 14:
            ranked.append((score, -selector_use[case["selector"]], case["selector"], case, basis))
    ranked.sort(reverse=True)
    for score, _reuse, _selector, case, basis in ranked:
        phrase_token_count = len(tokens(phrase))
        overlap = tokens(phrase) & case["_tokens"]
        phrase_slug = slug(phrase)
        selector_slug = slug(f"{case.get('class_name', '')} {case.get('case_name', '')}")
        exact_phrase = bool(
            phrase_slug
            and re.search(rf"(?:^|_){re.escape(phrase_slug)}(?:_|$)", selector_slug)
        )
        name_overlap = tokens(phrase) & case["_name_tokens"]
        l2_name_overlap = tokens(l2) & case["_name_tokens"]
        path = str(case.get("path") or "").lower()
        path_matches = {hint for hint in path_hints if hint and hint in path}
        case_name_text = (
            f"{case.get('class_name', '')} {case.get('case_name', '')} "
            f"{case.get('behavior_fingerprint', '')}"
        ).lower()
        symbol_matches = {hint for hint in symbol_hints if hint and hint in case_name_text}
        exact_l2 = bool(
            len(tokens(l2)) >= 2
            and re.search(rf"(?:^|_){re.escape(slug(l2))}(?:_|$)", selector_slug)
        )
        same_file = bool(representative_path and path == representative_path.lower())
        strong_surface = bool(path_matches or symbol_matches or exact_l2)
        # The surface signal above prevents generic vocabulary from crossing
        # L2 boundaries.  The behavior signal below then requires the atomic
        # phrase to be visible in the selector.  Assertion-body vocabulary is
        # supporting evidence only; it cannot rescue a vague selector match.
        if phrase_token_count == 1:
            # A single generic noun (for example ``data``, ``runtime``, or
            # ``gate``) is not enough to prove assertion-level equivalence.
            # It remains unresolved unless selected as the L2 anchor below.
            behavior_signal = False
        else:
            required_name_overlap = max(2, math.ceil(phrase_token_count * 0.75))
            atom_name_signal = exact_phrase or len(name_overlap) >= required_name_overlap
            behavior_signal = atom_name_signal and (
                strong_surface or (same_file and len(l2_name_overlap) >= 2)
            )
        if behavior_signal and selector_use[case["selector"]] < 3:
            return case, basis, score
    return None, "", 0


def representative_targets() -> dict[str, dict]:
    matrix = json.loads((HERE / "l2_execution_matrix.json").read_text(encoding="utf-8"))
    result = {}
    for row in matrix["features"]:
        l2 = clean_l2(row["level_2_feature"])
        probe_id = row.get("probe_id")
        result[l2] = {
            "probe_id": probe_id,
            "probe": matrix["probes"].get(probe_id) if probe_id else None,
            "implementation_status": row["implementation_status"],
        }
    return result


def load_atomic_audit(audit_path: Path) -> dict[str, dict]:
    if not audit_path.exists():
        return {}
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    result = {}
    for row in payload.get("atomic_features", []):
        atomic_id = row.get("atomic_feature_id")
        if not atomic_id:
            continue
        disposition = row.get("gate_disposition")
        if disposition is None:
            continue
        result[atomic_id] = disposition
    return result


def load_binding_overrides(override_path: Path) -> dict[str, dict]:
    if not override_path.exists():
        return {}
    payload = json.loads(override_path.read_text(encoding="utf-8"))
    return {
        key: value for key, value in payload.items() if key and isinstance(value, dict)
    }


def apply_audit_profile(row: dict, disposition: str) -> None:
    profile = AUDIT_DISPOSITION_MAP.get(disposition)
    if not profile:
        return
    row["coverage_relationship"] = profile["coverage_relationship"]
    row["current_result"] = profile["current_result"]
    row["test_generation_status"] = profile["test_generation_status"]
    row["implementation_status"] = profile.get(
        "implementation_status", row["implementation_status"]
    )
    if row["test_generation_status"] in ALWAYS_CLEAR_BINDING_STATUSES:
        row["test_binding_id"] = None
        row["test_name"] = row["test_name"] if row["test_generation_status"] != "MANUAL_ORACLE_REQUIRED" else row["test_name"]
        row["test_file"] = None
        row["test_selector"] = None
        row["runner"] = None
        row["runner_command"] = None
        row["mapping_score"] = None
        if row["current_result"] == "PASS":
            row["blocker_or_notes"] = "Environment or implementation-boundary mapping was not required."


def apply_override_profile(row: dict, override: dict) -> None:
    if "test_generation_status" in override:
        row["test_generation_status"] = override["test_generation_status"]
    if "coverage_relationship" in override:
        row["coverage_relationship"] = override["coverage_relationship"]
    if "current_result" in override:
        row["current_result"] = override["current_result"]
    if "implementation_status" in override:
        row["implementation_status"] = override["implementation_status"]
    if "mapping_confidence" in override:
        row["mapping_confidence"] = override["mapping_confidence"]
    if "test_binding_id" in override:
        row["test_binding_id"] = override["test_binding_id"]
    if "test_name" in override:
        row["test_name"] = override["test_name"]
    if "test_file" in override:
        row["test_file"] = override["test_file"]
    if "test_selector" in override:
        row["test_selector"] = override["test_selector"]
    if "runner" in override:
        row["runner"] = override["runner"]
    if "runner_command" in override:
        row["runner_command"] = override["runner_command"]
    if "mapping_basis" in override:
        row["mapping_basis"] = override["mapping_basis"]
    if "generation_attempt" in override:
        row["generation_attempt"] = override["generation_attempt"]
    if "blocker_or_notes" in override:
        row["blocker_or_notes"] = override["blocker_or_notes"]



def runner_command(case: dict) -> str:
    runner = case["runner"]
    selector = case["selector"]
    if runner == "pytest":
        return f".\\.venv\\Scripts\\python.exe -m pytest -q {selector}"
    path = case["path"]
    if runner == "bun":
        return f"bun test {path}"
    if runner == "node":
        return f"node {path}"
    if runner == "bash":
        return f"bash {path}"
    if runner == "powershell":
        return f"powershell -NoProfile -File {path}"
    return ""


def atomic_l2_rollup(rows: list[dict]) -> tuple[str, str]:
    failed = [row for row in rows if row["current_result"] == "FAIL"]
    if failed:
        return (
            "FUNCTION_IMPLEMENTED_ATOMIC_TEST_FAILED",
            f"{len(failed)} atomic executable test(s) failed; L2 PASS is prohibited.",
        )
    blocked = [row for row in rows if row["implementation_status"] == "NOT_IMPLEMENTED"]
    if blocked:
        return (
            "FUNCTION_NOT_IMPLEMENTED_TEST_BLOCKED",
            f"{len(blocked)} required atomic behavior(s) are outside the current implementation boundary.",
        )
    unresolved = [row for row in rows if row["current_result"] not in {"PASS", "FAIL"}]
    if unresolved:
        return (
            "IMPLEMENTED_TEST_GAP_BLOCKED",
            f"{len(unresolved)} implemented atomic feature(s) still lack a defensible executable PASS/FAIL result.",
        )
    if rows and all(row["current_result"] == "PASS" for row in rows):
        return (
            "FUNCTION_IMPLEMENTED_ALL_ATOMIC_TESTS_PASSED",
            f"All {len(rows)} required atomic behaviors have current PASS evidence.",
        )
    return "ATOMIC_ROLLUP_INCONCLUSIVE", "Atomic results contain an unsupported mixed state."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=HERE / "l2_atomic_source.json")
    parser.add_argument("--inventory", type=Path, default=HERE / "atomic_test_inventory.json")
    parser.add_argument("--results", type=Path, default=HERE / "atomic_test_run_results.json")
    parser.add_argument("--output", type=Path, default=HERE / "atomic_feature_matrix.json")
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))["l2_features"]
    audit_profiles = load_atomic_audit(AUDIT_PATH)
    override_profiles = load_binding_overrides(OVERRIDE_PATH)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))["cases"]
    inventory_by_case_name = {case.get("case_name"): case for case in inventory if case.get("case_name")}
    inventory_by_selector = {case["selector"]: case for case in inventory}
    inventory_by_path: dict[str, list[dict]] = defaultdict(list)
    for case in inventory:
        inventory_by_path[case["path"]].append(case)
    execution_results = {}
    if args.results.exists():
        result_payload = json.loads(args.results.read_text(encoding="utf-8"))
        execution_results = {item["selector"]: item for item in result_payload.get("results", [])}
    token_index: dict[str, set[int]] = defaultdict(set)
    for case_index, case in enumerate(inventory):
        case["_tokens"] = tokens(inventory_case_text(case))
        case["_name_tokens"] = tokens(f"{case.get('class_name', '')} {case.get('case_name', '')}")
        for token in case["_tokens"]:
            token_index[token].add(case_index)
    representatives = representative_targets()
    selector_use: Counter = Counter()
    rows = []
    l2_summaries = []
    category_index = Counter()

    for global_l2_index, item in enumerate(source, start=1):
        sheet = item["sheet"]
        category = {"Workflow Features": "WF", "Foundation Features": "FN", "Vertical Features": "VT"}[sheet]
        category_index[category] += 1
        l2_index = category_index[category]
        l2 = clean_l2(item["level_2"])
        representative = representatives[l2]
        l2_not_implemented = representative["implementation_status"] == "NOT_IMPLEMENTED"
        phrases = atomic_phrases(item["contract"]["granularity"], l2)
        if not phrases:
            raise ValueError(f"No reviewed atomic features derived for {sheet} / {l2}")

        l2_rows = []
        path_hints, symbol_hints = entrypoint_hints(item["code_evidence"]["entrypoints"])
        representative_path = ""
        if representative["probe"]:
            representative_path = representative["probe"]["target"].split("::", 1)[0].removeprefix("./")
        for atom_index, phrase in enumerate(phrases, start=1):
            atomic_id = f"P22-AF-{category}-{l2_index:03d}-{atom_index:02d}"
            absent = explicit_absence(l2, phrase, l2_not_implemented)
            unresolved_status, unresolved_reason = unresolved_generation_tag(l2, phrase)
            planned_name = f"test_atomic_{slug(l2)}__{slug(phrase)}"
            row = {
                "atomic_feature_id": atomic_id,
                "sheet": sheet,
                "level_1_feature": item["level_1"],
                "level_2_feature": l2,
                "level_2_description": item["level_2_description"],
                "atomic_feature_name": phrase,
                "atomic_feature_description": f"For {l2}, independently verify: {phrase}.",
                "scenario_type": scenario_type(phrase),
                "review_decision": "APPROVED_REPLACEMENT",
                "review_basis": "Derived from the canonical L2 granularity contract and checked against the recorded current-code boundary.",
                "historical_atomic_rows_replaced": item["historical_atomic_count"],
                "implementation_status": "NOT_IMPLEMENTED" if absent else "IMPLEMENTED_CURRENT_SUBSET_UNVERIFIED",
                "test_generation_status": "BLOCKED_NOT_IMPLEMENTED" if absent else unresolved_status,
                "coverage_relationship": "UNRESOLVED",
                "test_binding_id": None,
                "test_name": planned_name,
                "test_file": None,
                "test_selector": None,
                "runner": None,
                "runner_command": None,
                "mapping_basis": (
                    "Explicitly outside the current implementation boundary; retained as a to-be atomic feature."
                    if absent
                    else "No assertion-level executable binding has yet been accepted."
                ),
                "mapping_score": None,
                "mapping_confidence": "NONE",
                "generation_attempt": (
                    "Not attempted: the behavior is explicitly outside the current implementation boundary."
                    if absent
                    else "Attempted exact generated-selector discovery, curated mapping, and conservative assertion/name/code-surface matching."
                ),
                "current_result": "BLOCKED_IMPLEMENTATION" if absent else "NOT_RUN",
                "blocker_or_notes": (
                    item["code_evidence"]["limitations"] if absent else unresolved_reason
                ),
                "source_granularity": item["contract"]["granularity"],
                "code_entrypoints": item["code_evidence"]["entrypoints"],
                "code_limitations": item["code_evidence"]["limitations"],
            }
            if not absent:
                generated_case = inventory_by_case_name.get(planned_name)
                if generated_case:
                    case, basis, score = generated_case, "Exact generated Phase 22 selector name.", None
                    generation_status = "GENERATED_EXECUTABLE"
                    confidence = "HIGH_GENERATED_EXACT"
                elif (l2, phrase) in CURATED_BINDINGS:
                    curated_selector = CURATED_BINDINGS[(l2, phrase)]
                    case = inventory_by_selector[curated_selector]
                    basis, score = "Human-reviewed exact behavior binding.", None
                    generation_status = "REUSED_EXISTING_EXECUTABLE"
                    confidence = "HIGH_CURATED_EXACT"
                else:
                    case, basis, score = choose_existing_binding(
                        phrase,
                        l2,
                        path_hints,
                        symbol_hints,
                        representative_path,
                        inventory,
                        token_index,
                        selector_use,
                    )
                    generation_status = "REUSED_EXISTING_EXECUTABLE"
                    confidence = "HIGH"
                if case:
                    selector_use[case["selector"]] += 1
                    execution = execution_results.get(case["selector"])
                    row.update(
                        {
                            "implementation_status": "IMPLEMENTED_EXECUTABLE_EVIDENCE",
                            "test_generation_status": generation_status,
                            "coverage_relationship": "DIRECT" if selector_use[case["selector"]] == 1 else "SHARED_DIRECT",
                            "test_binding_id": f"P22-ATB-{category}-{l2_index:03d}-{atom_index:02d}-01",
                            "test_name": case["case_name"],
                            "test_file": case["path"],
                            "test_selector": case["selector"],
                            "runner": case["runner"],
                            "runner_command": runner_command(case),
                            "mapping_basis": (
                                basis if generation_status == "GENERATED_EXECUTABLE"
                                else f"Conservative assertion/name/path match (score {score}): {basis}"
                            ),
                            "mapping_score": score,
                            "mapping_confidence": confidence,
                            "current_result": execution["result"] if execution else "NOT_RUN",
                            "blocker_or_notes": (
                                execution["evidence"]
                                if execution
                                else "Existing executable selector discovered; execution result must come from a current run."
                            ),
                        }
                    )
            if atomic_id in audit_profiles:
                apply_audit_profile(row, audit_profiles[atomic_id])
            if atomic_id in override_profiles:
                apply_override_profile(row, override_profiles[atomic_id])
            l2_rows.append(row)

        # Ensure each implemented L2 retains at least one verified executable
        # anchor.  Bind its representative probe only to the closest remaining
        # atomic behavior; never copy the probe across every child.
        if not l2_not_implemented and not any(row["test_selector"] for row in l2_rows):
            probe = representative["probe"]
            assert probe is not None
            probe_text = f"{probe['target']} {probe['rationale']}"
            target_row = max(l2_rows, key=lambda row: len(tokens(row["atomic_feature_name"]) & tokens(probe_text)))
            target = probe["target"]
            target_path = target.split("::", 1)[0].removeprefix("./")
            target_selector = target.removeprefix("./")
            target_name = target.split("::")[-1]
            if "::" not in target and target_path in inventory_by_path:
                representative_case = inventory_by_path[target_path][0]
                target_selector = representative_case["selector"]
                target_name = representative_case["case_name"]
            target_row.update(
                {
                    "implementation_status": "IMPLEMENTED_EXECUTABLE_EVIDENCE",
                    "test_generation_status": "REUSED_L2_REPRESENTATIVE_EXECUTABLE",
                    "coverage_relationship": "DIRECT",
                    "test_binding_id": f"P22-ATB-{category}-{l2_index:03d}-{l2_rows.index(target_row)+1:02d}-01",
                    "test_name": target_name,
                    "test_file": target_path,
                    "test_selector": target_selector,
                    "runner": probe["runner"],
                    "runner_command": (
                        f".\\.venv\\Scripts\\python.exe -m pytest -q {target}"
                        if probe["runner"] == "pytest"
                        else f"{probe['runner']} {target}"
                    ),
                    "mapping_basis": f"L2 representative probe bound only to closest atomic behavior: {probe['rationale']}",
                    "mapping_score": None,
                    "mapping_confidence": "HIGH_REPRESENTATIVE_ANCHOR",
                    "current_result": "NOT_RUN",
                    "blocker_or_notes": "Executable anchor only; sibling atomic features remain independently unresolved.",
                }
            )

        rollup_status, rollup_reason = atomic_l2_rollup(l2_rows)
        rows.extend(l2_rows)
        l2_summaries.append(
            {
                "sheet": sheet,
                "level_1_feature": item["level_1"],
                "level_2_feature": l2,
                "historical_atomic_rows": item["historical_atomic_count"],
                "reviewed_atomic_features": len(l2_rows),
                "removed_net_rows": item["historical_atomic_count"] - len(l2_rows),
                "executable_bound": sum(bool(row["test_selector"]) for row in l2_rows),
                "tagged_not_generated": sum(row["test_generation_status"].startswith("TAGGED_NOT_GENERATED") for row in l2_rows),
                "blocked_not_implemented": sum(row["test_generation_status"] == "BLOCKED_NOT_IMPLEMENTED" for row in l2_rows),
                "atomic_rollup_status": rollup_status,
                "atomic_rollup_reason": rollup_reason,
            }
        )

    status_counts = Counter(row["test_generation_status"] for row in rows)
    implementation_counts = Counter(row["implementation_status"] for row in rows)
    rollup_counts = Counter(item["atomic_rollup_status"] for item in l2_summaries)
    payload = {
        "schema": "phase22.atomic_feature_matrix.v1",
        "source_workbook": "docs/integrations/autosci/phase-22-test-report.xlsx",
        "review_policy": {
            "atomic_granularity": "One independently observable behavior, rejection branch, evidence obligation, or explicitly named technology/platform variant.",
            "historical_rows": "Historical path/template duplicates are replaced; they remain recoverable from Git commit 012e7a20 and the progress log.",
            "test_policy": "A test record or L2 representative probe is not copied to every atomic child. Only assertion-level defensible selectors are bound.",
            "blocked_policy": "Unimplemented or explicitly excluded behavior remains in the to-be hierarchy with BLOCKED_NOT_IMPLEMENTED and no fabricated selector.",
        },
        "counts": {
            "l2_features": len(l2_summaries),
            "historical_atomic_rows": sum(item["historical_atomic_rows"] for item in l2_summaries),
            "reviewed_atomic_features": len(rows),
            "net_rows_removed": sum(item["removed_net_rows"] for item in l2_summaries),
            "test_generation_status": dict(sorted(status_counts.items())),
            "implementation_status": dict(sorted(implementation_counts.items())),
            "l2_atomic_rollup_status": dict(sorted(rollup_counts.items())),
        },
        "l2_summary": l2_summaries,
        "atomic_features": rows,
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
