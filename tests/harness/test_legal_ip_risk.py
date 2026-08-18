import hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
import pytest
from harness.lib import legal_ip_risk
from harness.lib.legal_ip_risk import screen
TOOL=Path(__file__).parents[2]/"harness/lib/legal_ip_risk.py";ANCHOR="a"*64
def dump(path,value):
 raw=(json.dumps(value,sort_keys=True)+"\n").encode();path.write_bytes(raw);return str(path.resolve()),hashlib.sha256(raw).hexdigest()
def manifest(tmp_path):
 evidence={"evidence_kind":"rights_record","record_id":"rights-1","source_id":"open-dataset","uri":"https://example.invalid/dataset","license":"CC-BY-4.0","copyright_owner":"Example Research Group","issuer_id":"registry-1","issuer_identity_uri":"https://registry.example.org/identity","trust_anchor_sha256":ANCHOR,"rights_basis":"public_license_registry_record","license_document_uri":"https://creativecommons.org/licenses/by/4.0/","issued_at":"2026-01-01T00:00:00Z"};path,sha=dump(tmp_path/"rights.json",evidence)
 return {"manifest_id":"m1","purpose":"research","processing_jurisdiction":"CA","retention_days":14,"contains_personal_data":False,"sources":[{"source_id":"open-dataset","uri":"https://example.invalid/dataset","license":"CC-BY-4.0","copyright_owner":"Example Research Group","allowed_purposes":["research"],"evidence_path":path,"evidence_sha256":sha}]}
def policy(m=None):
 p={"policy_version":"test-1","allowed_purposes":["research"],"allowed_processing_jurisdictions":["CA"],"review_processing_jurisdictions":["US"],"max_retention_days":30,"allowed_licenses":["CC-BY-4.0"],"review_licenses":[],"denied_licenses":["ARR"],"trusted_issuers":[{"issuer_id":"registry-1","identity_uri":"https://registry.example.org/identity","trust_anchor_sha256":ANCHOR,"allowed_evidence_kinds":["rights_record"]}],"trusted_sources":[]}
 if m:p["trusted_sources"]=[{"source_id":s["source_id"],"rights_evidence_sha256":s["evidence_sha256"],"issuer_id":"registry-1"} for s in m["sources"]]
 return p
def run_cli(tmp_path,m,*,raw=None,output=None):
 mp=tmp_path/"manifest.json";pp=tmp_path/"policy.json";mp.write_bytes(raw if raw is not None else (json.dumps(m)+"\n").encode());pp.write_text(json.dumps(policy(m))+"\n");out=output or tmp_path/"result.json";p=subprocess.run([sys.executable,str(TOOL),"screen","--manifest",str(mp),"--policy",str(pp),"--output",str(out)],capture_output=True,text=True);return p,mp,pp,out
def test_pinned_evidence_allows(tmp_path):
 m=manifest(tmp_path);r=screen(m,policy(m));assert r["decision"]=="allow" and r["admission_allowed"]
@pytest.mark.parametrize("bad",[True,1.9,"14"])
def test_retention_is_exact_int(tmp_path,bad):
 m=manifest(tmp_path);p=policy(m);m["retention_days"]=bad;assert screen(m,p)["decision"]=="deny"
def test_missing_id_denied(tmp_path):
 m=manifest(tmp_path);p=policy(m);m.pop("manifest_id");assert screen(m,p)["decision"]=="deny"
@pytest.mark.parametrize("bad_uri",["https:not-an-authority","https://user:secret@example.invalid/data"])
def test_malformed_or_credentialed_https_uri_is_denied(tmp_path,bad_uri):
 m=manifest(tmp_path);record=json.loads(Path(m["sources"][0]["evidence_path"]).read_text());record["uri"]=bad_uri;path,sha=dump(tmp_path/"bad-uri-rights.json",record);m["sources"][0].update({"uri":bad_uri,"evidence_path":path,"evidence_sha256":sha});assert screen(m,policy(m))["decision"]=="deny"
@pytest.mark.parametrize("attack",["bad_sha","nonexistent","self_string"])
def test_bad_evidence_denied(tmp_path,attack):
 m=manifest(tmp_path);s=m["sources"][0]
 if attack=="bad_sha":s["evidence_sha256"]="0"*64
 elif attack=="nonexistent":s["evidence_path"]=str((tmp_path/"missing").resolve())
 else:s["evidence_path"],s["evidence_sha256"]=dump(tmp_path/"claim.json",{"claim":"mine"})
 assert screen(m,policy(m))["decision"]=="deny"
