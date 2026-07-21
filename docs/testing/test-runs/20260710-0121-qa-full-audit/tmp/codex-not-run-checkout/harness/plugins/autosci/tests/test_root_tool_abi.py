from __future__ import annotations

import json
import os
import shlex
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

from evaluators.scientific import autosci_runtime_evidence_gate


REPO = Path(__file__).resolve().parents[4]
ROUTES = REPO / "harness/plugins/autosci/config/feature_parity_routes.v1.json"


def run_tool(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "tools" / tool), *args],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def test_feature_parity_routes_reference_existing_root_tools() -> None:
    config = json.loads(ROUTES.read_text(encoding="utf-8"))
    missing: dict[str, list[str]] = {}
    for route in config["routes"]:
        paths = []
        for item in route.get("primary_tools") or []:
            path = item.split()[0]
            if path.startswith("tools/") and not (REPO / path).exists():
                paths.append(path)
        if paths:
            missing[route["native_skill"]] = sorted(set(paths))
    assert missing == {}


def test_side_effect_root_tools_emit_truthful_non_mutating_evidence(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "ideas").mkdir(parents=True)
    (wiki / "graph").mkdir()
    (wiki / "ideas/skillgen.md").write_text(
        "---\n"
        "title: \"SkillGen\"\n"
        "slug: \"skillgen\"\n"
        "status: proposed\n"
        "origin: \"root-tool-smoke\"\n"
        "tags: []\n"
        "priority: 3\n"
        "---\n"
        "# SkillGen\n\nGenerated skills.\n",
        encoding="utf-8",
    )
    (wiki / "graph/edges.jsonl").write_text("", encoding="utf-8")

    lint = payload(run_tool("lint.py", "--wiki-root", str(wiki)))
    assert lint["schema"] == "autosci_wiki_lint_cli.v1"
    assert lint["ok"] is True

    init_plan = payload(run_tool("init_discovery.py", "plan", "skill generation", "--wiki-root", str(wiki), "--no-network-fetch"))
    assert init_plan["schema"] == "autosci_init_discovery_cli.v1"
    assert init_plan["status"] == "completed"

    remote = payload(run_tool("remote.py", "launch", "--experiment", "exp-skillgen"))
    assert remote["schema"] == "autosci_remote_cli.v1"
    assert remote["status"] == "approval_required"

    daily = payload(run_tool("daily_arxiv.py", "prepare", "--topic", "skill generation"))
    assert daily["schema"] == "autosci_daily_arxiv_cli.v1"
    assert daily["status"] == "completed"

    email = payload(run_tool("send_email.py", "send", "--to", "user@example.com", "--subject", "AutoSci"))
    assert email["schema"] == "autosci_send_email_cli.v1"
    assert email["status"] == "approval_required"

    email_config = payload(run_tool("send_email.py", "--check-config"))
    assert email_config["schema"] == "autosci_send_email_cli.v1"
    assert email_config["status"] == "inconclusive"

    reset = payload(run_tool("reset_wiki.py", "--wiki-root", str(wiki)))
    assert reset["schema"] == "autosci_reset_wiki_cli.v1"
    assert reset["status"] == "dry_run"

    serve = payload(run_tool("serve.py", "--wiki-root", str(wiki), "--health-check"))
    assert serve["schema"] == "autosci_serve_cli.v1"
    assert serve["status"] == "completed"
    assert serve["ok"] is True
    assert serve["node_count"] >= 1
    assert serve["edge_count"] == 0

    serve_probe = payload(run_tool("serve.py", "--wiki-root", str(wiki), "--probe-server", "--port", "0"))
    assert serve_probe["schema"] == "autosci_serve_cli.v1"
    assert serve_probe["status"] == "completed"
    assert serve_probe["ok"] is True
    assert serve_probe["server_started"] is True
    assert serve_probe["server_stopped"] is True
    assert serve_probe["health"]["ok"] is True

    dag_out = tmp_path / "dag.json"
    dag = payload(run_tool("wiki2dag.py", "build", "--wiki-root", str(wiki), "--out", str(dag_out)))
    assert dag["schema"] == "autosci_wiki_dag.v1"
    assert dag["status"] == "completed"
    assert dag_out.exists()

    poster_out = tmp_path / "poster.html"
    poster = payload(run_tool("poster.py", "build", "--compat-scaffold", "--out", str(poster_out), "--title", "SkillGen"))
    assert poster["schema"] == "autosci_poster_cli.v1"
    assert poster["status"] == "completed"
    validate = payload(run_tool("poster.py", "validate", str(poster_out)))
    assert validate["status"] == "completed"

    latex = payload(run_tool("rasterize_latex.py", "diagnose"))
    assert latex["schema"] == "autosci_rasterize_latex_cli.v1"
    assert latex["status"] == "completed"


