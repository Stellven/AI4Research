"""Tests for capability_token.py — Token validation and path enforcement."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from capability_token import CapabilityToken

def test_valid_token():
    t = CapabilityToken("t1", ["file:write", "shell:run"], "2099-01-01T00:00:00Z", "a1")
    v = t.validate_for_lease()
    assert v["valid"]
    assert t.has_scope("file:write")
    assert not t.has_scope("network:full")
    print("PASS: valid_token")

def test_expired_token():
    t = CapabilityToken("t1", ["file:write"], "2020-01-01T00:00:00Z", "a1")
    v = t.validate_for_lease()
    assert not v["valid"]
    assert "token_expired" in v["issues"]
    print("PASS: expired_token")

def test_allow_path():
    t = CapabilityToken("t1", ["file:write"], "2099-01-01T00:00:00Z", "a1",
                        allow_paths=["~/.solar/harness"])
    r = t.check_path_access("~/.solar/harness/lib/test.py")
    assert r["allowed"]
    r2 = t.check_path_access("/etc/passwd")
    assert not r2["allowed"]
    print("PASS: allow_path")

def test_deny_path():
    t = CapabilityToken("t1", ["file:write"], "2099-01-01T00:00:00Z", "a1",
                        deny_paths=["/etc", "/var"])
    r = t.check_path_access("/etc/shadow")
    assert not r["allowed"]
    r2 = t.check_path_access("/home/user/file.txt")
    assert r2["allowed"]
    print("PASS: deny_path")

if __name__ == "__main__":
    test_valid_token()
    test_expired_token()
    test_allow_path()
    test_deny_path()
    print("\n4/4 passed")