def consent_manifest(tmp_path,expires="2099-01-01T00:00:00Z",revoked=None):
 m=manifest(tmp_path);m["contains_personal_data"]=True;record={"evidence_kind":"consent_record","evidence_id":"c17","status":"granted","purposes":["research"],"expires_at":expires,"revoked_at":revoked};path,sha=dump(tmp_path/"consent.json",record);m["consent"]={"evidence_id":"c17","evidence_path":path,"evidence_sha256":sha};return m
@pytest.mark.parametrize("expires,revoked",[("2020-01-01T00:00:00Z",None),("2099-01-01T00:00:00Z","2026-01-01T00:00:00Z")])
def test_expired_revoked_consent_denied(tmp_path,expires,revoked):
 m=consent_manifest(tmp_path,expires,revoked);assert screen(m,policy(m),now=datetime(2026,8,12,tzinfo=timezone.utc))["decision"]=="deny"
def test_valid_consent_still_review(tmp_path):
 m=consent_manifest(tmp_path);r=screen(m,policy(m),now=datetime(2026,8,12,tzinfo=timezone.utc));assert r["decision"]=="review_required" and not r["admission_allowed"]
def test_duplicate_key_and_full_denial_schema(tmp_path):
 m=manifest(tmp_path);p,_,_,out=run_cli(tmp_path,m,raw=b'{"x":1,"x":2}');r=json.loads(out.read_text());assert p.returncode==2 and {"schema_version","policy","manifest","summary","limitations","findings","decision"}<=r.keys()
@pytest.mark.parametrize("target",["manifest","policy","evidence"])
def test_output_alias_preserves_input(tmp_path,target):
 m=manifest(tmp_path);mp=tmp_path/"manifest.json";mp.write_text(json.dumps(m));pp=tmp_path/"policy.json";pp.write_text(json.dumps(policy(m)));out={"manifest":mp,"policy":pp,"evidence":Path(m["sources"][0]["evidence_path"])}[target];before=out.read_bytes();p=subprocess.run([sys.executable,str(TOOL),"screen","--manifest",str(mp),"--policy",str(pp),"--output",str(out)]);assert p.returncode==2 and out.read_bytes()==before
def test_stale_output_replaced(tmp_path):
 m=manifest(tmp_path);out=tmp_path/"result.json";out.write_text('{"stale":true}');p,_,_,_=run_cli(tmp_path,m,raw=b'{"x":1,"x":2}',output=out);assert p.returncode==2 and "stale" not in json.loads(out.read_text())
def test_manifest_author_self_assertion_with_matching_sha_never_allows(tmp_path):
 m=manifest(tmp_path);p=policy(m);record=json.loads(Path(m["sources"][0]["evidence_path"]).read_text());record.update({"issuer_id":"manifest-author","issuer_identity_uri":"https://author.example/identity","trust_anchor_sha256":"b"*64});path,sha=dump(tmp_path/"self.json",record);m["sources"][0].update({"evidence_path":path,"evidence_sha256":sha});r=screen(m,p);assert r["decision"]=="review_required" and not r["admission_allowed"]
def test_forged_trusted_issuer_name_without_exact_sha_pin_never_allows(tmp_path):
 m=manifest(tmp_path);p=policy(m);record=json.loads(Path(m["sources"][0]["evidence_path"]).read_text());record["record_id"]="forged-but-trusted-name";path,sha=dump(tmp_path/"forged.json",record);m["sources"][0].update({"evidence_path":path,"evidence_sha256":sha});r=screen(m,p);assert r["decision"]=="review_required" and not r["admission_allowed"]
def test_atomic_replace_failure_preserves_old_output(tmp_path,monkeypatch):
 out=tmp_path/"result.json";out.write_bytes(b'{"prior":true}\n');monkeypatch.setattr(legal_ip_risk.os,"replace",lambda *_:(_ for _ in ()).throw(OSError("injected")))
 with pytest.raises(OSError):legal_ip_risk._atomic_write(out,{"decision":"deny"})
 assert out.read_bytes()==b'{"prior":true}\n' and not list(tmp_path.glob(".result.json.*.tmp"))