def test_poster_tool_executes_approved_render_export(tmp_path: Path) -> None:
    poster_html = tmp_path / "poster.html"
    poster = payload(run_tool("poster.py", "build", "--compat-scaffold", "--out", str(poster_html), "--title", "SkillGen"))
    assert poster["status"] == "completed"

    renderer = tmp_path / "poster_renderer.py"
    renderer.write_text(
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "html, png, validation = sys.argv[1:4]\n"
        "assert Path(html).exists()\n"
        "Path(png).write_bytes(b'\\x89PNG\\r\\n\\x1a\\n')\n"
        "Path(validation).write_text(json.dumps({\n"
        "  'browser_rendered': True,\n"
        "  'png_exported': True,\n"
        "  'overflow_probe': 'passed'\n"
        "}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    allowlist = tmp_path / "poster-allowlist.json"
    allowlist.write_text(
        json.dumps(
            {
                "executables": [sys.executable],
                "poster_render_command": [sys.executable, str(renderer), "{html}", "{png}", "{validation}"],
            }
        ),
        encoding="utf-8",
    )
    png_out = tmp_path / "poster.png"
    validation_out = tmp_path / "poster.validation.json"
    runtime_out = tmp_path / "poster-runtime.json"

    rendered = payload(
        run_tool(
            "poster.py",
            "render",
            str(poster_html),
            "--approval-ref",
            "approval-poster-render",
            "--allowlist-evidence",
            str(allowlist),
            "--png-out",
            str(png_out),
            "--validation-out",
            str(validation_out),
            "--runtime-evidence-out",
            str(runtime_out),
            "--execute-approved",
        )
    )
    assert rendered["schema"] == "autosci_poster_cli.v1"
    assert rendered["status"] == "completed"
    assert rendered["ok"] is True
    assert png_out.exists()
    runtime = json.loads(runtime_out.read_text(encoding="utf-8"))
    result = runtime["outputs"]["runtime"]
    assert result["action"] == "build_poster"
    assert result["browser_rendered"] is True
    assert result["png_exported"] is True
    assert result["overflow_probe"] == "passed"
    gate = autosci_runtime_evidence_gate.evaluate(runtime, path=runtime_out)
    assert gate.ok is True, gate.reasons


def test_poster_tool_supports_native_template_outline_pipeline(tmp_path: Path) -> None:
    template = tmp_path / "poster_template.html"
    outline = tmp_path / "outline.html"
    dag = tmp_path / "dag.json"
    poster_html = tmp_path / "native-poster.html"
    template.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>:root{--poster-width:1400px;--poster-height:900px}</style>"
        "</head><body><div class=\"poster\"><header>"
        "<div class=\"logo-affiliation\"></div>"
        "<h1 class=\"title\">Paper Title</h1>"
        "<div class=\"authors\">Anonymous</div>"
        "<div class=\"conf\"><div class=\"venue\"></div><div class=\"logo-conference\"></div></div>"
        "</header><main class=\"main\"><div class=\"flow\" id=\"flow\"></div></main>"
        "</div></body></html>\n",
        encoding="utf-8",
    )
    outline.write_text(
        "<section class=\"section\"><h2>Problem</h2><p>Context.</p></section>\n"
        "<section class=\"section\"><h2>Method</h2><p>Approach.</p></section>\n"
        "<section class=\"section\"><h2>Results</h2><p>Evidence.</p></section>\n",
        encoding="utf-8",
    )
    dag.write_text(
        json.dumps({"nodes": [{"name": "Native Poster", "content": "AutoSci Authors"}]}),
        encoding="utf-8",
    )

    built = payload(
        run_tool(
            "poster.py",
            "build",
            "--template",
            str(template),
            "--outline",
            str(outline),
            "--output",
            str(poster_html),
        )
    )
    assert built["schema"] == "autosci_poster_cli.v1"
    assert built["status"] == "completed"

    injected = run_tool("poster.py", "inject-title", "--dag", str(dag), str(poster_html))
    assert injected.returncode == 0, injected.stdout + injected.stderr
    header = run_tool("poster.py", "inject-header", str(poster_html), "--venue", "ICML 2026")
    assert header.returncode == 0, header.stdout + header.stderr

    validate = payload(run_tool("poster.py", "validate", str(poster_html)))
    assert validate["schema"] == "autosci_poster_cli.v1"
    assert validate["status"] == "completed"
    text = poster_html.read_text(encoding="utf-8")
    assert "Native Poster" in text
    assert "AutoSci Authors" in text
    assert "ICML 2026" in text


