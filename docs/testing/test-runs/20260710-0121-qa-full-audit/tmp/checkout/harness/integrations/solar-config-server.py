#!/usr/bin/env python3
"""
Solar Config Server

Local-only setup/config UI for Solar Harness. It stores non-secret user config in
~/.solar/harness/config/solar-user-config.json and secrets in
~/.solar/secrets/solar-user-secrets.env. Secrets are never returned unmasked.

No external dependencies. Binds to 127.0.0.1 only.
"""

from __future__ import annotations

import html
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(HOME / ".solar" / "harness")))
sys.path.insert(0, str(HARNESS_DIR / "lib"))
from qmd_resolver import resolve_qmd_bin  # noqa: E402

CONFIG_PATH = HARNESS_DIR / "config" / "solar-user-config.json"
MODEL_REGISTRY_PATH = HARNESS_DIR / "config" / "model-registry.json"
KNOWLEDGE_PROBE_HEALTH = HARNESS_DIR / "state" / "knowledge-probe-health.json"
MODEL_DOCTOR_HEALTH = HARNESS_DIR / "state" / "model-registry-doctor-health.json"
SECRETS_PATH = HOME / ".solar" / "secrets" / "solar-user-secrets.env"
PID_FILE = HARNESS_DIR / ".solar-config-server.pid"
PORT_FILE = HARNESS_DIR / ".solar-config-server.port"
LOG_FILE = HARNESS_DIR / ".solar-config-server.log"
DEFAULT_PORT = int(os.environ.get("SOLAR_CONFIG_PORT", "8789"))
BIND_HOST = "127.0.0.1"

SECRET_KEYS = {
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "ZHIPU_AUTH_TOKEN",
    "ZHIPU_API_KEY",
    "DEEPSEEK_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
}

DEFAULT_CONFIG = {
    "version": 1,
    "updated_at": "",
    "setup_complete": False,
    "user": {
        "display_name": "",
        "timezone": "America/Toronto",
    },
    "paths": {
        "knowledge_vault": str(HOME / "Knowledge"),
        "raw_dir": str(HOME / "Knowledge" / "_raw"),
        "harness_dir": str(HARNESS_DIR),
    },
    "models": {
        "pm": "opus",
        "planner": "opus",
        "builder": "opus",
        "evaluator": "opus",
        "lab_builder_matrix": "glm,glm,glm,anthropic-sonnet",
    },
    "providers": {
        "zhipu_base_url": "https://api.z.ai/api/anthropic",
        "deepseek_base_url": "https://api.deepseek.com/anthropic",
        "prefer_zhipu": True,
    },
    "wiki": {
        "qmd_collection": "solar-wiki",
        "auto_ingest_enabled": True,
        "capture_server_port": 8788,
    },
    "mirage": {
        "enabled": True,
        "workspace_id": "solar-default",
        "config_path": str(HARNESS_DIR / "config" / "mirage.solar.yaml"),
    },
    "apple_notes": {
        "enabled": False,
        "folder": "Solar Inbox",
        "interval_seconds": 7200,
    },
    "ui": {
        "open_on_first_run": True,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_model_registry() -> dict:
    try:
        return json.loads(MODEL_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "defaults": {"main_model": "opus", "lab_builder_matrix": "glm,glm,glm,anthropic-sonnet"},
            "models": {},
            "matrix_options": [],
        }


def model_registry_options() -> dict[str, object]:
    reg = load_model_registry()
    model_options = []
    for model_id, spec in (reg.get("models") or {}).items():
        if not spec.get("main_allowed"):
            continue
        aliases = spec.get("aliases") or []
        model_options.append({
            "value": aliases[0] if aliases else model_id,
            "id": model_id,
            "label": spec.get("label") or model_id,
        })
    return {
        "model_options": model_options or [
            {"value": "opus", "id": "claude-opus", "label": "Claude Opus 4.7"},
            {"value": "anthropic-sonnet", "id": "claude-sonnet", "label": "Claude Sonnet"},
        ],
        "matrix_options": reg.get("matrix_options") or [
            {"value": "glm,glm,glm,anthropic-sonnet", "label": "3× GLM 5.1 + Claude Sonnet"},
        ],
    }


def deep_merge(base: dict, override: dict) -> dict:
    out = json.loads(json.dumps(base))
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return deep_merge(DEFAULT_CONFIG, json.loads(CONFIG_PATH.read_text()))
        except Exception:
            pass
    return deep_merge(DEFAULT_CONFIG, {})


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config["updated_at"] = utc_now()
    # Backup before write
    if CONFIG_PATH.exists():
        backup = CONFIG_PATH.with_suffix(".bak")
        try:
            import shutil as _shutil
            _shutil.copy2(CONFIG_PATH, backup)
        except OSError:
            pass
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(CONFIG_PATH)


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(errors="ignore").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        if raw.startswith("export "):
            raw = raw[len("export ") :].strip()
        key, value = raw.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def save_secrets(updates: dict[str, str]) -> None:
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = parse_env_file(SECRETS_PATH)
    for key, value in updates.items():
        if key not in SECRET_KEYS:
            continue
        value = str(value or "").strip()
        if value:
            existing[key] = value
    lines = [
        "# Solar user secrets. Managed by solar-config-server.py",
        "# Do not commit this file.",
    ]
    for key in sorted(existing):
        lines.append(f"export {key}={shell_quote(existing[key])}")
    tmp = SECRETS_PATH.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(SECRETS_PATH)
    os.chmod(SECRETS_PATH, stat.S_IRUSR | stat.S_IWUSR)


def masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + value[-4:]


def load_masked_secrets() -> dict[str, dict[str, object]]:
    env_file = parse_env_file(SECRETS_PATH)
    out: dict[str, dict[str, object]] = {}
    for key in sorted(SECRET_KEYS):
        value = env_file.get(key) or os.environ.get(key, "")
        out[key] = {
            "configured": bool(value),
            "masked": masked(value),
            "source": "file" if key in env_file else ("env" if value else "missing"),
        }
    return out


def run_cmd(args: list[str], timeout: int = 5) -> dict[str, object]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-2000:],
        }
    except Exception as exc:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}


