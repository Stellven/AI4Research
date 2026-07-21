from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def git(cwd: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(["/usr/bin/git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    checkout = root / "tmp/checkout"
    locked = "fb3f589b08e4167ac3cb0043fb3d59801a0f110b"
    real_code, real_sha, real_err = git(repo, "rev-parse", "HEAD")
    clone_code, clone_sha, clone_err = git(checkout, "rev-parse", "HEAD")
    branch_code, branch, branch_err = git(repo, "branch", "--show-current")
    env_path = root / "environment.json"
    payload = json.loads(env_path.read_text(encoding="utf-8"))
    payload.update({
        "audit_completed_local": datetime.now().astimezone().isoformat(timespec="seconds"),
        "real_repo_final_sha": real_sha,
        "real_repo_final_branch": branch,
        "isolated_checkout_final_sha": clone_sha,
        "locked_sha_unchanged_in_isolated_checkout": clone_sha == locked,
        "authoritative_test_home": str(root / "tmp/final-home"),
        "authoritative_solar_home": str(root / "tmp/installer-solar"),
        "live_phase_executed": False,
    })
    env_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with (root / "repo-state.txt").open("a", encoding="utf-8") as handle:
        handle.write("\nfinal_audit_state\n")
        handle.write(f"audit_completed_local={payload['audit_completed_local']}\n")
        handle.write(f"real_repo_final_branch={branch} [exit_code={branch_code}] {branch_err}\n")
        handle.write(f"real_repo_final_sha={real_sha} [exit_code={real_code}] {real_err}\n")
        handle.write(f"isolated_checkout_final_sha={clone_sha} [exit_code={clone_code}] {clone_err}\n")
        handle.write(f"locked_sha_unchanged_in_isolated_checkout={clone_sha == locked}\n")
    result = {
        "real_repo_final_branch": branch,
        "real_repo_final_sha": real_sha,
        "isolated_checkout_final_sha": clone_sha,
        "lock_matches": clone_sha == locked,
    }
    print(json.dumps(result, indent=2))
    return 0 if clone_sha == locked else 1


if __name__ == "__main__":
    raise SystemExit(main())
