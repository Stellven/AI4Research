#!/usr/bin/env python3
"""Deterministic fail-closed legal/IP/privacy risk screening; not legal advice."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any

ORDER = {"allow": 0, "review_required": 1, "deny": 2}

def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError(f"{path} must contain a JSON object")
    return value

def _hash(value: dict[str, Any]) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()

def _set(value: Any) -> set[str]:
    return {str(x).strip() for x in value if str(x).strip()} if isinstance(value,list) else set()

def screen(manifest: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    findings=[]
    def add(check: str, decision: str, reason: str, source: str):
        findings.append({"check":check,"decision":decision,"reason":reason,"source":source})
    version=str(policy.get("policy_version") or "").strip()
    if not version: add("policy_version","deny","policy_version is missing","policy.policy_version")
    purpose=str(manifest.get("purpose") or "").strip()
    if not purpose: add("purpose","deny","processing purpose is missing","manifest.purpose")
    elif purpose not in _set(policy.get("allowed_purposes")): add("purpose","deny",f"purpose {purpose!r} is not allowed","policy.allowed_purposes")
    else: add("purpose","allow",f"purpose {purpose!r} is policy-listed","policy.allowed_purposes")
    jurisdiction=str(manifest.get("processing_jurisdiction") or "").strip()
    if not jurisdiction: add("jurisdiction","deny","processing jurisdiction is missing","manifest.processing_jurisdiction")
    elif jurisdiction in _set(policy.get("allowed_processing_jurisdictions")): add("jurisdiction","allow",f"jurisdiction {jurisdiction!r} is policy-listed","policy.allowed_processing_jurisdictions")
    elif jurisdiction in _set(policy.get("review_processing_jurisdictions")): add("jurisdiction","review_required",f"jurisdiction {jurisdiction!r} requires human review","policy.review_processing_jurisdictions")
    else: add("jurisdiction","deny",f"jurisdiction {jurisdiction!r} is unknown or disallowed","policy.allowed_processing_jurisdictions")
    try:
        days,max_days=int(manifest.get("retention_days")),int(policy["max_retention_days"])
        add("retention","allow" if 0<=days<=max_days else "deny",f"retention is {days} days; policy maximum is {max_days}","policy.max_retention_days")
    except (KeyError,TypeError,ValueError): add("retention","deny","retention_days or maximum is missing/invalid","manifest.retention_days")
    personal=manifest.get("contains_personal_data")
    if not isinstance(personal,bool): add("personal_data","deny","contains_personal_data must be explicitly true or false","manifest.contains_personal_data")
    elif personal:
        consent=manifest.get("consent")
        if not isinstance(consent,dict) or consent.get("status")!="granted" or purpose not in _set(consent.get("purposes")) or not str(consent.get("evidence_id") or "").strip():
            add("personal_data","deny","consent is missing, revoked, lacks evidence, or does not cover purpose","manifest.consent")
        else: add("personal_data","review_required","recorded consent covers purpose; human privacy review remains required","manifest.consent")
    else: add("personal_data","allow","manifest explicitly declares no personal data","manifest.contains_personal_data")
    allowed,review,denied=_set(policy.get("allowed_licenses")),_set(policy.get("review_licenses")),_set(policy.get("denied_licenses"))
    sources=manifest.get("sources")
    if not isinstance(sources,list) or not sources: add("source_inventory","deny","at least one source is required","manifest.sources")
    else:
        for i,src in enumerate(sources):
            where=f"manifest.sources[{i}]"
            if not isinstance(src,dict): add("source_inventory","deny","source is not an object",where); continue
            sid,uri=str(src.get("source_id") or "").strip(),str(src.get("uri") or "").strip()
            license_id,owner=str(src.get("license") or "").strip(),str(src.get("copyright_owner") or "").strip()
            add("source_provenance","allow" if sid and uri else "deny","source_id and attributable URI are required",where)
            if not license_id or license_id.upper() in {"UNKNOWN","NOASSERTION","NONE"}: add("source_rights","deny","license/right is missing or unknown",f"{where}.license")
            elif license_id in denied: add("source_rights","deny",f"license {license_id!r} is denied","policy.denied_licenses")
            elif license_id in review: add("source_rights","review_required",f"license {license_id!r} requires human review","policy.review_licenses")
            elif license_id not in allowed: add("source_rights","deny",f"license {license_id!r} is unrecognized","policy.allowed_licenses")
            elif purpose not in _set(src.get("allowed_purposes")): add("source_rights","deny",f"rights do not include purpose {purpose!r}",f"{where}.allowed_purposes")
            else: add("source_rights","allow",f"license {license_id!r} and purpose are policy-compatible",where)
            add("copyright_attribution","allow" if owner else "deny","rights holder must be recorded",f"{where}.copyright_owner")
    decision=max((x["decision"] for x in findings),key=ORDER.get)
    return {"schema_version":"solar.legal_ip_risk_screen.v1","decision":decision,"admission_allowed":decision=="allow","policy":{"version":version,"sha256":_hash(policy)},"manifest":{"id":str(manifest.get("manifest_id") or ""),"sha256":_hash(manifest)},"findings":findings,"summary":{x:sum(f["decision"]==x for f in findings) for x in ORDER},"disclaimer":"Engineering risk screen only; not legal advice or legal approval. Review-required and deny decisions block automatic admission.","limitations":["No jurisdiction-specific legal conclusion, copyright ownership verification, or legal-counsel approval.","No hosted-provider deletion, consent revocation propagation, or cross-channel enforcement."]}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("screen",nargs="?");ap.add_argument("--manifest",required=True,type=Path);ap.add_argument("--policy",required=True,type=Path);ap.add_argument("--output",required=True,type=Path);a=ap.parse_args()
    try: result=screen(_load(a.manifest.resolve()),_load(a.policy.resolve()))
    except Exception as exc: result={"schema_version":"solar.legal_ip_risk_screen.v1","decision":"deny","admission_allowed":False,"findings":[{"check":"input","decision":"deny","reason":str(exc),"source":"cli"}],"disclaimer":"Engineering risk screen only; not legal advice or legal approval."}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");print(json.dumps(result,ensure_ascii=False));return 0 if result["decision"]=="allow" else 2
if __name__=="__main__": raise SystemExit(main())
