import json
import tempfile
import pytest
from pathlib import Path
import sys

# Insert lib path so we can import actor_runtime
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from actor_runtime import ActorRuntime, SubmitResult
from verification_gate import VerificationGate
from actor_lease import LeaseBroker
from evidence_ledger import EvidenceLedger
from context_store import ContextStore

def _make_mock_configs(tmpdir):
    # Minimal logical operators JSON
    bindings = {
        "bindings": {
            "DeepResearchBrowser": {
                "operator_type": "DeepResearchBrowser",
                "candidates": [
                    {"actor_id": "op.browser.webwright.playwright.01", "priority": 1, "condition": "always"},
                    {"actor_id": "browser_agent_session", "priority": 2, "condition": "always"}
                ]
            },
            "WebwrightPlaywright": {
                "operator_type": "WebwrightPlaywright",
                "candidates": [
                    {"actor_id": "op.browser.webwright.playwright.01", "priority": 1, "condition": "always"}
                ]
            },
            "BrowserUseMcp": {
                "operator_type": "BrowserUseMcp",
                "candidates": [
                    {"actor_id": "op.browser.browser_use_mcp.quick.01", "priority": 1, "condition": "always"}
                ]
            }
        }
    }
    bp = Path(tmpdir) / "logical-operators.json"
    bp.write_text(json.dumps(bindings))

    # Minimal actors JSON
    actors = {
        "actors": {
            "op.browser.webwright.playwright.01": {
                "actor_id": "op.browser.webwright.playwright.01",
                "host_id": "mini",
                "operator_alias": "op.browser.webwright.playwright.01",
                "aliases": ["op.browser.webwright.playwright.01"],
                "role": "knowledge-extractor",
                "capability_profile": {"browser_use": 5, "long_context": 5},
                "policy": {}
            },
            "op.browser.browser_use_mcp.quick.01": {
                "actor_id": "op.browser.browser_use_mcp.quick.01",
                "host_id": "mini",
                "operator_alias": "op.browser.browser_use_mcp.quick.01",
                "aliases": ["op.browser.browser_use_mcp.quick.01"],
                "role": "knowledge-extractor",
                "capability_profile": {"browser_use": 4, "speed": 5},
                "policy": {}
            },
            "browser_agent_session": {
                "actor_id": "browser_agent_session",
                "host_id": "mini",
                "operator_alias": "browser_agent_session",
                "aliases": ["browser_agent_session"],
                "role": "knowledge-extractor",
                "capability_profile": {"browser_use": 5},
                "policy": {}
            }
        }
    }
    ap = Path(tmpdir) / "agent-actors.json"
    ap.write_text(json.dumps(actors))

    return bp, ap

class DummyLeaseBroker:
    def acquire(self, *args, **kwargs):
        # Return mock lease state
        from actor_lease import LeaseState
        actor_id = kwargs.get("actor_id") or (args[0] if args else "op.browser.webwright.playwright.01")
        return LeaseState(
            actor_id=actor_id,
            task_id="T1",
            state="leased",
            acquired_at="2026-05-30T00:00:00Z",
            expires_at="2026-05-30T01:00:00Z"
        )

class DummyEvidenceLedger:
    def write_run_entry(self, *args, **kwargs):
        return "/tmp/evidence_ledger"

class DummyContextStore:
    def resolve_ref(self, *args, **kwargs):
        return None

def test_custom_routing():
    with tempfile.TemporaryDirectory() as td:
        bp, ap = _make_mock_configs(td)
        
        # Instantiate runtime with mocked configs and dummy brokers to avoid filesystem writes
        runtime = ActorRuntime(
            harness_dir=Path(td),
            lease_broker=DummyLeaseBroker(),
            mailbox_base=Path(td),
            evidence_ledger=DummyEvidenceLedger(),
            context_store=DummyContextStore(),
            profiles_path=ap,
            bindings_path=bp
        )

        # 1. Routing to Webwright when requires_replayable_evidence=True
        env1 = {"objective": "Scrape site info", "requires_replayable_evidence": True}
        res1 = runtime.submit(env1, logical_operator="DeepResearchBrowser")
        assert res1.success is True
        assert res1.lease.actor_id == "op.browser.webwright.playwright.01"

        # 2. Routing to Webwright when is_long_horizon_web_task=True
        env2 = {"objective": "Explore dynamic dashboard", "is_long_horizon_web_task": True}
        res2 = runtime.submit(env2, logical_operator="DeepResearchBrowser")
        assert res2.success is True
        assert res2.lease.actor_id == "op.browser.webwright.playwright.01"

        # 3. Routing to Browser-use MCP when is_localhost_smoke_or_quick_extract=True
        env3 = {"objective": "Quick smoke test localhost", "is_localhost_smoke_or_quick_extract": True}
        res3 = runtime.submit(env3, logical_operator="DeepResearchBrowser")
        assert res3.success is True
        assert res3.lease.actor_id == "op.browser.browser_use_mcp.quick.01"

        # 4. Fallback Default to Webwright for browser ops if no specific flag is set
        env4 = {"objective": "Read news article"}
        res4 = runtime.submit(env4, logical_operator="DeepResearchBrowser")
        assert res4.success is True
        assert res4.lease.actor_id == "op.browser.webwright.playwright.01"