def _mirage_detail(doctor_result: dict) -> dict:
    """Extract structured mirage fields from doctor --json output."""
    if not doctor_result.get("ok"):
        return {"ok": False, "detail": str(doctor_result.get("stderr") or "")[:300]}
    try:
        d = json.loads(str(doctor_result.get("stdout") or ""))
        drive = d.get("drive") or {}
        qmd = d.get("qmd") or {}
        mounts = d.get("mounts") or []
        qmd_detail = qmd.get("detail") if isinstance(qmd, dict) and isinstance(qmd.get("detail"), dict) else {}

        def mount_item(m: dict) -> dict:
            status = m.get("status")
            ready = m.get("ready")
            if ready is None:
                ready = status == "ok"
            return {
                "path": m.get("path"),
                "mode": m.get("mode") or m.get("type"),
                "ready": bool(ready),
                "status": status or ("ok" if ready else "error"),
                "physical_root": m.get("physical_root", ""),
                "reason": m.get("reason", ""),
            }

        def count_from(text: object) -> int:
            m = re.search(r"(\d+)", str(text or ""))
            return int(m.group(1)) if m else 0

        return {
            "ok": True,
            "enabled": d.get("enabled", False),
            "workspace_id": d.get("workspace_id", ""),
            "mounts": [mount_item(m) for m in mounts if isinstance(m, dict)],
            "drive_status": drive.get("status", "unknown") if isinstance(drive, dict) else "unknown",
            "drive_ro": drive.get("mode", "ro") == "ro" if isinstance(drive, dict) else True,
            "drive_root": drive.get("local_root", "") if isinstance(drive, dict) else "",
            "qmd_status": qmd.get("status", "unknown") if isinstance(qmd, dict) else "unknown",
            "qmd_indexed": qmd.get("indexed", 0) if isinstance(qmd, dict) and qmd.get("indexed") is not None else count_from(qmd_detail.get("total")),
            "qmd_vectors": count_from(qmd_detail.get("vectors")),
            "qmd_pending": count_from(qmd_detail.get("pending")),
            "last_probe_at": d.get("probed_at"),
            "stale": False,
            "credential_configured": bool(drive.get("credentials_path") or drive.get("token_path") or drive.get("local_root")) if isinstance(drive, dict) else False,
        }
    except (json.JSONDecodeError, Exception):
        return {"ok": True, "detail": str(doctor_result.get("stdout") or "")[:300]}


def health_file_summary(path: Path) -> dict[str, object]:
    d = {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "status": "missing", "path": str(path)}
    return {
        "ok": bool(d.get("ok")),
        "status": d.get("status", "unknown"),
        "checked_at": d.get("checked_at", ""),
        "probes_passed": d.get("probes_passed"),
        "probes_failed": d.get("probes_failed"),
        "path": str(path),
    }


