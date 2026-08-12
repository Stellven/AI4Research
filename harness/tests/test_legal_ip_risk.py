import hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
from harness.lib.legal_ip_risk import screen

TOOL=Path(__file__).parents[1]/"lib/legal_ip_risk.py"
def dump(path:Path,value)->tuple[str,str]:
 raw=(json.dumps(value,sort_keys=True)+"\n").encode();path.write_bytes(raw);return str(path.resolve()),hashlib.sha256(raw).hexdigest()
def policy(): return {"policy_version":"test-1","allowed_purposes":["research"],"allowed_processing_jurisdictions":["CA"],"review_processing_jurisdictions":["US"],"max_retention_days":30,"allowed_licenses":["CC0-1.0","CC-BY-4.0"],"review_licenses":["CC-BY-SA-4.0"],"denied_licenses":["ARR"]}
def manifest(tmp_path:Path):
 evidence={"evidence_kind":"rights_record","source_id":"open-dataset","uri":"https://example.invalid/dataset","license":"CC-BY-4.0","copyright_owner":"Example Research Group","issuer":"Example Registry","issued_at":"2026-01-01T00:00:00Z"};path,sha=dump(tmp_path/"rights.json",evidence)
 return {"manifest_id":"m1","purpose":"research","processing_jurisdiction":"CA","retention_days":14,"contains_personal_data":False,"sources":[{"source_id":"open-dataset","uri":"https://example.invalid/dataset","license":"CC-BY-4.0","copyright_owner":"Example Research Group","allowed_purposes":["research"],"evidence_path":path,"evidence_sha256":sha}]}
def run_cli(tmp_path:Path,manifest_value,*,raw:bytes|None=None,output:Path|None=None):
 mp=tmp_path/"manifest.json";pp=tmp_path/"policy.json";mp.write_bytes(raw if raw is not None else (json.dumps(manifest_value)+"\n").encode());pp.write_text(json.dumps(policy())+"\n");out=output or tmp_path/"result.json";p=subprocess.run([sys.executable,str(TOOL),"screen","--manifest",str(mp),"--policy",str(pp),"--output",str(out)],capture_output=True,text=True);return p,mp,pp,out
def test_allows_only_hash_verified_structured_rights(tmp_path):
 r=screen(manifest(tmp_path),policy());assert r["decision"]=="allow" and r["admission_allowed"] and all(f["rule_id"] for f in r["findings"])
@pytest.mark.parametrize("bad",[True,1.9,"14"])
def test_retention_requires_exact_nonbool_json_integer(tmp_path,bad):
 m=manifest(tmp_path);m["retention_days"]=bad;assert screen(m,policy())["decision"]=="deny"
def test_missing_manifest_id_fails_closed(tmp_path):
 m=manifest(tmp_path);m.pop("manifest_id");assert screen(m,policy())["decision"]=="deny"
@pytest.mark.parametrize("attack",["bad_sha","nonexistent","self_assertion"])
def test_unverifiable_rights_evidence_fails_closed(tmp_path,attack):
 m=manifest(tmp_path);source=m["sources"][0]
 if attack=="bad_sha": source["evidence_sha256"]="0"*64
 elif attack=="nonexistent": source["evidence_path"]=str((tmp_path/"missing.json").resolve())
 else: source["evidence_path"],source["evidence_sha256"]=dump(tmp_path/"claim.json",{"claim":"I own this"})
 assert screen(m,policy())["decision"]=="deny"
def consent_manifest(tmp_path:Path,*,expires="2099-01-01T00:00:00Z",revoked=None):
 m=manifest(tmp_path);m["contains_personal_data"]=True;record={"evidence_kind":"consent_record","evidence_id":"consent-17","status":"granted","purposes":["research"],"expires_at":expires,"revoked_at":revoked};path,sha=dump(tmp_path/"consent.json",record);m["consent"]={"evidence_id":"consent-17","evidence_path":path,"evidence_sha256":sha};return m
@pytest.mark.parametrize("expires,revoked",[("2020-01-01T00:00:00Z",None),("2099-01-01T00:00:00Z","2026-01-01T00:00:00Z")])
def test_expired_or_revoked_consent_is_denied(tmp_path,expires,revoked):
 assert screen(consent_manifest(tmp_path,expires=expires,revoked=revoked),policy(),now=datetime(2026,8,12,tzinfo=timezone.utc))["decision"]=="deny"
def test_valid_hashed_consent_requires_human_review(tmp_path):
 r=screen(consent_manifest(tmp_path),policy(),now=datetime(2026,8,12,tzinfo=timezone.utc));assert r["decision"]=="review_required" and not r["admission_allowed"]
def test_duplicate_json_key_is_rejected(tmp_path):
 m=manifest(tmp_path);raw=json.dumps(m).replace('"manifest_id": "m1"','"manifest_id": "m1", "manifest_id": "m2"').encode();p,_,_,out=run_cli(tmp_path,m,raw=raw);assert p.returncode==2 and json.loads(out.read_text())["decision"]=="deny" and "duplicate JSON key" in out.read_text()
@pytest.mark.parametrize("target",["manifest","policy","evidence"])
def test_output_cannot_alias_any_input(tmp_path,target):
 m=manifest(tmp_path);mp=tmp_path/"manifest.json";mp.write_text(json.dumps(m));pp=tmp_path/"policy.json";pp.write_text(json.dumps(policy()));paths={"manifest":mp,"policy":pp,"evidence":Path(m["sources"][0]["evidence_path"])};out=paths[target];before=out.read_bytes();p=subprocess.run([sys.executable,str(TOOL),"screen","--manifest",str(mp),"--policy",str(pp),"--output",str(out)],capture_output=True);assert p.returncode==2 and out.read_bytes()==before
def test_stale_output_is_atomically_replaced_with_current_denial(tmp_path):
 m=manifest(tmp_path);out=tmp_path/"result.json";out.write_text('{"stale":true}')
 p,_,_,_=run_cli(tmp_path,m,raw=b'{"manifest_id":"a","manifest_id":"b"}',output=out);value=json.loads(out.read_text());assert p.returncode==2 and value["decision"]=="deny" and "stale" not in value
