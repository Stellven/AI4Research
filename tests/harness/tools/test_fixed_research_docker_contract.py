from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "harness"
DOCKERFILE = HARNESS / "docker/Dockerfile.fixed-research-uat"
ENTRYPOINT = HARNESS / "docker/fixed-research-uat-entry.sh"


def test_fixed_research_uat_image_is_nonroot_and_contains_no_baked_auth() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "USER solar" in dockerfile
    assert dockerfile.index("USER solar") < dockerfile.index("git init --quiet")
    assert "usermod --login solar" in dockerfile
    assert "useradd --create-home --uid 1000 solar" not in dockerfile
    assert "COPY --chown=solar:solar . /opt/solar/harness" in dockerfile
    assert "ENTRYPOINT" in dockerfile
    assert ".credentials.json" not in dockerfile
    assert "API_KEY" not in dockerfile
    assert "python3-jsonschema" in dockerfile
    assert "python3-requests" in dockerfile
    assert "python3-yaml" in dockerfile
    assert "util-linux" in dockerfile
    assert "SOLAR_BIND_HOST=0.0.0.0" in dockerfile
    assert "SOLAR_STATUS_PORT_START=8765" in dockerfile


def test_fixed_research_uat_entry_uses_readonly_auth_input_and_real_product_surfaces() -> None:
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert ENTRYPOINT.stat().st_mode & 0o111
    assert '"/run/claude-auth/$name"' in entrypoint
    assert "status-server.py" in entrypoint
    assert "fixed_research_uat.py" in entrypoint
    assert "SOLAR_OPERATORD_AUTO_KICK" in entrypoint
    assert "secrets.token_urlsafe(32)" in entrypoint
    assert "SOLAR_AUTH_TOKEN" in entrypoint
    assert "SKIP_LLM" not in entrypoint
    assert "FAKE_KEYS" not in entrypoint
