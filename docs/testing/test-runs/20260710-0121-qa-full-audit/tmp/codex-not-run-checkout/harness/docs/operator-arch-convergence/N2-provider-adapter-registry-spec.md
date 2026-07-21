# N2: Provider Adapter Registry Spec

> Sprint: `sprint-20260527-operator-architecture-convergence`
> Node: N2 | Gate: G_PLAN
> Status: spec_only (no code changes)
> Evidence Policy: no_code=true, no_lib_modification=read-only

---

## 1. Purpose

Today, `config/model-registry.json` stores provider metadata (label, model_flag, aliases) but has no adapter-level abstraction for auth resolution, quota checking, error classification, or command building. Adding a new provider (e.g., Mistral, Cohere) requires editing the registry JSON plus finding and patching every call site that handles auth headers, rate-limit responses, or CLI flag construction.

This spec defines a **4-dimension adapter shape** and a **Provider Adapter Registry** that encapsulates all provider-specific behavior behind a uniform interface. New providers register once; all downstream code calls through the registry.

---

## 2. 4-Dimension Adapter Shape

Every provider adapter must implement exactly these four dimensions:

```python
class ProviderAdapter(Protocol):
    provider_id: str  # e.g. "anthropic", "zhipu", "deepseek"

    def auth_resolve(self, context: AuthContext) -> AuthResult:
        """Resolve authentication credentials for this provider.

        Dimensions checked: env var, config file, vault, API key rotation.
        Must not hardcode tokens or paths.
        """

    def quota_check(self, context: QuotaContext) -> QuotaResult:
        """Check if the provider has remaining quota for the request.

        Covers: token budget, RPM/TPM limits, concurrent request slots.
        Returns pass/fail + remaining capacity metadata.
        """

    def error_classify(self, error: ProviderError) -> ErrorClassification:
        """Classify a provider-specific error into the 7-class taxonomy.

        Maps HTTP status codes, provider-specific error strings, and
        exception types to the unified error taxonomy.
        """

    def command_build(self, context: CommandContext) -> CommandResult:
        """Build the CLI invocation for this provider.

        Constructs model_flag, base_url, auth headers, and any
        provider-specific CLI arguments.
        """
```

### 2.1 Data Types

```python
@dataclass
class AuthContext:
    provider_id: str
    pane_id: str | None
    model_key: str
    required_scopes: list[str]  # e.g. ["inference"], ["inference", "fine-tune"]

@dataclass
class AuthResult:
    resolved: bool
    auth_type: str          # "api_key" | "oauth" | "vault" | "env_var" | "none"
    auth_value: str         # masked in logs (first 4 chars + "***")
    source: str             # "env:ANTHROPIC_API_KEY" | "config" | "vault"
    expires_at: str | None  # for OAuth/rotating keys

@dataclass
class QuotaContext:
    provider_id: str
    model_key: str
    request_type: str       # "inference" | "embedding" | "fine-tune"
    estimated_tokens: int

@dataclass
class QuotaResult:
    allowed: bool
    remaining_rpm: int | None
    remaining_tpm: int | None
    remaining_budget: float | None
    retry_after: str | None  # ISO timestamp when quota resets

@dataclass
class ProviderError:
    provider_id: str
    http_status: int | None
    error_code: str          # provider-specific code
    error_message: str
    exception_type: str      # e.g. "RateLimitError", "ConnectionError"

@dataclass
class ErrorClassification:
    error_class: str         # one of 7 taxonomy classes
    severity: str            # "transient" | "permanent" | "critical"
    retry_eligible: bool
    retry_after: float       # seconds, 0 = immediate
    escalation_path: str     # "backoff" | "fallback_provider" | "notify_operator" | "halt"

@dataclass
class CommandContext:
    provider_id: str
    model_key: str
    model_flag: str          # base flag from registry
    base_url: str | None
    extra_args: dict[str, str]

@dataclass
class CommandResult:
    command: list[str]       # full CLI invocation
    env_overrides: dict[str, str]  # env vars to set
    working_dir: str | None
```

