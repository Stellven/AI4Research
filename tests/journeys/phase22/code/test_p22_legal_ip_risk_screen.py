import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

def test_p22_legal_ip_risk_screen(repo_root: Path, tmp_path: Path) -> None:
    run_id="p22-legal-ip-risk-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out=repo_root/"outputs/phase22-real-journeys"/run_id;out.mkdir(parents=True)
    policy={"policy_version":"opensolar-local-2026-08-12","allowed_purposes":["noncommercial-research","reproducibility"],"allowed_processing_jurisdictions":["CA"],"review_processing_jurisdictions":["US","EU"],"max_retention_days":90,"allowed_licenses":["CC0-1.0","CC-BY-4.0"],"review_licenses":["CC-BY-SA-4.0"],"denied_licenses":["ARR","PROPRIETARY"]}
    def artifact(name,value):
        path=(out/name).resolve();raw=(json.dumps(value,sort_keys=True)+"\n").encode();path.write_bytes(raw);return str(path),hashlib.sha256(raw).hexdigest()
    def source(name,source_id,uri,license_id,owner,purposes):
        record={"evidence_kind":"rights_record","source_id":source_id,"uri":uri,"license":license_id,"copyright_owner":owner,"issuer":"Synthetic Phase 22 Rights Registry","issued_at":"2026-08-12T00:00:00Z"};path,sha=artifact(name,record);return {"source_id":source_id,"uri":uri,"license":license_id,"copyright_owner":owner,"allowed_purposes":purposes,"evidence_path":path,"evidence_sha256":sha}
    allowed={"manifest_id":"open-citations-study","purpose":"noncommercial-research","processing_jurisdiction":"CA","retention_days":30,"contains_personal_data":False,"sources":[source("crossref-rights.json","crossref-public-api","https://api.crossref.org/works","CC0-1.0","Crossref",["noncommercial-research","reproducibility"]),source("corpus-rights.json","curated-open-corpus","https://example.invalid/open-corpus","CC-BY-4.0","Synthetic Open Corpus Authors",["noncommercial-research"])]}
    unknown=json.loads(json.dumps(allowed));unknown["manifest_id"]="unknown-rights";unknown["sources"][1]=source("unknown-rights.json","curated-open-corpus","https://example.invalid/open-corpus","NOASSERTION","Synthetic Open Corpus Authors",["noncommercial-research"])
    personal=json.loads(json.dumps(allowed));personal["manifest_id"]="personal-records";personal["contains_personal_data"]=True
    consent={"evidence_kind":"consent_record","evidence_id":"consent-ledger:synthetic-7","status":"granted","purposes":["noncommercial-research"],"expires_at":"2099-01-01T00:00:00Z","revoked_at":None};consent_path,consent_sha=artifact("consent.json",consent);personal["consent"]={"evidence_id":"consent-ledger:synthetic-7","evidence_path":consent_path,"evidence_sha256":consent_sha}
    policy_path=out/"policy.json";policy_path.write_text(json.dumps(policy,indent=2)+"\n",encoding="utf-8")
    runs={}
    env=os.environ.copy()
    for name,value in (("allow",allowed),("unknown",unknown),("personal_review",personal)):
        manifest_path=out/f"{name}-manifest.json";manifest_path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")
        result_path=out/f"{name}-result.json"
        command=[sys.executable,str(repo_root/"harness/lib/legal_ip_risk.py"),"screen","--manifest",str(manifest_path),"--policy",str(policy_path),"--output",str(result_path)]
        process=subprocess.run(command,cwd=repo_root,env=env,capture_output=True,text=True,timeout=30)
        runs[name]={"command":command,"exit_code":process.returncode,"stdout_tail":process.stdout[-1000:],"stderr_tail":process.stderr[-1000:],"result":json.loads(result_path.read_text(encoding="utf-8"))}
    a,b,c=runs["allow"],runs["unknown"],runs["personal_review"]
    checks={"explicit_open_rights_allowed":a["exit_code"]==0 and a["result"]["decision"]=="allow" and a["result"]["admission_allowed"],"unknown_rights_fail_closed":b["exit_code"]==2 and b["result"]["decision"]=="deny" and not b["result"]["admission_allowed"],"consented_personal_data_still_requires_review":c["exit_code"]==2 and c["result"]["decision"]=="review_required" and not c["result"]["admission_allowed"],"raw_policy_manifest_and_evidence_are_hash_addressed":all(len(x["result"]["policy"]["sha256"])==64 and len(x["result"]["manifest"]["sha256"])==64 and all(len(f["evidence_sha256"])==64 for f in x["result"]["findings"] if f["evidence_path"]) for x in runs.values()),"provenance_rights_and_rule_ids_present":all({"source_provenance","source_rights","copyright_attribution"}<={f["check"] for f in x["result"]["findings"]} and all(f["rule_id"] for f in x["result"]["findings"]) for x in runs.values()),"legal_and_hosted_boundaries_explicit":all("not legal advice" in x["result"]["disclaimer"] and len(x["result"]["limitations"])==2 for x in runs.values())}
    evidence={"schema_version":"phase22.legal_ip_risk.v1","journey_id":"P22-REPAIR-069","run_id":run_id,"repo_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo_root,text=True).strip(),"production_entrypoint":"harness/lib/legal_ip_risk.py screen (also routed by solar-harness evolution legal-risk-screen)","assertions":checks,"runs":runs,"status":"PASS_WITH_KNOWN_LIMITATIONS" if all(checks.values()) else "FAIL","limitations":["This is deterministic local policy screening, not a jurisdiction-specific legal conclusion or legal-counsel approval.","Hosted-provider deletion/revocation, cross-channel enforcement, and external copyright ownership verification remain untested and out of scope."]}
    (out/"journey-result.json").write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
    worker=repo_root/".codex-tmp/phase22-worker-results/p22-069-legal-ip/result.json";worker.parent.mkdir(parents=True,exist_ok=True);worker.write_text(json.dumps({"issue_id":"P22-REPAIR-069","result":evidence["status"],"run_id":run_id,"journey_result":str(out/"journey-result.json"),"assertions":checks,"limitations":evidence["limitations"]},indent=2)+"\n",encoding="utf-8")
    assert all(checks.values()), out/"journey-result.json"
