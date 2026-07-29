from __future__ import annotations

from pathlib import Path

from test_j11_capsule_operator import WorkerJourney, python_env, write_json


def test_p22_j14_wechat_user_identity(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    rec = WorkerJourney(repo_root, "P22-J14", "WeChat channel request with bound user identity and context verification")
    sandbox = tmp_path / "p22-j14"
    env = python_env({"HOME": str(sandbox / "home"), "USERPROFILE": str(sandbox / "home")})

    wechat_probe = rec.run(
        "wechat-entrypoint-search",
        [
            phase22_python,
            "-c",
            "from pathlib import Path; import json; roots=[Path('harness'),Path('integrations'),Path('core'),Path('app')]; hits=[]\nfor root in roots:\n    if root.exists():\n        for p in root.rglob('*'):\n            if p.is_file() and 'wechat' in p.name.lower(): hits.append(str(p))\nprint(json.dumps({'hits': hits[:50], 'count': len(hits)}))",
        ],
        env=env,
    )
    identity_probe = rec.run(
        "identity-entrypoint-search",
        [
            phase22_python,
            "-c",
            "from pathlib import Path; import json; files=[str(p) for p in Path('harness/lib').glob('*identity*')]+[str(p) for p in Path('harness/lib').glob('*account*')]+[str(p) for p in Path('harness/config').glob('*account*')]; print(json.dumps({'hits': files, 'count': len(files)}))",
        ],
        env=env,
    )
    social_registry_probe = rec.run(
        "social-account-registry-import",
        [phase22_python, "-c", "import sys,json; sys.path.insert(0,'harness/lib'); import social_account_registry as s; print(json.dumps({'module':'social_account_registry','attrs': sorted([x for x in dir(s) if not x.startswith('_')])[:30]}))"],
        env=env,
    )

    probe_path = write_json(
        rec.run_dir / "j14-wechat-identity-preflight.json",
        {
            "wechat_probe_exit_code": wechat_probe.returncode,
            "wechat_probe_stdout": wechat_probe.stdout,
            "identity_probe_exit_code": identity_probe.returncode,
            "identity_probe_stdout": identity_probe.stdout,
            "social_registry_exit_code": social_registry_probe.returncode,
            "social_registry_stdout": social_registry_probe.stdout[-1000:],
            "social_registry_stderr": social_registry_probe.stderr[-1000:],
        },
    )
    rec.add_artifact(probe_path, "j14_wechat_identity_preflight")
    rec.add_assertion("wechat_channel_entrypoint_missing", '"count": 0' in wechat_probe.stdout, wechat_probe.stdout)
    rec.add_assertion("identity_registry_probe_executed", identity_probe.returncode == 0 or social_registry_probe.returncode == 0, identity_probe.stdout + social_registry_probe.stdout)

    command_evidence = rec.run_dir / "commands.json"
    rec.add_l2("Vertical", "WeChat/user identity", "WeChat Channel Intake", "NOT_AVAILABLE", "wechat_channel_entrypoint_missing", command_evidence, command_label="wechat-entrypoint-search", known_limitations=["No WeChat-named production channel entrypoint was found under harness, integrations, core, or app."])
    rec.add_l2("Vertical", "WeChat/user identity", "User Identity Binding & Context Verification", "NOT_AVAILABLE", "wechat_channel_entrypoint_missing", command_evidence, command_label="identity-entrypoint-search", known_limitations=["Identity/account helper modules exist, but no WeChat-bound request intake flow is implemented."])
    rec.add_l2("Vertical", "WeChat/user identity", "Channel Account/Provider Readiness", "ENVIRONMENT_BLOCKED", "wechat_channel_entrypoint_missing", command_evidence, command_label="wechat-entrypoint-search", environment_requirement="Configured WeChat account/channel provider and production channel adapter", known_limitations=["No local WeChat account/channel provider is configured or implemented in the current product surface."])

    rec.finalize("NOT_AVAILABLE", limitations=["J14 could not run as a product journey because the WeChat channel entrypoint is absent in the current checkout."])
