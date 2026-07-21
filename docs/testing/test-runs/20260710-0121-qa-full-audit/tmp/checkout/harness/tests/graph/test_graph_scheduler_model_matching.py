import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from graph_scheduler import assign_workers  # noqa: E402


def test_sonnet_preferred_matches_anthropic_sonnet_alias_before_glm():
    result = assign_workers(
        [
            {
                "id": "N3",
                "preferred_model": "sonnet",
                "required_skills": ["python"],
                "required_capabilities": ["python"],
            }
        ],
        [
            {"pane": "solar-harness-lab:0.2", "models": ["glm", "glm-5.1"], "skills": ["python"], "capabilities": ["python"]},
            {"pane": "solar-harness-lab:0.3", "models": ["anthropic-sonnet", "claude-sonnet"], "skills": ["python"], "capabilities": ["python"]},
        ],
    )

    assert result["assigned"][0]["pane"] == "solar-harness-lab:0.3"
    assert result["assigned"][0]["fallback_model"] is False


def test_opus_preferred_matches_claude_opus_alias():
    result = assign_workers(
        [
            {
                "id": "N",
                "preferred_model": "opus",
                "required_skills": ["testing"],
                "required_capabilities": ["testing"],
            }
        ],
        [
            {"pane": "builder", "models": ["claude-opus-4.7"], "skills": ["testing"], "capabilities": ["testing"]},
        ],
    )

    assert result["assigned"][0]["pane"] == "builder"
    assert result["assigned"][0]["fallback_model"] is False


def test_anthropic_quota_exhausted_worker_is_skipped_without_preferred_model():
    result = assign_workers(
        [
            {
                "id": "N1",
                "required_skills": ["bash"],
                "required_capabilities": ["bash"],
            }
        ],
        [
            {
                "pane": "anthropic-pane",
                "models": ["claude-opus"],
                "skills": ["bash"],
                "capabilities": ["bash"],
                "quota_exhausted": ["anthropic"],
            },
            {
                "pane": "glm-pane",
                "models": ["glm-5.1"],
                "skills": ["bash"],
                "capabilities": ["bash"],
            },
        ],
    )

    assert result["assigned"][0]["pane"] == "glm-pane"
    assert result["queued"] == []


def test_anthropic_quota_exhausted_alias_blocks_preferred_sonnet():
    result = assign_workers(
        [
            {
                "id": "N2",
                "preferred_model": "sonnet",
                "required_skills": ["bash"],
                "required_capabilities": ["bash"],
            }
        ],
        [
            {
                "pane": "anthropic-pane",
                "models": ["claude-sonnet"],
                "skills": ["bash"],
                "capabilities": ["bash"],
                "quota_exhausted": ["anthropic"],
            },
            {
                "pane": "deepseek-pane",
                "models": ["deepseek-v4-pro"],
                "skills": ["bash"],
                "capabilities": ["bash"],
            },
        ],
    )

    assert result["assigned"][0]["pane"] == "deepseek-pane"
    assert result["assigned"][0]["fallback_model"] is True
