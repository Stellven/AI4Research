#!/usr/bin/env python3
"""Fail-closed, evidence-backed legal/IP/privacy risk screening; not legal advice."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ORDER = {"allow": 0, "review_required": 1, "deny": 2}
HEX = set("0123456789abcdef")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _load(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _canonical_hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _string(value: Any) -> str:
    return value.strip() if type(value) is str else ""


def _strings(value: Any) -> set[str]:
    if not isinstance(value, list) or any(type(item) is not str or not item.strip() for item in value):
        return set()
    return {item.strip() for item in value}


def _sha(value: Any) -> str:
    text = _string(value).lower()
    return text if len(text) == 64 and all(char in HEX for char in text) else ""


def _evidence(path_value: Any, expected_hash: Any) -> tuple[Path | None, dict[str, Any] | None, str, str]:
    text = _string(path_value)
    expected = _sha(expected_hash)
    if not text or not expected:
        return None, None, "", "canonical evidence_path and 64-character evidence_sha256 are required"
    path = Path(text)
    if not path.is_absolute():
        return None, None, "", "evidence_path must be absolute"
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return None, None, "", "evidence artifact does not exist"
    if path != resolved or path.is_symlink() or not path.is_file():
        return None, None, "", "evidence_path must name a canonical, regular, non-symlink file"
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        return path, None, actual, "evidence SHA256 does not match raw bytes"
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return path, None, actual, f"evidence artifact is not duplicate-free JSON: {exc}"
    if not isinstance(value, dict):
        return path, None, actual, "evidence artifact must contain an object"
    return path, value, actual, ""


def _instant(value: Any) -> datetime | None:
    text = _string(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def screen(
    manifest: dict[str, Any],
    policy: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    manifest_raw_sha256: str | None = None,
    policy_path: Path | None = None,
    policy_raw_sha256: str | None = None,
    output_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    findings: list[dict[str, Any]] = []
    manifest_ref = str(manifest_path) if manifest_path else "in-memory"
    manifest_hash = manifest_raw_sha256 or _canonical_hash(manifest)

    def add(check: str, decision: str, reason: str, source: str, *, source_path: Path | None = None, source_hash: str = "") -> None:
        findings.append({"rule_id": f"solar.legal_ip.{check}.v1", "check": check, "decision": decision, "reason": reason, "source": source, "manifest_path": manifest_ref, "manifest_sha256": manifest_hash, "evidence_path": str(source_path) if source_path else "", "evidence_sha256": source_hash})

    manifest_id = _string(manifest.get("manifest_id"))
    add("manifest_id", "allow" if manifest_id else "deny", "manifest_id is recorded" if manifest_id else "manifest_id is required", "manifest.manifest_id")
    version = _string(policy.get("policy_version"))
    add("policy_version", "allow" if version else "deny", "policy version is recorded" if version else "policy_version is missing", "policy.policy_version")
    purpose = _string(manifest.get("purpose"))
    allowed_purposes = _strings(policy.get("allowed_purposes"))
    if not purpose or not allowed_purposes:
        add("purpose", "deny", "purpose or strictly typed policy purpose list is missing", "manifest.purpose")
    elif purpose not in allowed_purposes:
        add("purpose", "deny", f"purpose {purpose!r} is not allowed", "policy.allowed_purposes")
    else:
        add("purpose", "allow", f"purpose {purpose!r} is policy-listed", "policy.allowed_purposes")
    jurisdiction = _string(manifest.get("processing_jurisdiction"))
    allowed_jurisdictions = _strings(policy.get("allowed_processing_jurisdictions"))
    review_jurisdictions = _strings(policy.get("review_processing_jurisdictions"))
    if jurisdiction in allowed_jurisdictions and jurisdiction:
        add("jurisdiction", "allow", f"jurisdiction {jurisdiction!r} is policy-listed", "policy.allowed_processing_jurisdictions")
    elif jurisdiction in review_jurisdictions and jurisdiction:
        add("jurisdiction", "review_required", f"jurisdiction {jurisdiction!r} requires human review", "policy.review_processing_jurisdictions")
    else:
        add("jurisdiction", "deny", "jurisdiction is missing, unknown, or disallowed", "manifest.processing_jurisdiction")
    days, max_days = manifest.get("retention_days"), policy.get("max_retention_days")
    if type(days) is not int or type(max_days) is not int:
        add("retention", "deny", "retention values must be exact JSON integers (booleans, floats, and strings are rejected)", "manifest.retention_days")
    else:
        add("retention", "allow" if 0 <= days <= max_days else "deny", f"retention is {days} days; policy maximum is {max_days}", "policy.max_retention_days")

    referenced_paths: set[Path] = set()
    personal = manifest.get("contains_personal_data")
    if type(personal) is not bool:
        add("personal_data", "deny", "contains_personal_data must be exactly true or false", "manifest.contains_personal_data")
    elif personal:
        consent = manifest.get("consent")
        if not isinstance(consent, dict):
            add("personal_data", "deny", "personal data requires a consent object", "manifest.consent")
        else:
            path, record, actual, error = _evidence(consent.get("evidence_path"), consent.get("evidence_sha256"))
            if path:
                referenced_paths.add(path)
            valid = not error and record is not None
            if valid:
                expires = _instant(record.get("expires_at"))
                valid = (
                    record.get("evidence_kind") == "consent_record"
                    and _string(record.get("evidence_id")) == _string(consent.get("evidence_id"))
                    and record.get("status") == "granted"
                    and record.get("revoked_at") is None
                    and purpose in _strings(record.get("purposes"))
                    and expires is not None and expires > now
                )
                error = "" if valid else "consent evidence is expired, revoked, malformed, or does not cover purpose"
            add("personal_data", "review_required" if valid else "deny", "verified consent artifact covers purpose; human privacy review remains required" if valid else error, "manifest.consent", source_path=path, source_hash=actual)
    else:
        add("personal_data", "allow", "manifest explicitly declares no personal data", "manifest.contains_personal_data")

    allowed, review, denied = _strings(policy.get("allowed_licenses")), _strings(policy.get("review_licenses")), _strings(policy.get("denied_licenses"))
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        add("source_inventory", "deny", "at least one source is required", "manifest.sources")
    else:
        for index, source in enumerate(sources):
            where = f"manifest.sources[{index}]"
            if not isinstance(source, dict):
                add("source_inventory", "deny", "source is not an object", where); continue
            sid, uri = _string(source.get("source_id")), _string(source.get("uri"))
            license_id, owner = _string(source.get("license")), _string(source.get("copyright_owner"))
            uri_valid = bool(uri and urlparse(uri).scheme.lower() in {"https", "http", "doi"} and urlparse(uri).netloc)
            path, record, actual, error = _evidence(source.get("evidence_path"), source.get("evidence_sha256"))
            if path:
                referenced_paths.add(path)
            evidence_matches = not error and record is not None
            if evidence_matches:
                evidence_matches = (
                    record.get("evidence_kind") == "rights_record"
                    and _string(record.get("source_id")) == sid
                    and _string(record.get("uri")) == uri
                    and _string(record.get("license")) == license_id
                    and _string(record.get("copyright_owner")) == owner
                    and _string(record.get("issuer")) != ""
                    and _instant(record.get("issued_at")) is not None
                )
                error = "" if evidence_matches else "structured rights evidence does not match source fields or lacks issuer/issued_at"
            add("source_provenance", "allow" if sid and uri_valid and evidence_matches else "deny", "source URI and structured evidence artifact are verified" if sid and uri_valid and evidence_matches else (error or "source_id or allowed URI scheme is missing"), where, source_path=path, source_hash=actual)
            if not evidence_matches:
                add("source_rights", "deny", error or "rights evidence is unavailable", where, source_path=path, source_hash=actual)
            elif not license_id or license_id.upper() in {"UNKNOWN", "NOASSERTION", "NONE"}:
                add("source_rights", "deny", "license/right is missing or unknown", f"{where}.license", source_path=path, source_hash=actual)
            elif license_id in denied:
                add("source_rights", "deny", f"license {license_id!r} is denied", "policy.denied_licenses", source_path=path, source_hash=actual)
            elif license_id in review:
                add("source_rights", "review_required", f"license {license_id!r} requires human review", "policy.review_licenses", source_path=path, source_hash=actual)
            elif license_id not in allowed or purpose not in _strings(source.get("allowed_purposes")):
                add("source_rights", "deny", "license is unrecognized or rights exclude declared purpose", where, source_path=path, source_hash=actual)
            else:
                add("source_rights", "allow", f"license {license_id!r} and purpose are policy-compatible", where, source_path=path, source_hash=actual)
            add("copyright_attribution", "allow" if owner and evidence_matches else "deny", "rights holder is backed by hashed structured evidence" if owner and evidence_matches else "rights holder evidence is missing or invalid", f"{where}.copyright_owner", source_path=path, source_hash=actual)

    if output_path is not None:
        output_resolved = output_path.resolve()
        protected = {item.resolve() for item in (manifest_path, policy_path) if item is not None} | {item.resolve() for item in referenced_paths}
        if output_resolved in protected:
            add("output_alias", "deny", "output must not alias manifest, policy, or evidence input", "cli.output", source_path=output_resolved)
    decision = max((item["decision"] for item in findings), key=ORDER.get)
    return {"schema_version":"solar.legal_ip_risk_screen.v1","decision":decision,"admission_allowed":decision=="allow","policy":{"version":version,"path":str(policy_path) if policy_path else "in-memory","sha256":policy_raw_sha256 or _canonical_hash(policy)},"manifest":{"id":manifest_id,"path":manifest_ref,"sha256":manifest_hash},"findings":findings,"summary":{name:sum(item["decision"]==name for item in findings) for name in ORDER},"disclaimer":"Engineering risk screen only; not legal advice or legal approval. Review-required and deny decisions block automatic admission.","limitations":["No jurisdiction-specific legal conclusion, external copyright ownership verification, or legal-counsel approval.","No hosted-provider deletion, consent revocation propagation, or cross-channel enforcement."]}


def _atomic_write(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY); os.fsync(directory); os.close(directory)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("screen",nargs="?"); parser.add_argument("--manifest",required=True,type=Path); parser.add_argument("--policy",required=True,type=Path); parser.add_argument("--output",required=True,type=Path); args=parser.parse_args()
    manifest_path, policy_path, output_path = args.manifest.resolve(), args.policy.resolve(), args.output.resolve()
    input_alias = output_path in {manifest_path, policy_path}
    try:
        manifest, manifest_hash = _load(manifest_path); policy, policy_hash = _load(policy_path)
        result=screen(manifest,policy,manifest_path=manifest_path,manifest_raw_sha256=manifest_hash,policy_path=policy_path,policy_raw_sha256=policy_hash,output_path=output_path)
    except Exception as exc:
        result={"schema_version":"solar.legal_ip_risk_screen.v1","decision":"deny","admission_allowed":False,"findings":[{"rule_id":"solar.legal_ip.input.v1","check":"input","decision":"deny","reason":str(exc),"source":"cli","manifest_path":str(manifest_path),"manifest_sha256":"","evidence_path":"","evidence_sha256":""}],"disclaimer":"Engineering risk screen only; not legal advice or legal approval."}
    protected={manifest_path,policy_path}
    if "manifest" in locals():
        for source in manifest.get("sources",[]) if isinstance(manifest.get("sources"),list) else []:
            if isinstance(source,dict) and _string(source.get("evidence_path")): protected.add(Path(source["evidence_path"]).resolve())
        consent=manifest.get("consent") if "manifest" in locals() else None
        if isinstance(consent,dict) and _string(consent.get("evidence_path")): protected.add(Path(consent["evidence_path"]).resolve())
    if not input_alias and output_path not in protected:
        if output_path.exists(): output_path.unlink()
        _atomic_write(output_path,result)
    print(json.dumps(result,ensure_ascii=False)); return 0 if result.get("decision")=="allow" else 2

if __name__=="__main__": raise SystemExit(main())