def system_status() -> dict[str, object]:
    cfg = load_config()
    qmd_bin = resolve_qmd_bin()
    qmd = run_cmd([qmd_bin, "status"], timeout=8) if qmd_bin else {"ok": False, "stderr": "qmd not found"}
    wiki = run_cmd([str(HARNESS_DIR / "solar-harness.sh"), "wiki", "status", "--json"], timeout=8)
    mirage = run_cmd([str(HARNESS_DIR / "solar-harness.sh"), "mirage", "doctor", "--json"], timeout=8)
    status_server = run_cmd(["/usr/bin/curl", "-fsS", "--max-time", "3", "http://127.0.0.1:8765/healthz"], timeout=5)
    return {
        "config_path": str(CONFIG_PATH),
        "secrets_path": str(SECRETS_PATH),
        "config": cfg,
        "model_registry": model_registry_options(),
        "secrets": load_masked_secrets(),
        "checks": {
            "wiki": summarize_json_cmd(wiki),
            "qmd": summarize_text_cmd(qmd, ["Total:", "Vectors:", "Pending:", "solar-wiki"]),
            "mirage": _mirage_detail(mirage),
            "knowledge_probe": health_file_summary(KNOWLEDGE_PROBE_HEALTH),
            "model_doctor": health_file_summary(MODEL_DOCTOR_HEALTH),
            "status_server": {"ok": bool(status_server.get("ok")), "detail": str(status_server.get("stdout") or status_server.get("stderr", ""))[:300]},
        },
    }


def summarize_json_cmd(result: dict[str, object]) -> dict[str, object]:
    text = str(result.get("stdout") or "")
    if result.get("ok"):
        try:
            return {"ok": True, "json": json.loads(text)}
        except Exception:
            return {"ok": True, "detail": text[:500]}
    return {"ok": False, "detail": str(result.get("stderr") or text)[:500]}


def summarize_text_cmd(result: dict[str, object], patterns: list[str]) -> dict[str, object]:
    text = str(result.get("stdout") or result.get("stderr") or "")
    lines = []
    for line in text.splitlines():
        if any(p in line for p in patterns):
            lines.append(line.strip())
    return {"ok": bool(result.get("ok")), "detail": lines[:12] or text.splitlines()[:8]}