### 2.2 Dimension Semantics

| Dimension | Responsibility | Must Not |
|-----------|---------------|----------|
| `auth_resolve` | Find and validate credentials; support rotation | Hardcode tokens; read from world-readable files |
| `quota_check` | Check RPM/TPM/budget before dispatch | Block on network calls (must use cached state) |
| `error_classify` | Map provider errors to 7-class taxonomy | Swallow errors; return `unknown` without logging |
| `command_build` | Assemble CLI invocation with provider-specific flags | Hardcode base URLs; duplicate model_flag logic |

---

## 3. Registry API

### 3.1 Methods

```python
class ProviderAdapterRegistry:
    def register(self, adapter: ProviderAdapter) -> None:
        """Register a provider adapter. Raises on duplicate provider_id."""

    def get(self, provider_id: str) -> ProviderAdapter:
        """Retrieve adapter by provider_id. Raises KeyError if not found."""

    def hot_reload(self, config_path: str) -> ReloadResult:
        """Reload adapters from config without restarting.

        Compares checksum of config_path with last loaded version.
        If changed, rebuilds adapter instances and swaps atomically.
        If unchanged, returns no-op result.
        """
```

### 3.2 Data Types

```python
@dataclass
class ReloadResult:
    reloaded: bool
    providers_added: list[str]
    providers_removed: list[str]
    providers_updated: list[str]
    checksum_before: str
    checksum_after: str
    errors: list[str]
```

### 3.3 Lifecycle

```
Startup → load from config/model-registry.json + config/provider-adapters.yaml
         → register all adapters
Runtime → get(provider_id) for each dispatch
         → hot_reload(config_path) on SIGHUP or config change detection
Shutdown → no special cleanup (adapters are stateless)
```

### 3.4 Registration Contract

- `register()` must validate that the adapter implements all 4 dimensions.
- Duplicate `provider_id` raises `DuplicateProviderError`.
- Adapter must be stateless (no mutable class-level state); all context via arguments.
- Registry is thread-safe for reads; writes only during `hot_reload`.

---

## 4. Provider Example Specs

### 4.1 Anthropic

```yaml
provider_id: anthropic
adapter_class: AnthropicAdapter
dimensions:
  auth_resolve:
    strategy: env_var
    env_key: ANTHROPIC_API_KEY
    fallback: config:anthropic.api_key
    auth_type: api_key
    header: x-api-key
    rotation: none
  quota_check:
    strategy: cached_headers
    # Anthropic returns rate limit headers: x-ratelimit-limit,
    # x-ratelimit-remaining, x-ratelimit-reset
    cache_ttl_seconds: 60
    rpm_limit: null  # plan-dependent, read from headers
    tpm_limit: null
    budget_limit: null
  error_classify:
    mappings:
      - http_status: 429
        error_class: rate_limit
        severity: transient
        retry_eligible: true
        retry_after: from_header("retry-after", default=60)
      - http_status: 401
        error_class: auth_fail
        severity: permanent
        retry_eligible: false
      - http_status: 403
        error_class: quota_exhaust
        severity: permanent
        retry_eligible: false
      - http_status: 500
        error_class: model_unavail
        severity: transient
        retry_eligible: true
      - http_status: 503
        error_class: model_unavail
        severity: transient
        retry_eligible: true
      - exception: ConnectionError
        error_class: network
        severity: transient
        retry_eligible: true
    default: unknown
  command_build:
    base_url: https://api.anthropic.com
    model_flag_template: "--model {model_key}"
    extra_args:
      - key: anthropic-version
        value: "2023-06-01"
    env_overrides:
      ANTHROPIC_API_KEY: from_auth_resolve
```

### 4.2 GLM (Zhipu)

