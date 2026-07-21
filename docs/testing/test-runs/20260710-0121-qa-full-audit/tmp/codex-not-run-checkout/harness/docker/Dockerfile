# ============================================================================
# Solar Product Platform — Docker validation image
#
# Purpose: Clean container install validation (G2 gate).
#          No secrets baked in. No live user paths.
#
# Build:   docker build -t solar-harness-test -f docker/Dockerfile .
# Run:     docker run --rm -e SKIP_LLM_CLI=1 solar-harness-test
# ============================================================================
FROM ubuntu:24.04

LABEL org.solar.product="solar-harness"
LABEL org.solar.version="0.1.0"
LABEL org.solar.gate="G2"

# ── system deps ───────────────────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      bash \
      python3 \
      python3-venv \
      python3-pip \
      tmux \
      git \
      jq \
      sqlite3 \
      curl \
      ca-certificates \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── non-root user ─────────────────────────────────────────────────────────
RUN useradd -m solar && \
    mkdir -p /opt/solar /home/solar/Knowledge && \
    chown -R solar:solar /opt/solar /home/solar/Knowledge

USER solar
WORKDIR /home/solar

# ── environment (no real secrets, no hardcoded keys) ──────────────────────
ENV SOLAR_HOME=/opt/solar
ENV HARNESS_DIR=/opt/solar/harness
ENV KNOWLEDGE_VAULT=/home/solar/Knowledge
ENV SKIP_LLM_CLI=1
ENV FAKE_KEYS=1
ENV HOME=/home/solar

# ── copy harness source ───────────────────────────────────────────────────
# COPY is done at build time; real secrets must NEVER be in the source tree.
# gitleaks.toml + pre-commit hook gate this.
COPY --chown=solar:solar . /opt/solar/harness

# ── entrypoint ────────────────────────────────────────────────────────────
# Default: run installer then smoke test
ENTRYPOINT ["/opt/solar/harness/docker/smoke-test.sh"]
