import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def test_p22_self_rag_bounded_reflection(repo_root: Path) -> None:
    run_id = "p22-self-rag-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = repo_root / "outputs/phase22-real-journeys" / run_id
    output_dir.mkdir(parents=True)
    fixture_dir = repo_root / "tests/journeys/phase22/fixtures/significant/self_rag"
    result_path, index_path = output_dir / "self-rag-result.json", output_dir / "retrieval-index.json"
    env = os.environ.copy()
    relative_output = result_path.relative_to(repo_root).as_posix()
    relative_index = index_path.relative_to(repo_root).as_posix()
    wrapper_args = ["./harness/solar-harness.sh", "evolution", "self-rag-evaluate",
                    "--request", "tests/journeys/phase22/fixtures/significant/self_rag/request.json",
                    "--corpus", "tests/journeys/phase22/fixtures/significant/self_rag/corpus",
                    "--index-state", relative_index, "--max-iterations", "3", "--top-k", "1",
                    "--output", relative_output]
    if os.name == "nt":
        drive = repo_root.drive.rstrip(":").lower()
        posix_repo = f"/mnt/{drive}/{repo_root.as_posix().split(':', 1)[1].lstrip('/')}"
        command = ["wsl.exe", "--cd", str(repo_root), "env", f"HARNESS_DIR={posix_repo}/harness",
                   "bash", *wrapper_args]
    else:
        env["HARNESS_DIR"] = str(repo_root / "harness")
        command = ["bash", *wrapper_args]
    process = subprocess.run(command, cwd=repo_root, env=env, capture_output=True, text=True, timeout=30)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    attack_dir = output_dir / "reviewer-attacks"
    moon_corpus = attack_dir / "moon-corpus"
    moon_corpus.mkdir(parents=True)
    (moon_corpus / "cats.json").write_text(json.dumps({"document_id": "cats", "text": "Domestic cats sleep for much of the day and hunt at dusk.",
        "provenance": {"uri": "local-review://cats"}}), encoding="utf-8")
    moon_request = attack_dir / "moon-request.json"
    moon_request.write_text(json.dumps({"question": "Are cats evidence that the Moon is cheese?", "required_claims": [
        {"claim_id": "moon", "text": "The Moon is cheese.", "required_exact_quote": "The Moon is made of cheese."}]}), encoding="utf-8")
    conflict_corpus = attack_dir / "conflict-corpus"
    conflict_corpus.mkdir()
    quote = "The trial measured a twelve percent nitrate decline."
    for suffix, uri, text in (("a", "local-review://trial/a", quote),
                              ("b", "local-review://trial/b", quote + " A later correction disputes this value.")):
        (conflict_corpus / f"result-{suffix}.json").write_text(json.dumps({"document_id": "trial-result", "text": text,
            "provenance": {"uri": uri}}), encoding="utf-8")
    conflict_request = attack_dir / "conflict-request.json"
    conflict_request.write_text(json.dumps({"question": "What nitrate decline was measured?", "required_claims": [
        {"claim_id": "nitrate", "text": quote, "required_exact_quote": quote}]}), encoding="utf-8")

    def attack(name: str, request: Path, corpus: Path, *, index: Path | None = None, top_k: int = 2):
        attack_result = attack_dir / f"{name}-result.json"
        attack_index = index or attack_dir / f"{name}-index.json"
        args = ["./harness/solar-harness.sh", "evolution", "self-rag-evaluate", "--request",
                request.relative_to(repo_root).as_posix(), "--corpus", corpus.relative_to(repo_root).as_posix(),
                "--index-state", attack_index.relative_to(repo_root).as_posix(), "--max-iterations", "2",
                "--top-k", str(top_k), "--output", attack_result.relative_to(repo_root).as_posix()]
        attack_command = (["wsl.exe", "--cd", str(repo_root), "env", f"HARNESS_DIR={posix_repo}/harness", "bash", *args]
                          if os.name == "nt" else ["bash", *args])
        attack_process = subprocess.run(attack_command, cwd=repo_root, env=env, capture_output=True, text=True, timeout=30)
        return attack_process, json.loads(attack_result.read_text(encoding="utf-8")), attack_result, attack_index

    moon_process, moon, moon_result, moon_index = attack("moon", moon_request, moon_corpus)
    conflict_process, conflict, conflict_result, conflict_index = attack("conflict", conflict_request, conflict_corpus)
    persistent_corpus = attack_dir / "persistent-corpus"
    persistent_corpus.mkdir()
    persistent_file = persistent_corpus / "result.json"
    persistent_request = attack_dir / "persistent-request.json"
    persistent_request.write_text(json.dumps({"question": "What nitrate decline was measured?", "required_claims": [
        {"claim_id": "nitrate", "text": quote, "required_exact_quote": quote}]}), encoding="utf-8")
    persistent_file.write_text(json.dumps({"document_id": "persistent-result", "text": quote,
        "provenance": {"uri": "local-review://persistent/a"}}), encoding="utf-8")
    persistent_index = attack_dir / "persistent-index.json"
    first_process, first_version, first_result, _ = attack(
        "persistent-v1", persistent_request, persistent_corpus, index=persistent_index, top_k=1)
    persistent_file.write_text(json.dumps({"document_id": "persistent-result", "text": quote + " The source was revised.",
        "provenance": {"uri": "local-review://persistent/b"}}), encoding="utf-8")
    second_process, second_version, second_result, _ = attack(
        "persistent-v2", persistent_request, persistent_corpus, index=persistent_index, top_k=1)
    all_evidence = [e for claim in result.get("answer", []) for e in claim.get("evidence", [])]
    assertions = {
        "production_solar_harness_exited_zero": process.returncode == 0,
        "real_local_index_written": index_path.exists() and result["corpus"]["retrieval_entrypoint"].endswith("LearningRetriever"),
        "bounded_reflection_accepted": result["status"] == "accepted" and result["iterations_used"] <= 3,
        "both_claims_answered": {x["claim_id"] for x in result["answer"]} == {"nitrogen", "richness"},
        "exact_spans_independently_bound": all(e["quote"] and e["end"] > e["start"] and
            hashlib.sha256(e["quote"].encode()).hexdigest() == e["quote_sha256"] for e in all_evidence),
        "immutable_versions_recorded": all(len(e["source_version_sha256"]) == 64 for e in all_evidence),
        "no_unsupported_answer": result["answer_policy"]["unsupported_answer_count"] == 0,
        "trace_hash_chained": all(row["previous_trace_sha256"] == ("0" * 64 if i == 0 else result["trace"][i-1]["trace_sha256"])
                                  for i, row in enumerate(result["trace"])),
        "moon_cheese_attack_abstained": moon_process.returncode == 0 and moon["status"] == "abstained" and moon["answer"] == [],
        "changed_document_attack_abstained": conflict_process.returncode == 0 and conflict["status"] == "abstained"
                                               and conflict["reasons"] == ["immutable_document_version_conflict"],
        "cross_run_persistent_lineage_attack_abstained": first_process.returncode == second_process.returncode == 0
            and first_version["status"] == "accepted" and second_version["status"] == "abstained"
            and second_version["reasons"] == ["immutable_document_version_conflict"]
            and len(second_version["corpus"]["persistent_document_lineage"]["persistent-result"]) == 2,
    }
    evidence = {
        "schema_version": "phase22.self_rag_journey.v2", "journey_id": "NT-memory-retrieval", "run_id": run_id,
        "repo_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip(),
        "production_command": command, "input": {"request": str(fixture_dir / "request.json"), "corpus": str(fixture_dir / "corpus")},
        "assertions": assertions, "exit_code": process.returncode, "stdout_tail": process.stdout[-2000:],
        "stderr_tail": process.stderr[-2000:], "artifacts": [str(result_path), str(index_path), str(moon_result),
            str(moon_index), str(conflict_result), str(conflict_index), str(first_result), str(second_result),
            str(persistent_index)],
        "status": "PASS_WITH_KNOWN_LIMITATIONS" if all(assertions.values()) else "FAIL",
        "limitations": result.get("limitations", []),
    }
    evidence_path = output_dir / "journey-result.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    assert all(assertions.values()), evidence_path