```yaml
provider_id: zhipu
adapter_class: ZhipuAdapter
dimensions:
  auth_resolve:
    strategy: env_var
    env_key: ZHIPU_API_KEY
    fallback: config:zhipu.api_key
    auth_type: api_key
    header: Authorization
    header_template: "Bearer {api_key}"
    rotation: none
  quota_check:
    strategy: cached_headers
    cache_ttl_seconds: 60
    rpm_limit: null
    tpm_limit: null
    budget_limit: null
  error_classify:
    mappings:
      - http_status: 429
        error_class: rate_limit
        severity: transient
        retry_eligible: true
        retry_after: 30
      - http_status: 401
        error_class: auth_fail
        severity: permanent
        retry_eligible: false
      - http_status: 402
        error_class: quota_exhaust
        severity: permanent
        retry_eligible: false
      - http_status: 500
        error_class: model_unavail
        severity: transient
        retry_eligible: true
      - exception: ConnectionError
        error_class: network
        severity: transient
        retry_eligible: true
    default: unknown
  command_build:
    base_url: https://open.bigmodel.cn/api/paas
    model_flag_template: "--model {model_key}"
    extra_args: []
    env_overrides:
      ZHIPU_API_KEY: from_auth_resolve
```

### 4.3 OpenAI-Compatible (DeepSeek, Local, Generic)

```yaml
provider_id: openai_compat
adapter_class: OpenAICompatAdapter
applies_to: [deepseek, local, any-openai-api]
dimensions:
  auth_resolve:
    strategy: env_var
    env_key: OPENAI_API_KEY
    fallback: config:openai_compat.api_key
    auth_type: api_key
    header: Authorization
    header_template: "Bearer {api_key}"
    rotation: none
    notes: |
      For local providers, auth may be "none" (no key needed).
      The adapter must handle both cases.
  quota_check:
    strategy: cached_headers
    cache_ttl_seconds: 60
    rpm_limit: null
    tpm_limit: null
    budget_limit: null
    notes: |
      OpenAI-compatible endpoints return standard rate limit headers.
      Local providers may have no limits → quota_check returns allowed=true always.
  error_classify:
    mappings:
      - http_status: 429
        error_class: rate_limit
        severity: transient
        retry_eligible: true
        retry_after: from_header("retry-after", default=30)
      - http_status: 401
        error_class: auth_fail
        severity: permanent
        retry_eligible: false
      - http_status: 402
        error_class: quota_exhaust
        severity: permanent
        retry_eligible: false
      - http_status: 500
        error_class: model_unavail
        severity: transient
        retry_eligible: true
      - http_status: 502
        error_class: model_unavail
        severity: transient
        retry_eligible: true
      - http_status: 503
        error_class: model_unavail
        severity: transient
        retry_eligible: true
      - error_code: context_length_exceeded
        error_class: context_overflow
        severity: permanent
        retry_eligible: false
      - exception: ConnectionError
        error_class: network
        severity: transient
        retry_eligible: true
    default: unknown
  command_build:
    base_url: from_config  # varies by provider: api.deepseek.com, localhost:8000
    model_flag_template: "--model {model_key}"
    extra_args:
      - key: openai-base-url
        value: from_config
    env_overrides:
      OPENAI_API_KEY: from_auth_resolve
      OPENAI_BASE_URL: from_config
```

---

## 5. 7-Class Error Taxonomy

All provider errors must be classified into exactly one of these 7 classes:

| # | Class | Severity | Retry | Meaning |
|---|-------|----------|-------|---------|
| 1 | `rate_limit` | transient | yes | Provider throttled the request (HTTP 429 or equivalent) |
| 2 | `auth_fail` | permanent | no | Authentication failed (invalid/expired key, 401) |
| 3 | `quota_exhaust` | permanent | no | Account quota or budget exhausted (402, 403) |
| 4 | `model_unavail` | transient | yes | Model temporarily unavailable (500, 502, 503) |
| 5 | `context_overflow` | permanent | no | Request exceeds model context window |
| 6 | `network` | transient | yes | Connection failed, DNS, timeout, TLS |
| 7 | `unknown` | critical | no | Unclassified error; requires human investigation |

