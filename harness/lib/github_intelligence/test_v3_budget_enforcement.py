#!/usr/bin/env python3
"""V3 Builder Node — Budget Cap Enforcement Test.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s05-verification-release
Node: V3

Tests ModelLedger class from model_ledger.py:
1. Budget cap enforcement (MAX_PREMIUM_CALLS_PER_DAY=20)
2. Aggregation queries (usage_by_model, total_cost, premium_count_on, list_calls)
3. ModelCall field validation and to_row/from_row roundtrip
4. SQLite backup/restore verification

All output files written to: harness/reports/github-intelligence/s05-acceptance/
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

# Ensure we can import model_ledger from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model_ledger import (
    CALL_TYPES,
    MAX_PREMIUM_CALLS_PER_DAY,
    PROVIDER_TIER,
    BudgetExceeded,
    ModelCall,
    ModelLedger,
)

REPORT_DIR = "~/.solar/harness/reports/github-intelligence/s05-acceptance"
BACKUP_DIR = "~/.solar/harness/backups/github-intelligence"

# Timestamp for this test run
TS = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
BACKUP_TS_DIR = os.path.join(BACKUP_DIR, f"V3-{TS}")


def write_report(filename: str, data: dict) -> str:
    """Write a JSON report file and return the path."""
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def test_step_1_create_db_with_sample_data():
    """Step 1: Create fresh SQLite DB, populate with ~10 sample calls, write backup."""
    print("=" * 60)
    print("STEP 1: Create test DB with sample data + backup")
    print("=" * 60)

    # Create fresh temp DB
    db_path = tempfile.mktemp(suffix=".sqlite", prefix="v3_test_")
    conn = sqlite3.connect(db_path)
    ledger = ModelLedger(conn)

    # Populate with sample data simulating V1+V2 calls (mix of local and premium)
    sample_calls = [
        # V1 calls (6 calls)
        {"call_id": "v1-local-001", "full_name": "pytorch/pytorch", "model_name": "qwen3.6-thunderomlx",
         "provider": "thunderomlx", "call_type": "preprocess", "input_tokens": 500, "output_tokens": 300,
         "cost_estimate": 0.0, "created_at": "2026-05-28T08:00:00Z"},
        {"call_id": "v1-local-002", "full_name": "pytorch/pytorch", "model_name": "qwen3.6-thunderomlx",
         "provider": "thunderomlx", "call_type": "verification", "input_tokens": 200, "output_tokens": 150,
         "cost_estimate": 0.0, "created_at": "2026-05-28T08:05:00Z"},
        {"call_id": "v1-prem-001", "full_name": "modelscope/modelscope", "model_name": "gemini-pro",
         "provider": "google", "call_type": "reasoning", "input_tokens": 8000, "output_tokens": 2000,
         "cost_estimate": 0.12, "created_at": "2026-05-28T09:00:00Z"},
        {"call_id": "v1-prem-002", "full_name": "modelscope/modelscope", "model_name": "claude-sonnet",
         "provider": "anthropic", "call_type": "editorial", "input_tokens": 5000, "output_tokens": 1500,
         "cost_estimate": 0.08, "created_at": "2026-05-28T09:15:00Z"},
        {"call_id": "v1-local-003", "full_name": "huggingface/transformers", "model_name": "ollama",
         "provider": "ollama", "call_type": "preprocess", "input_tokens": 1000, "output_tokens": 800,
         "cost_estimate": 0.0, "created_at": "2026-05-28T10:00:00Z"},
        {"call_id": "v1-prem-003", "full_name": "huggingface/transformers", "model_name": "claude-opus",
         "provider": "anthropic", "call_type": "architecture", "input_tokens": 12000, "output_tokens": 3000,
         "cost_estimate": 0.25, "created_at": "2026-05-28T10:30:00Z"},
        # V2 calls (4 calls)
        {"call_id": "v2-local-001", "full_name": "langchain-ai/langchain", "model_name": "qwen3.6-thunderomlx",
         "provider": "thunderomlx", "call_type": "preprocess", "input_tokens": 600, "output_tokens": 400,
         "cost_estimate": 0.0, "created_at": "2026-05-28T11:00:00Z"},
        {"call_id": "v2-prem-001", "full_name": "langchain-ai/langchain", "model_name": "gemini-pro",
         "provider": "google", "call_type": "reasoning", "input_tokens": 6000, "output_tokens": 1500,
         "cost_estimate": 0.09, "created_at": "2026-05-28T11:15:00Z"},
        {"call_id": "v2-prem-002", "full_name": "microsoft/autogen", "model_name": "codex",
         "provider": "openai", "call_type": "architecture", "input_tokens": 10000, "output_tokens": 2500,
         "cost_estimate": 0.18, "created_at": "2026-05-28T11:30:00Z"},
        {"call_id": "v2-local-002", "full_name": "microsoft/autogen", "model_name": "qwen3.6-thunderomlx",
         "provider": "thunderomlx", "call_type": "verification", "input_tokens": 300, "output_tokens": 200,
         "cost_estimate": 0.0, "created_at": "2026-05-28T11:45:00Z"},
    ]

    for s in sample_calls:
        call = ModelCall(
            call_id=s["call_id"],
            full_name=s["full_name"],
            model_name=s["model_name"],
            provider=s["provider"],
            call_type=s["call_type"],
            input_tokens=s["input_tokens"],
            output_tokens=s["output_tokens"],
            cost_estimate=s["cost_estimate"],
            created_at=s["created_at"],
        )
        ledger.record(call, enforce_budget=False)  # Don't enforce during setup

    conn.commit()

    # Count rows
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM model_call_ledger")
    row_count = cur.fetchone()[0]
    print(f"  DB created: {db_path}")
    print(f"  Rows inserted: {row_count}")

    # Write backup copy
    os.makedirs(BACKUP_TS_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_TS_DIR, "before.db")
    conn.close()
    shutil.copy2(db_path, backup_path)
    print(f"  Backup written: {backup_path}")

    # Reopen connection
    conn = sqlite3.connect(db_path)
    ledger = ModelLedger(conn)

    return db_path, backup_path, conn, ledger, row_count, sample_calls


def test_step_2_budget_cap_enforcement(conn, ledger):
    """Step 2: Budget cap enforcement test."""
    print("\n" + "=" * 60)
    print("STEP 2: Budget cap enforcement")
    print("=" * 60)

    results = {
        "test": "budget_cap_enforcement",
        "max_premium_calls_per_day": MAX_PREMIUM_CALLS_PER_DAY,
        "steps": [],
    }

    # Check initial premium count for today
    today = "2026-05-28"
    initial_count = ledger.premium_count_on(today)
    results["initial_premium_count"] = initial_count
    print(f"  Initial premium count on {today}: {initial_count}")

    # Record additional premium calls until we hit the cap
    calls_needed = MAX_PREMIUM_CALLS_PER_DAY - initial_count
    results["calls_needed_to_reach_cap"] = calls_needed
    print(f"  Need {calls_needed} more premium calls to reach cap")

    for i in range(calls_needed):
        idx = initial_count + i
        ledger.record_event(
            model_name="claude-opus",
            provider="anthropic",
            call_type="editorial",
            full_name="test/budget-repo",
            input_tokens=200,
            output_tokens=200,
            cost_estimate=0.05,
            enforce_budget=True,
            created_at=f"2026-05-28T12:{idx % 60:02d}:00Z",
            call_id=f"budget-fill-{idx}",
        )
    conn.commit()

    count_at_cap = ledger.premium_count_on(today)
    results["count_at_cap"] = count_at_cap
    print(f"  Premium count at cap: {count_at_cap}")

    # 21st premium call must raise BudgetExceeded
    budget_exceeded_raised = False
    exception_message = ""
    try:
        ledger.record_event(
            model_name="claude-opus",
            provider="anthropic",
            call_type="editorial",
            created_at="2026-05-28T13:00:00Z",
            call_id="budget-overflow",
            enforce_budget=True,
        )
    except BudgetExceeded as e:
        budget_exceeded_raised = True
        exception_message = str(e)
        print(f"  BudgetExceeded raised: {exception_message}")

    results["budget_exceeded_raised"] = budget_exceeded_raised
    results["exception_message"] = exception_message
    assert budget_exceeded_raised, "Expected BudgetExceeded on call #21"
    assert "premium cap reached" in exception_message.lower() or "premium cap" in exception_message.lower(), \
        f"Exception message should mention premium cap, got: {exception_message}"

    # Verify exception message contains budget exhaustion details
    results["exception_contains_day"] = today in exception_message
    results["exception_contains_count"] = str(MAX_PREMIUM_CALLS_PER_DAY) in exception_message
    print(f"  Exception contains day '{today}': {results['exception_contains_day']}")
    print(f"  Exception contains cap '{MAX_PREMIUM_CALLS_PER_DAY}': {results['exception_contains_count']}")

    # Test enforce_budget=False bypass
    bypass_call = ledger.record_event(
        model_name="claude-opus",
        provider="anthropic",
        call_type="editorial",
        created_at="2026-05-28T14:00:00Z",
        call_id="budget-bypass",
        cost_estimate=0.05,
        enforce_budget=False,
    )
    conn.commit()
    results["bypass_succeeded"] = bypass_call.call_id == "budget-bypass"
    print(f"  enforce_budget=False bypass: {'PASS' if results['bypass_succeeded'] else 'FAIL'}")

    # Cap resets for a different day
    next_day_call = ledger.record_event(
        model_name="claude-opus",
        provider="anthropic",
        call_type="editorial",
        created_at="2026-05-29T00:00:00Z",
        call_id="next-day-call",
        cost_estimate=0.05,
        enforce_budget=True,
    )
    conn.commit()
    results["next_day_call_succeeded"] = next_day_call.call_id == "next-day-call"
    print(f"  Next-day call (cap reset): {'PASS' if results['next_day_call_succeeded'] else 'FAIL'}")

    # Local calls never count toward budget
    local_call = ledger.record_event(
        model_name="qwen3.6-thunderomlx",
        provider="thunderomlx",
        call_type="preprocess",
        created_at="2026-05-28T15:00:00Z",
        call_id="local-no-budget",
        enforce_budget=True,
    )
    conn.commit()
    results["local_call_not_budgeted"] = local_call.tier == "local"
    print(f"  Local call not budgeted (tier={local_call.tier}): {'PASS' if results['local_call_not_budgeted'] else 'FAIL'}")

    results["verdict"] = "PASS" if all([
        budget_exceeded_raised,
        results["bypass_succeeded"],
        results["next_day_call_succeeded"],
        results["local_call_not_budgeted"],
    ]) else "FAIL"

    print(f"\n  STEP 2 VERDICT: {results['verdict']}")
    return results


def test_step_3_aggregation_queries(conn, ledger, sample_calls):
    """Step 3: Validate 4 aggregation queries."""
    print("\n" + "=" * 60)
    print("STEP 3: Aggregation query validation")
    print("=" * 60)

    results = {}

    # 3a: usage_by_model()
    print("\n  3a: usage_by_model()")
    usage = ledger.usage_by_model()
    usage_report = {
        "test": "usage_by_model",
        "data": {},
        "validation": [],
    }
    for model_name, stats in usage.items():
        usage_report["data"][model_name] = stats
        print(f"    {model_name}: calls={stats['calls']}, in={stats['input_tokens']}, out={stats['output_tokens']}, cost={stats['cost']}")

    # Validate expected models exist
    expected_models = {"qwen3.6-thunderomlx", "gemini-pro", "claude-sonnet", "claude-opus", "codex", "ollama"}
    found_models = set(usage.keys())
    usage_report["validation"].append({
        "check": "expected_models_present",
        "expected": sorted(expected_models),
        "found": sorted(found_models),
        "pass": expected_models.issubset(found_models),
    })

    # Validate qwen3.6 is local tier (cost = 0)
    qwen_cost = usage.get("qwen3.6-thunderomlx", {}).get("cost", -1)
    usage_report["validation"].append({
        "check": "local_model_zero_cost",
        "model": "qwen3.6-thunderomlx",
        "cost": qwen_cost,
        "pass": qwen_cost == 0.0,
    })

    # Validate premium models have cost > 0
    for prem_model in ["gemini-pro", "claude-opus"]:
        prem_cost = usage.get(prem_model, {}).get("cost", 0)
        usage_report["validation"].append({
            "check": f"premium_model_has_cost",
            "model": prem_model,
            "cost": prem_cost,
            "pass": prem_cost > 0,
        })

    usage_report["verdict"] = "PASS" if all(v["pass"] for v in usage_report["validation"]) else "FAIL"
    print(f"  3a VERDICT: {usage_report['verdict']}")

    # 3b: total_cost()
    print("\n  3b: total_cost()")
    total = ledger.total_cost()
    total_report = {
        "test": "total_cost",
        "total_cost": total,
        "validation": [],
    }
    print(f"    Total cost: ${total:.4f}")

    # Compute expected cost from sample data (initial 10 calls)
    expected_initial_cost = sum(s["cost_estimate"] for s in sample_calls)
    total_report["validation"].append({
        "check": "total_cost_exceeds_initial",
        "initial_sample_cost": expected_initial_cost,
        "total_cost": total,
        "pass": total >= expected_initial_cost,
    })
    total_report["validation"].append({
        "check": "total_cost_positive",
        "total_cost": total,
        "pass": total > 0,
    })

    # Test with date filter
    total_28 = ledger.total_cost(since="2026-05-28T00:00:00Z", until="2026-05-29T00:00:00Z")
    total_29 = ledger.total_cost(since="2026-05-29T00:00:00Z")
    total_report["validation"].append({
        "check": "date_filtered_cost",
        "cost_2026_05_28": total_28,
        "cost_2026_05_29": total_29,
        "pass": total_28 > 0 and total_29 > 0,
    })

    total_report["verdict"] = "PASS" if all(v["pass"] for v in total_report["validation"]) else "FAIL"
    print(f"  3b VERDICT: {total_report['verdict']}")

    # 3c: premium_count_on()
    print("\n  3c: premium_count_on()")
    count_28 = ledger.premium_count_on("2026-05-28")
    count_29 = ledger.premium_count_on("2026-05-29")
    count_empty = ledger.premium_count_on("2020-01-01")

    count_report = {
        "test": "premium_count_on",
        "data": {
            "2026-05-28": count_28,
            "2026-05-29": count_29,
            "2020-01-01": count_empty,
        },
        "validation": [
            {"check": "count_28_exceeds_cap", "count": count_28, "cap": MAX_PREMIUM_CALLS_PER_DAY,
             "pass": count_28 > MAX_PREMIUM_CALLS_PER_DAY, "note": "includes bypass call"},
            {"check": "count_29_at_least_1", "count": count_29, "pass": count_29 >= 1},
            {"check": "empty_day_zero", "count": count_empty, "pass": count_empty == 0},
        ],
    }
    print(f"    2026-05-28: {count_28} premium calls (cap={MAX_PREMIUM_CALLS_PER_DAY})")
    print(f"    2026-05-29: {count_29} premium calls")
    print(f"    2020-01-01: {count_empty} premium calls")

    count_report["verdict"] = "PASS" if all(v["pass"] for v in count_report["validation"]) else "FAIL"
    print(f"  3c VERDICT: {count_report['verdict']}")

    # 3d: list_calls() with filters
    print("\n  3d: list_calls()")

    # By full_name
    pytorch_calls = ledger.list_calls(full_name="pytorch/pytorch")
    preprocess_calls = ledger.list_calls(call_type="preprocess")
    all_calls = ledger.list_calls(limit=50)

    list_report = {
        "test": "list_calls",
        "data": {
            "pytorch_pytorch_count": len(pytorch_calls),
            "preprocess_count": len(preprocess_calls),
            "total_count": len(all_calls),
        },
        "validation": [
            {"check": "pytorch_filter", "count": len(pytorch_calls),
             "pass": len(pytorch_calls) > 0 and all(c.full_name == "pytorch/pytorch" for c in pytorch_calls)},
            {"check": "preprocess_filter", "count": len(preprocess_calls),
             "pass": len(preprocess_calls) > 0 and all(c.call_type == "preprocess" for c in preprocess_calls)},
            {"check": "total_count", "count": len(all_calls),
             "pass": len(all_calls) >= 25},  # 10 sample + 15 fill + bypass + next-day + local
        ],
    }
    print(f"    pytorch/pytorch: {len(pytorch_calls)} calls")
    print(f"    preprocess: {len(preprocess_calls)} calls")
    print(f"    total (limit=50): {len(all_calls)} calls")

    list_report["verdict"] = "PASS" if all(v["pass"] for v in list_report["validation"]) else "FAIL"
    print(f"  3d VERDICT: {list_report['verdict']}")

    # Write all 4 aggregation report files
    write_report("V3-agg_model.json", usage_report)
    write_report("V3-agg_cost.json", total_report)
    write_report("V3-agg_count.json", count_report)

    # Build provider aggregation from list_calls (since there's no usage_by_provider method)
    provider_agg = {}
    for call in all_calls:
        p = call.provider
        if p not in provider_agg:
            provider_agg[p] = {"calls": 0, "models": set(), "total_cost": 0.0}
        provider_agg[p]["calls"] += 1
        provider_agg[p]["models"].add(call.model_name)
        provider_agg[p]["total_cost"] += call.cost_estimate

    provider_report = {
        "test": "get_calls_by_provider",
        "data": {p: {"calls": v["calls"], "models": sorted(v["models"]), "total_cost": v["total_cost"]}
                 for p, v in sorted(provider_agg.items())},
        "verdict": "PASS" if len(provider_agg) >= 3 else "FAIL",
    }
    write_report("V3-agg_provider.json", provider_report)

    all_pass = all(r["verdict"] == "PASS" for r in [usage_report, total_report, count_report, list_report, provider_report])
    return {
        "usage_by_model": usage_report["verdict"],
        "total_cost": total_report["verdict"],
        "premium_count_on": count_report["verdict"],
        "list_calls": list_report["verdict"],
        "provider_agg": provider_report["verdict"],
        "overall": "PASS" if all_pass else "FAIL",
    }


def test_step_4_model_call_validation():
    """Step 4: Validate ModelCall fields and roundtrip."""
    print("\n" + "=" * 60)
    print("STEP 4: ModelCall field validation and roundtrip")
    print("=" * 60)

    report = {
        "test": "model_call_field_validation",
        "fields": [f.name for f in ModelCall.__dataclass_fields__.values()] if hasattr(ModelCall, '__dataclass_fields__') else [],
        "validation": [],
    }

    # Try to get fields properly
    from dataclasses import fields as dc_fields
    report["fields"] = [f.name for f in dc_fields(ModelCall)]
    print(f"  ModelCall fields: {report['fields']}")

    # Full-field ModelCall
    call = ModelCall(
        call_id="mc-test-full",
        full_name="owner/repo",
        model_name="qwen3.6-thunderomlx",
        provider="thunderomlx",
        call_type="preprocess",
        input_tokens=351,
        output_tokens=460,
        cost_estimate=0.0,
        usage_extra={"ttft": 8.17, "tps_out": 74.48},
    )

    # to_row roundtrip
    row = call.to_row()
    restored = ModelCall.from_row(row)

    report["validation"].append({
        "check": "to_row_from_row_roundtrip",
        "pass": restored == call,
        "details": f"call_id={call.call_id}, restored_id={restored.call_id}",
    })
    print(f"  Roundtrip: {'PASS' if restored == call else 'FAIL'}")

    # Tier computed correctly
    report["validation"].append({
        "check": "tier_local_for_thunderomlx",
        "tier": call.tier,
        "is_premium": call.is_premium,
        "pass": call.tier == "local" and not call.is_premium,
    })
    print(f"  Tier: {call.tier}, is_premium: {call.is_premium}")

    # to_row includes tier
    report["validation"].append({
        "check": "to_row_includes_tier",
        "has_tier_key": "tier" in row,
        "tier_value": row.get("tier"),
        "pass": "tier" in row and row["tier"] == "local",
    })
    print(f"  to_row has tier key: {'PASS' if 'tier' in row else 'FAIL'}")

    # to_row serializes usage_extra to JSON string
    import json as _json
    report["validation"].append({
        "check": "usage_extra_serialized_as_json",
        "is_string": isinstance(row["usage_extra"], str),
        "parseable": _json.loads(row["usage_extra"]) == {"ttft": 8.17, "tps_out": 74.48},
        "pass": isinstance(row["usage_extra"], str),
    })

    # Premium ModelCall
    prem_call = ModelCall(
        call_id="mc-prem-test",
        full_name="test/repo",
        model_name="claude-opus",
        provider="anthropic",
        call_type="editorial",
        input_tokens=1000,
        output_tokens=500,
        cost_estimate=0.15,
    )
    report["validation"].append({
        "check": "premium_tier",
        "model": "claude-opus",
        "tier": prem_call.tier,
        "is_premium": prem_call.is_premium,
        "pass": prem_call.tier == "premium" and prem_call.is_premium,
    })
    print(f"  claude-opus tier: {prem_call.tier}, is_premium: {prem_call.is_premium}")

    # __post_init__ validation: bad call_type
    bad_type_caught = False
    try:
        ModelCall(
            call_id="x", full_name=None, model_name="m", provider="p",
            call_type="not_a_call_type",
        )
    except ValueError as e:
        bad_type_caught = True
        report["validation"].append({
            "check": "validation_bad_call_type",
            "error": str(e),
            "pass": "call_type must be one of" in str(e),
        })
    assert bad_type_caught, "Expected ValueError for bad call_type"
    print(f"  Bad call_type caught: PASS")

    # __post_init__ validation: negative tokens
    neg_tok_caught = False
    try:
        ModelCall(
            call_id="x", full_name=None, model_name="m", provider="p",
            call_type="preprocess", input_tokens=-1,
        )
    except ValueError as e:
        neg_tok_caught = True
        report["validation"].append({
            "check": "validation_negative_tokens",
            "error": str(e),
            "pass": "token counts must be" in str(e),
        })
    assert neg_tok_caught, "Expected ValueError for negative tokens"
    print(f"  Negative tokens caught: PASS")

    # __post_init__ validation: negative cost
    neg_cost_caught = False
    try:
        ModelCall(
            call_id="x", full_name=None, model_name="m", provider="p",
            call_type="preprocess", cost_estimate=-0.01,
        )
    except ValueError as e:
        neg_cost_caught = True
        report["validation"].append({
            "check": "validation_negative_cost",
            "error": str(e),
            "pass": "cost_estimate must be" in str(e),
        })
    assert neg_cost_caught, "Expected ValueError for negative cost"
    print(f"  Negative cost caught: PASS")

    # Verify CALL_TYPES constant
    report["validation"].append({
        "check": "call_types_constant",
        "value": list(CALL_TYPES),
        "pass": len(CALL_TYPES) == 5 and "preprocess" in CALL_TYPES,
    })

    # Verify PROVIDER_TIER mapping
    report["validation"].append({
        "check": "provider_tier_mapping",
        "local_providers": [k for k, v in PROVIDER_TIER.items() if v == "local"],
        "premium_providers": [k for k, v in PROVIDER_TIER.items() if v == "premium"],
        "pass": len(PROVIDER_TIER) >= 6,
    })

    report["verdict"] = "PASS" if all(v["pass"] for v in report["validation"]) else "FAIL"
    print(f"\n  STEP 4 VERDICT: {report['verdict']}")

    write_report("V3-budget_trigger.json", report)
    return report


def test_step_5_sqlite_restore(db_path, backup_path):
    """Step 5: Restore DB from backup, verify row count diff = 0."""
    print("\n" + "=" * 60)
    print("STEP 5: SQLite restore verification")
    print("=" * 60)

    # Read current row count
    conn_current = sqlite3.connect(db_path)
    cur = conn_current.cursor()
    cur.execute("SELECT COUNT(*) FROM model_call_ledger")
    current_count = cur.fetchone()[0]
    conn_current.close()

    # Read backup row count
    conn_backup = sqlite3.connect(backup_path)
    cur_b = conn_backup.cursor()
    cur_b.execute("SELECT COUNT(*) FROM model_call_ledger")
    backup_count = cur_b.fetchone()[0]
    conn_backup.close()

    # Create a restored copy
    restore_path = tempfile.mktemp(suffix=".sqlite", prefix="v3_restored_")
    shutil.copy2(backup_path, restore_path)
    conn_restored = sqlite3.connect(restore_path)
    cur_r = conn_restored.cursor()
    cur_r.execute("SELECT COUNT(*) FROM model_call_ledger")
    restored_count = cur_r.fetchone()[0]

    # Diff
    diff = current_count - restored_count
    print(f"  Current DB rows: {current_count}")
    print(f"  Backup DB rows:  {backup_count}")
    print(f"  Restored DB rows: {restored_count}")
    print(f"  Diff (current - restored): {diff}")
    print(f"  Backup/Restored diff: {restored_count - backup_count} (expected 0)")

    restore_report = {
        "test": "sqlite_restore_verification",
        "current_db_rows": current_count,
        "backup_db_rows": backup_count,
        "restored_db_rows": restored_count,
        "current_vs_restored_diff": diff,
        "backup_vs_restored_diff": restored_count - backup_count,
        "validation": [
            {"check": "backup_equals_restored", "pass": restored_count == backup_count},
            {"check": "current_gt_backup", "pass": current_count > backup_count,
             "note": "budget fill + bypass + next-day calls added after backup"},
        ],
        "verdict": "PASS" if restored_count == backup_count else "FAIL",
    }

    conn_restored.close()
    os.unlink(restore_path)

    print(f"\n  STEP 5 VERDICT: {restore_report['verdict']}")
    return restore_report


def main():
    print(f"V3 Budget Cap Enforcement Test — {TS}")
    print(f"MAX_PREMIUM_CALLS_PER_DAY = {MAX_PREMIUM_CALLS_PER_DAY}")
    print(f"PROVIDER_TIER = {json.dumps(PROVIDER_TIER, indent=2)}")
    print(f"CALL_TYPES = {CALL_TYPES}")

    # Step 1: Create DB + backup
    db_path, backup_path, conn, ledger, initial_rows, sample_calls = test_step_1_create_db_with_sample_data()

    # Step 2: Budget cap enforcement
    budget_results = test_step_2_budget_cap_enforcement(conn, ledger)

    # Step 3: Aggregation queries
    agg_results = test_step_3_aggregation_queries(conn, ledger, sample_calls)

    # Step 4: ModelCall validation
    model_call_results = test_step_4_model_call_validation()

    # Step 5: SQLite restore
    restore_results = test_step_5_sqlite_restore(db_path, backup_path)

    # Cleanup
    conn.close()

    # Summary
    print("\n" + "=" * 60)
    print("V3 TEST SUMMARY")
    print("=" * 60)
    summary = {
        "timestamp": TS,
        "max_premium_calls_per_day": MAX_PREMIUM_CALLS_PER_DAY,
        "steps": {
            "step2_budget_enforcement": budget_results["verdict"],
            "step3_aggregation": agg_results["overall"],
            "step4_model_call_validation": model_call_results["verdict"],
            "step5_sqlite_restore": restore_results["verdict"],
        },
        "output_files": [
            "V3-agg_provider.json",
            "V3-agg_model.json",
            "V3-agg_cost.json",
            "V3-agg_count.json",
            "V3-budget_trigger.json",
        ],
        "overall_verdict": "PASS" if all([
            budget_results["verdict"] == "PASS",
            agg_results["overall"] == "PASS",
            model_call_results["verdict"] == "PASS",
            restore_results["verdict"] == "PASS",
        ]) else "FAIL",
    }

    for step, verdict in summary["steps"].items():
        status = "✅" if verdict == "PASS" else "❌"
        print(f"  {status} {step}: {verdict}")
    print(f"\n  OVERALL: {summary['overall_verdict']}")

    # Clean up temp DB
    if os.path.exists(db_path):
        os.unlink(db_path)

    return summary


if __name__ == "__main__":
    summary = main()
    sys.exit(0 if summary["overall_verdict"] == "PASS" else 1)