HTML = r"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Solar Setup</title>
  <style>
    :root {
      --bg:#f4efe5; --ink:#15120d; --muted:#716958; --card:#fffdf7;
      --line:#ded2bd; --accent:#215f63; --accent2:#b85c38; --ok:#27734d;
      --warn:#a16412; --err:#a3332a; --shadow:0 18px 45px rgba(37,30,15,.12);
    }
    * { box-sizing:border-box; }
    body {
      margin:0; color:var(--ink);
      font-family: ui-serif, Georgia, "Songti SC", "STSong", serif;
      background:
        radial-gradient(circle at 15% 10%, rgba(184,92,56,.18), transparent 24rem),
        radial-gradient(circle at 80% 0%, rgba(33,95,99,.17), transparent 26rem),
        linear-gradient(135deg, #faf6ec 0%, var(--bg) 100%);
    }
    header { padding:42px clamp(20px,4vw,56px) 18px; }
    h1 { margin:0; font-size:clamp(34px,5vw,64px); line-height:.95; letter-spacing:-.04em; }
    .sub { max-width:840px; color:var(--muted); font-size:18px; margin-top:18px; }
    main { padding:20px clamp(20px,4vw,56px) 56px; display:grid; gap:20px; grid-template-columns:1.1fr .9fr; }
    @media (max-width: 920px) { main { grid-template-columns:1fr; } }
    .card { background:rgba(255,253,247,.88); border:1px solid var(--line); border-radius:24px; padding:22px; box-shadow:var(--shadow); backdrop-filter: blur(10px); }
    .card h2 { margin:0 0 14px; font-size:24px; }
    .grid { display:grid; gap:14px; grid-template-columns:repeat(2,minmax(0,1fr)); }
    @media (max-width: 620px) { .grid { grid-template-columns:1fr; } }
    label { display:block; font-size:13px; color:var(--muted); margin-bottom:6px; }
    input, select {
      width:100%; border:1px solid #d7c8ae; background:#fffaf0; color:var(--ink);
      border-radius:12px; padding:11px 12px; font:15px ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    input[type="checkbox"] { width:auto; transform:scale(1.15); margin-right:8px; }
    .row { margin:12px 0; }
    .actions { display:flex; gap:12px; flex-wrap:wrap; margin-top:18px; }
    button {
      border:0; border-radius:999px; padding:12px 18px; cursor:pointer;
      background:var(--accent); color:white; font-weight:700; box-shadow:0 10px 20px rgba(33,95,99,.2);
    }
    button.secondary { background:#352f25; }
    button.ghost { background:transparent; color:var(--accent); border:1px solid var(--accent); box-shadow:none; }
    button:disabled { opacity:.62; cursor:not-allowed; transform:none; }
    .notice { margin-top:12px; padding:12px 14px; border-radius:16px; border:1px solid var(--line); background:#fff9ec; font-weight:800; display:none; }
    .notice.ok { display:block; color:var(--ok); border-color:rgba(39,115,77,.35); background:rgba(39,115,77,.08); }
    .notice.warn { display:block; color:var(--warn); border-color:rgba(161,100,18,.35); background:rgba(161,100,18,.08); }
    .notice.err { display:block; color:var(--err); border-color:rgba(163,51,42,.35); background:rgba(163,51,42,.08); }
    .status { display:grid; gap:10px; }
    .pill { display:flex; justify-content:space-between; gap:12px; padding:12px 14px; border-radius:16px; border:1px solid var(--line); background:#fff9ec; }
    .ok { color:var(--ok); font-weight:800; } .warn { color:var(--warn); font-weight:800; } .err { color:var(--err); font-weight:800; }
    pre { white-space:pre-wrap; word-break:break-word; background:#211b14; color:#f7ead2; border-radius:16px; padding:14px; max-height:300px; overflow:auto; }
    .secret { display:grid; grid-template-columns:1fr 1.2fr; gap:10px; align-items:end; }
    @media (max-width: 620px) { .secret { grid-template-columns:1fr; } }
    .hint { color:var(--muted); font-size:13px; }
  </style>
</head>
<body>
  <header>
    <h1>Solar Setup<br>统一配置面板</h1>
    <p class="sub">集中配置模型、Key、知识库路径、QMD、Mirage、Apple Notes 和自动化入口。服务只监听 127.0.0.1；敏感 Key 只保存到本机 secrets 文件，页面不回显明文。</p>
  </header>
  <main>
    <section class="card">
      <h2>基础配置</h2>
      <form id="cfg">
        <div class="grid">
          <div><label>显示名称</label><input name="user.display_name"></div>
          <div><label>时区</label><input name="user.timezone"></div>
          <div><label>Knowledge Vault</label><input name="paths.knowledge_vault"></div>
          <div><label>Raw Dir</label><input name="paths.raw_dir"></div>
          <div><label>Planner 模型</label><select name="models.planner" data-model-select="single"></select></div>
          <div><label>Builder 模型</label><select name="models.builder" data-model-select="single"></select></div>
          <div><label>Evaluator 模型</label><select name="models.evaluator" data-model-select="single"></select></div>
          <div><label>Lab Builder Matrix</label><select name="models.lab_builder_matrix" data-model-select="matrix"></select></div>
          <div><label>QMD Collection</label><input name="wiki.qmd_collection"></div>
          <div><label>Mirage Workspace</label><input name="mirage.workspace_id"></div>
          <div><label>Apple Notes Folder</label><input name="apple_notes.folder"></div>
          <div><label>Notes Interval Seconds</label><input name="apple_notes.interval_seconds" type="number"></div>
        </div>
        <div class="row">
          <label><input name="providers.prefer_zhipu" type="checkbox"> 优先使用 Zhipu/GLM（不可用时回退）</label>
          <label><input name="wiki.auto_ingest_enabled" type="checkbox"> Wiki 自动 ingest</label>
          <label><input name="mirage.enabled" type="checkbox"> 启用 Mirage 统一数据底座</label>
          <label><input name="apple_notes.enabled" type="checkbox"> 启用 Apple Notes 扫描</label>
          <label><input name="setup_complete" type="checkbox"> 标记初始配置完成</label>
        </div>
        <h2>Key / 凭证</h2>
        <p class="hint">留空表示不修改已有值。Google 凭证填本机 JSON 路径，不上传文件。</p>
        <div id="secrets" class="status"></div>
        <div class="actions">
          <button id="saveBtn" type="button" onclick="save()">保存配置</button>
          <button type="button" class="secondary" onclick="refresh()">刷新状态</button>
          <button type="button" class="ghost" onclick="openStatus()">打开 Solar Status</button>
        </div>
        <div id="saveNotice" class="notice"></div>
      </form>
    </section>
    <aside class="card">
      <h2>系统状态</h2>
      <div id="status" class="status"></div>
      <h2 style="margin-top:20px">原始检查</h2>
      <pre id="raw">Loading...</pre>
    </aside>
  </main>
  <script>
    let current = {};
    const secretKeys = ["ANTHROPIC_API_KEY","OPENAI_API_KEY","ZHIPU_AUTH_TOKEN","DEEPSEEK_API_KEY","GOOGLE_APPLICATION_CREDENTIALS"];
    let modelOptions = [["opus", "Claude Opus 4.7"], ["anthropic-sonnet", "Claude Sonnet"], ["glm", "GLM-5.1"]];
    let matrixOptions = [["glm,glm,glm,anthropic-sonnet", "3× GLM 5.1 + Claude Sonnet"]];
    function get(obj, path) { return path.split('.').reduce((o,k)=>o&&o[k], obj); }
    function set(obj, path, value) { const parts=path.split('.'); let o=obj; parts.slice(0,-1).forEach(k=>o=o[k]||(o[k]={})); o[parts.at(-1)]=value; }
    function renderSelectOptions(el, options, value) {
      const has = options.some(([v]) => v === value);
      const all = has || !value ? options : [[value, `当前自定义：${value}`], ...options];
      el.innerHTML = all.map(([v, label]) => `<option value="${v}">${label}</option>`).join('');
      if (value !== undefined) el.value = value;
    }
    function normalizeOptions(items) {
      return (items || []).map(item => Array.isArray(item) ? item : [item.value, item.label || item.value]).filter(([v]) => !!v);
    }
    function fillForm(config) {
      document.querySelectorAll('[name]').forEach(el => {
        if (secretKeys.includes(el.name)) return;
        const val = get(config, el.name);
        if (el.dataset.modelSelect === 'single') {
          renderSelectOptions(el, modelOptions, val);
          return;
        }
        if (el.dataset.modelSelect === 'matrix') {
          renderSelectOptions(el, matrixOptions, val);
          return;
        }
        if (el.type === 'checkbox') el.checked = !!val;
        else if (val !== undefined) el.value = val;
      });
    }
    function renderSecrets(secrets) {
      const root = document.getElementById('secrets');
      root.innerHTML = secretKeys.map(k => {
        const s = secrets[k] || {};
        const label = s.configured ? `${s.masked} (${s.source})` : '未配置';
        return `<div class="secret"><div><label>${k}：${label}</label><input name="${k}" type="password" placeholder="留空不修改"></div><div class="hint">状态：${s.configured ? '<span class=ok>ok</span>' : '<span class=warn>pending</span>'}</div></div>`;
      }).join('');
    }
    function renderStatus(data) {
      const checks = data.checks || {};
      const html = Object.entries(checks).map(([k,v]) => `<div class="pill"><b>${k}</b><span class="${v.ok?'ok':'warn'}">${v.ok?'ok':'warn'}</span></div>`).join('');
      document.getElementById('status').innerHTML = html;
      document.getElementById('raw').textContent = JSON.stringify(checks, null, 2);
    }
    function showNotice(kind, text) {
      const el = document.getElementById('saveNotice');
      el.className = 'notice ' + kind;
      el.textContent = text;
    }
    async function refresh() {
      const res = await fetch('/api/status');
      const data = await res.json();
      current = data.config;
      if (data.model_registry) {
        modelOptions = normalizeOptions(data.model_registry.model_options);
        matrixOptions = normalizeOptions(data.model_registry.matrix_options);
      }
      fillForm(data.config);
      renderSecrets(data.secrets || {});
      renderStatus(data);
    }
    async function save() {
      const btn = document.getElementById('saveBtn');
      const oldText = btn.textContent;
      btn.disabled = true;
      btn.textContent = '保存中…';
      showNotice('warn', '正在保存配置，请稍等…');
      try {
        const config = JSON.parse(JSON.stringify(current || {}));
        const secrets = {};
        document.querySelectorAll('[name]').forEach(el => {
          if (secretKeys.includes(el.name)) {
            if (el.value.trim()) secrets[el.name] = el.value.trim();
            return;
          }
          const value = el.type === 'checkbox' ? el.checked : (el.type === 'number' ? Number(el.value) : el.value);
          set(config, el.name, value);
        });
        const res = await fetch('/api/config', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({config, secrets})});
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || '保存失败');
        await refresh();
        showNotice('ok', '配置已保存，状态已刷新。');
      } catch (err) {
        showNotice('err', err.message || '保存失败，请查看日志。');
      } finally {
        btn.disabled = false;
        btn.textContent = oldText;
      }
    }
    function openStatus(){ window.open('http://127.0.0.1:8765', '_blank'); }
    refresh();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        try:
            with open(LOG_FILE, "a") as f:
                f.write("[%s] %s\n" % (utc_now(), fmt % args))
        except OSError:
            pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/setup"}:
            self._send(200, HTML.encode(), "text/html; charset=utf-8")
        elif parsed.path == "/api/status":
            self._json(200, system_status())
        elif parsed.path == "/healthz":
            self._send(200, b"ok", "text/plain")
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/mirage/reprobe":
            import subprocess as _sp
            try:
                r = _sp.run(
                    [str(HARNESS_DIR / "solar-harness.sh"), "mirage", "doctor", "--json"],
                    capture_output=True, text=True, timeout=15
                )
                self._json(200, {"ok": r.returncode == 0, "stdout": r.stdout[:2000], "stderr": r.stderr[:500]})
            except Exception as exc:
                self._json(500, {"ok": False, "error": str(exc)})
            return
        if parsed.path != "/api/config":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            cfg = deep_merge(DEFAULT_CONFIG, payload.get("config") or {})
            save_config(cfg)
            save_secrets(payload.get("secrets") or {})
            self._json(200, {"ok": True, "config_path": str(CONFIG_PATH), "secrets_path": str(SECRETS_PATH)})
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def start_server(port: int = DEFAULT_PORT, open_browser: bool = False) -> None:
    HARNESS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(load_config())
    httpd = ThreadingHTTPServer((BIND_HOST, port), Handler)
    PID_FILE.write_text(str(os.getpid()) + "\n")
    PORT_FILE.write_text(str(port) + "\n")
    if open_browser:
        threading.Timer(0.5, lambda: subprocess.run(["/usr/bin/open", f"http://{BIND_HOST}:{port}/setup"], check=False)).start()
    try:
        httpd.serve_forever()
    finally:
        try:
            PID_FILE.unlink()
        except OSError:
            pass


def daemon_start(port: int, open_browser: bool) -> None:
    pid = read_pid()
    if pid and is_running(pid):
        print(f"status=running\npid={pid}\nurl=http://{BIND_HOST}:{PORT_FILE.read_text().strip() if PORT_FILE.exists() else port}/setup")
        if open_browser:
            subprocess.run(["/usr/bin/open", f"http://{BIND_HOST}:{port}/setup"], check=False)
        return
    cmd = [sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(port)]
    if open_browser:
        cmd.append("--open")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as log:
        subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
    time.sleep(0.8)
    pid = read_pid()
    print(f"status=running\npid={pid or 'unknown'}\nurl=http://{BIND_HOST}:{port}/setup")


def stop_server() -> None:
    pid = read_pid()
    if not pid or not is_running(pid):
        print("status=stopped")
        return
    os.kill(pid, 15)
    print(f"status=stopped\npid={pid}")


def status() -> None:
    pid = read_pid()
    port = PORT_FILE.read_text().strip() if PORT_FILE.exists() else str(DEFAULT_PORT)
    if pid and is_running(pid):
        print(f"status=running\npid={pid}\nurl=http://{BIND_HOST}:{port}/setup\nconfig={CONFIG_PATH}\nsecrets={SECRETS_PATH}")
    else:
        print(f"status=stopped\nurl=http://{BIND_HOST}:{port}/setup\nconfig={CONFIG_PATH}\nsecrets={SECRETS_PATH}")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    port = DEFAULT_PORT
    open_browser = "--open" in argv
    if "--port" in argv:
        idx = argv.index("--port")
        port = int(argv[idx + 1])
    if cmd == "serve":
        start_server(port, open_browser)
    elif cmd == "start":
        daemon_start(port, open_browser)
    elif cmd == "stop":
        stop_server()
    elif cmd == "restart":
        stop_server()
        time.sleep(0.5)
        daemon_start(port, open_browser)
    elif cmd == "status":
        status()
    elif cmd == "open":
        daemon_start(port, True)
    elif cmd == "first-run":
        cfg = load_config()
        if not cfg.get("setup_complete"):
            daemon_start(port, True)
        else:
            print("status=skipped\nreason=setup_complete")
    else:
        print("Usage: solar-config-server.py [start|stop|restart|status|open|first-run|serve] [--port N] [--open]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