### 5.1 Classification Rules

1. **Priority**: HTTP status → error_code string → exception_type → default to `unknown`.
2. **severity=transient**: eligible for automatic retry with exponential backoff.
3. **severity=permanent**: no retry; escalate to fallback provider or notify operator.
4. **severity=critical**: `unknown` class; log full error context, notify operator, do not retry.
5. **retry_after**: sourced from `Retry-After` header when available; otherwise provider-specific default.

### 5.2 Escalation Matrix

| Class | First Response | If Persists |
|-------|---------------|-------------|
| `rate_limit` | Backoff + retry | Switch to fallback provider |
| `auth_fail` | Halt + notify operator | No automatic recovery |
| `quota_exhaust` | Switch to fallback provider | Notify operator |
| `model_unavail` | Backoff + retry | Switch to fallback provider |
| `context_overflow` | Truncate input + retry once | Halt + notify |
| `network` | Backoff + retry | Halt after 3 failures |
| `unknown` | Halt + notify + log full context | No automatic recovery |

---

## 6. New-Provider Onboarding Checklist

Adding a new provider to the registry requires exactly these steps:

| # | Step | Verification |
|---|------|-------------|
| 1 | Create adapter YAML in `config/provider-adapters.d/{provider_id}.yaml` with all 4 dimensions | `registry validate --file {provider_id}.yaml` passes |
| 2 | Map all provider-specific error codes/HTTP statuses to the 7-class taxonomy | Grep for unmapped errors: `registry audit-errors --provider {provider_id}` returns 0 unknowns |
| 3 | Add `provider` field to model entries in `config/model-registry.json` | `registry check --provider {provider_id}` finds all models |
| 4 | Implement `auth_resolve` with env var + config fallback (no hardcoded keys) | `registry test-auth --provider {provider_id}` resolves without error |
| 5 | Implement `quota_check` with cached-headers strategy | `registry test-quota --provider {provider_id}` returns structured result |
| 6 | Implement `command_build` producing correct CLI invocation | Dry-run: `registry dry-run --provider {provider_id} --model {model_key}` matches expected command |
| 7 | Register hot-reload: add file path to `config/provider-adapters.yaml` includes list | `registry hot-reload --dry-run` detects the new provider |

---

## 7. Configuration Schema

```yaml
# config/provider-adapters.yaml
version: 1
includes:
  - provider-adapters.d/*.yaml

defaults:
  auth_resolve:
    strategy: env_var
    rotation: none
  quota_check:
    strategy: cached_headers
    cache_ttl_seconds: 60
  error_classify:
    default_class: unknown
    default_severity: critical
    default_retry_eligible: false
  command_build:
    model_flag_template: "--model {model_key}"
```

Each provider's YAML in `provider-adapters.d/` overrides defaults as shown in §4.

---

## 8. Acceptance Mapping

| Acceptance ID | Criterion | Spec Section |
|---------------|-----------|-------------|
| A-N2-1 | Adapter shape covers 4 dimensions (auth/quota/error/command) | §2 (ProviderAdapter protocol with 4 methods), §2.2 (dimension semantics table) |
| A-N2-2 | Registry API defines 3 methods (register/get/hot-reload mapping) | §3.1 (3 methods), §3.2 (data types), §3.3 (lifecycle), §3.4 (registration contract) |
| A-N2-3 | >=3 provider example specs are complete (anthropic + glm + openai-compat) | §4.1 (Anthropic), §4.2 (Zhipu/GLM), §4.3 (OpenAI-Compatible covering deepseek + local + generic) |
| A-N2-4 | Error taxonomy locked to 7 classes | §5 (7-class table + classification rules + escalation matrix) |
| A-N2-5 | New-provider onboarding checklist <=7 steps | §6 (exactly 7 steps with verification commands) |