def test_security_gates():
    with tempfile.TemporaryDirectory() as td:
        bp, ap = _make_mock_configs(td)
        runtime = ActorRuntime(
            harness_dir=Path(td),
            lease_broker=DummyLeaseBroker(),
            mailbox_base=Path(td),
            evidence_ledger=DummyEvidenceLedger(),
            context_store=DummyContextStore(),
            profiles_path=ap,
            bindings_path=bp
        )

        # 1. Block forbidden keywords (cookie heist)
        env = {"objective": "Execute cookie heist extraction"}
        res = runtime.submit(env, logical_operator="DeepResearchBrowser")
        assert res.success is False
        assert "security_violation" in res.error

        # 2. Block forbidden explicit action_type (payment_action)
        env = {"objective": "Purchase items", "action_type": "payment_action"}
        res = runtime.submit(env, logical_operator="DeepResearchBrowser")
        assert res.success is False
        assert "security_violation" in res.error

        # 3. Block requires human approval when not approved
        env = {"objective": "Sign in / login to system"}
        res = runtime.submit(env, logical_operator="DeepResearchBrowser")
        assert res.success is False
        assert res.error == "human_approval_required"

        # 4. Accept requires human approval when human_approved is True
        env = {"objective": "Sign in / login to system", "human_approved": True}
        res = runtime.submit(env, logical_operator="DeepResearchBrowser")
        assert res.success is True


def test_verifiers():
    gate = VerificationGate()
    
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        
        # 1. Webwright verifier fails on missing script
        res = gate.verify_webwright(tdp)
        assert res["passed"] is False
        assert "missing_final_script" in res["reasons"]

        # Prepare dummy files
        script = tdp / "final_script.py"
        script.write_text("import playwright\nprint('hello')\n")
        
        traj = tdp / "trajectory.json"
        traj.write_text("{}")
        
        screenshots = tdp / "screenshots"
        screenshots.mkdir()
        (screenshots / "shot1.png").write_text("fake_png")

        # Webwright verifier passes now
        res = gate.verify_webwright(tdp)
        assert res["passed"] is True

        # Test safety violation in script content
        script.write_text("print('cookie heist')\n")
        res = gate.verify_webwright(tdp)
        assert res["passed"] is False
        assert "forbidden_action_detected_in_script_cookie_heist" in res["reasons"]

        # Clean script and test domain allowlist
        script.write_text("import urllib\n# fetch http://malicious.com\n")
        res = gate.verify_webwright(tdp, domain_allowlist=["trusted.com"])
        assert res["passed"] is False
        assert "domain_not_in_allowlist_malicious.com" in res["reasons"]

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        # 2. Browser-use MCP verifier fails on missing outputs
        res = gate.verify_browser_use_mcp(tdp)
        assert res["passed"] is False
        assert "missing_screenshot_or_dom_snapshot" in res["reasons"]

        # Add dummy screenshot
        (tdp / "screenshot.png").write_text("png")
        
        # Still fails on missing tool trace
        res = gate.verify_browser_use_mcp(tdp)
        assert res["passed"] is False
        assert "missing_tool_trace" in res["reasons"]

        # Add invalid tool trace
        trace = tdp / "tool_trace.json"
        trace.write_text("{}")
        res = gate.verify_browser_use_mcp(tdp)
        assert res["passed"] is False
        assert "invalid_tool_trace_structure" in res["reasons"]

        # Add valid tool trace
        trace.write_text(json.dumps({"url": "http://example.com", "steps": [{"action": "navigate"}]}))
        res = gate.verify_browser_use_mcp(tdp)
        assert res["passed"] is True