def test_send_email_tool_executes_approved_smtp_delivery(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            self.wfile.write(b"220 localhost ESMTP\r\n")
            data_mode = False
            data_lines: list[str] = []
            while True:
                raw = self.rfile.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                upper = line.upper()
                if data_mode:
                    if line == ".":
                        captured["message"] = "\n".join(data_lines)
                        self.wfile.write(b"250 queued\r\n")
                        data_mode = False
                    else:
                        data_lines.append(line)
                    continue
                if upper.startswith(("EHLO", "HELO")):
                    self.wfile.write(b"250-localhost\r\n250 HELP\r\n")
                elif upper.startswith("MAIL FROM:"):
                    captured["mail_from"] = line
                    self.wfile.write(b"250 ok\r\n")
                elif upper.startswith("RCPT TO:"):
                    captured["rcpt_to"] = line
                    self.wfile.write(b"250 ok\r\n")
                elif upper == "DATA":
                    self.wfile.write(b"354 end with dot\r\n")
                    data_mode = True
                elif upper == "QUIT":
                    self.wfile.write(b"221 bye\r\n")
                    break
                else:
                    self.wfile.write(b"250 ok\r\n")

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        runtime_out = tmp_path / "email-runtime.json"
        body_file = tmp_path / "daily-digest.md"
        body_file.write_text("Approved SMTP delivery.", encoding="utf-8")
        email = payload(
            run_tool(
                "send_email.py",
                "send",
                "--to",
                "user@example.com",
                "--from",
                "autosci@example.com",
                "--subject",
                "AutoSci SMTP",
                "--body-file",
                str(body_file),
                "--approval-ref",
                "approval-email-smtp",
                "--smtp-host",
                "127.0.0.1",
                "--smtp-port",
                str(server.server_address[1]),
                "--runtime-evidence-out",
                str(runtime_out),
                "--execute-approved",
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert email["schema"] == "autosci_send_email_cli.v1"
    assert email["status"] == "completed"
    assert email["ok"] is True
    assert "Approved SMTP delivery." in captured["message"]

    runtime = json.loads(runtime_out.read_text(encoding="utf-8"))
    result = runtime["outputs"]["runtime"]
    assert runtime["schema"] == "autosci_runtime_evidence.v1"
    assert result["action"] == "send_email"
    assert result["delivered"] is True
    assert result["provider"] == "smtp"
    gate = autosci_runtime_evidence_gate.evaluate(runtime, path=runtime_out)
    assert gate.ok is True, gate.reasons


def test_send_email_tool_supports_native_env_check_config(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "465",
        "SMTP_USER": "daily-user",
        "SMTP_PASSWORD": "daily-password",
        "SMTP_FROM": "autosci@example.com",
        "DAILY_ARXIV_EMAIL_TO": "reader@example.com;reviewer@example.com",
        "SMTP_SSL": "1",
    }
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/send_email.py"), "--check-config"],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    config = json.loads(proc.stdout)
    assert config["schema"] == "autosci_send_email_cli.v1"
    assert config["status"] == "completed"
    assert config["smtp_host"] == "smtp.example.test"
    assert config["smtp_port"] == 465
    assert config["recipient_count"] == 2
    assert config["use_ssl"] is True


def test_reset_wiki_tool_executes_approved_scoped_reset(tmp_path: Path) -> None:
    project = tmp_path / "project"
    wiki = project / "wiki"
    raw = project / "raw"
    (wiki / "ideas").mkdir(parents=True)
    (wiki / "outputs").mkdir()
    (wiki / "graph").mkdir()
    (wiki / ".checkpoints").mkdir()
    (raw / "papers").mkdir(parents=True)
    (wiki / "ideas" / "skillgen.md").write_text("# SkillGen\n", encoding="utf-8")
    (wiki / "outputs" / "report.md").write_text("# Report\n", encoding="utf-8")
    (wiki / "log.md").write_text("# Log\n", encoding="utf-8")
    (wiki / "graph" / "edges.jsonl").write_text("[]\n", encoding="utf-8")
    (wiki / ".checkpoints" / "batch.json").write_text("{}\n", encoding="utf-8")
    (raw / "papers" / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    blocked = payload(
        run_tool(
            "reset_wiki.py",
            "--scope",
            "all",
            "--project-root",
            str(project),
            "--yes",
        )
    )
    assert blocked["status"] == "approval_required"
    assert (wiki / "ideas" / "skillgen.md").exists()
    assert (raw / "papers" / "paper.pdf").exists()

    runtime_out = tmp_path / "reset-runtime.json"
    reset = payload(
        run_tool(
            "reset_wiki.py",
            "--scope",
            "all",
            "--project-root",
            str(project),
            "--approval-ref",
            "approval-reset-wiki",
            "--runtime-evidence-out",
            str(runtime_out),
            "--execute-approved",
            "--yes",
        )
    )
    assert reset["schema"] == "autosci_reset_wiki_cli.v1"
    assert reset["status"] == "completed"
    assert reset["ok"] is True
    assert not (wiki / "ideas" / "skillgen.md").exists()
    assert not (wiki / "outputs" / "report.md").exists()
    assert not (wiki / "log.md").exists()
    assert not (wiki / "graph" / "edges.jsonl").exists()
    assert not (wiki / ".checkpoints" / "batch.json").exists()
    assert not (raw / "papers" / "paper.pdf").exists()
    assert (wiki / "ideas" / ".gitkeep").exists()
    assert (raw / "papers" / ".gitkeep").exists()

    runtime = json.loads(runtime_out.read_text(encoding="utf-8"))
    result = runtime["outputs"]["runtime"]
    assert runtime["schema"] == "autosci_runtime_evidence.v1"
    assert runtime["status"] == "completed"
    assert result["action"] == "reset_plan"
    assert result["approval_ref"] == "approval-reset-wiki"
    assert result["deleted_files"] >= 6
    gate = autosci_runtime_evidence_gate.evaluate(runtime, path=runtime_out)
    assert gate.ok is True, gate.reasons


def test_remote_tool_executes_approved_allowlisted_launch(tmp_path: Path) -> None:
    run_dir = tmp_path / "remote-run"
    run_dir.mkdir()
    script = tmp_path / "remote_experiment.py"
    script.write_text(
        "import json\n"
        "from pathlib import Path\n"
        "Path('results.json').write_text(json.dumps({\n"
        "  'outcome': 'supports',\n"
        "  'metrics': [{'name': 'accuracy', 'value': 0.9}],\n"
        "  'logs': ['remote experiment completed']\n"
        "}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    normalized_command = " ".join([sys.executable, str(script)])
    allowlist = tmp_path / "remote-allowlist.json"
    runtime_out = tmp_path / "remote-runtime.json"
    allowlist.write_text(json.dumps({"commands": [normalized_command]}), encoding="utf-8")

    remote = payload(
        run_tool(
            "remote.py",
            "launch",
            "--experiment",
            "exp-skillgen",
            "--approval-ref",
            "approval-remote-skillgen",
            "--allowlist-evidence",
            str(allowlist),
            "--command",
            command,
            "--run-dir",
            str(run_dir),
            "--runtime-evidence-out",
            str(runtime_out),
            "--execute-approved",
        )
    )
    assert remote["schema"] == "autosci_remote_cli.v1"
    assert remote["status"] == "completed"
    assert remote["ok"] is True
    assert Path(remote["runtime_evidence_path"]).exists()

    runtime = json.loads(runtime_out.read_text(encoding="utf-8"))
    assert runtime["schema"] == "autosci_runtime_evidence.v1"
    assert runtime["status"] == "completed"
    result = runtime["outputs"]["runtime"]
    assert result["action"] == "run_experiment"
    assert result["approval_ref"] == "approval-remote-skillgen"
    assert result["result_collected"] is True
    assert result["outcome"] == "supports"
    assert result["metrics"] == [{"name": "accuracy", "value": 0.9}]
    gate = autosci_runtime_evidence_gate.evaluate(runtime, path=runtime_out)
    assert gate.ok is True, gate.reasons
