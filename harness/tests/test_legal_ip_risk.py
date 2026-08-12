from harness.lib.legal_ip_risk import screen

def policy(): return {"policy_version":"test-1","allowed_purposes":["research"],"allowed_processing_jurisdictions":["CA"],"review_processing_jurisdictions":["US"],"max_retention_days":30,"allowed_licenses":["CC0-1.0","CC-BY-4.0"],"review_licenses":["CC-BY-SA-4.0"],"denied_licenses":["ARR"]}
def manifest(): return {"manifest_id":"m1","purpose":"research","processing_jurisdiction":"CA","retention_days":14,"contains_personal_data":False,"sources":[{"source_id":"open-dataset","uri":"https://example.invalid/dataset","license":"CC-BY-4.0","copyright_owner":"Example Research Group","allowed_purposes":["research"]}]}
def test_allows_explicit_compatible_rights():
 r=screen(manifest(),policy());assert r["decision"]=="allow" and r["admission_allowed"] and len(r["policy"]["sha256"])==64
def test_unknown_license_fails_closed():
 m=manifest();m["sources"][0]["license"]="NOASSERTION";r=screen(m,policy());assert r["decision"]=="deny" and not r["admission_allowed"]
def test_incompatible_purpose_is_denied():
 m=manifest();m["purpose"]="commercial-training";assert screen(m,policy())["decision"]=="deny"
def test_personal_data_requires_consent_and_review():
 m=manifest();m["contains_personal_data"]=True;assert screen(m,policy())["decision"]=="deny";m["consent"]={"status":"granted","purposes":["research"],"evidence_id":"consent-17"};r=screen(m,policy());assert r["decision"]=="review_required" and not r["admission_allowed"]
def test_review_license_and_jurisdiction_never_auto_admit():
 m=manifest();m["processing_jurisdiction"]="US";m["sources"][0]["license"]="CC-BY-SA-4.0";r=screen(m,policy());assert r["decision"]=="review_required" and not r["admission_allowed"]
def test_missing_provenance_owner_and_retention_fail_closed():
 m=manifest();m["retention_days"]=90;m["sources"][0].pop("uri");m["sources"][0].pop("copyright_owner");r=screen(m,policy());assert r["decision"]=="deny";assert {f["check"] for f in r["findings"] if f["decision"]=="deny"}>={"retention","source_provenance","copyright_attribution"}
