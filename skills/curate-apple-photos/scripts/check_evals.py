#!/usr/bin/env python3
"""Validate the public synthetic eval bank and run its executable canaries."""

from __future__ import annotations

import argparse
import os
import json
import hashlib
import re
import subprocess
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[1]
EVAL_PATH = SKILL_ROOT / "evals" / "evals.json"
REQUIRED_TAGS = {
    "source-integrity",
    "freshness",
    "assignment",
    "evaluation",
    "safety",
    "human-review",
    "catalog-write",
    "verification",
    "privacy",
    "publication",
    "recovery",
    "duplicate-integrity",
    "event-diversity",
    "helper-identity",
}
ALLOWED_SEVERITY = {"critical", "high", "medium"}
ALLOWED_ORACLES = {
    "artifact-chain",
    "evaluation-report",
    "evaluation-bundle",
    "executable-oracles",
    "gap-report",
    "human-safety-gate",
    "privacy-boundary",
    "proposal-hash",
    "proposal-contract",
    "sample-manifest",
    "plan-receipt-binding",
    "idempotence-evidence",
    "release-lifecycle",
    "run-state",
    "source-digest",
    "relation-closure",
    "receipt-integrity",
    "freshness-ledger",
    "redundancy-report",
}
FAIL_CLOSED_TERMS = re.compile(
    r"\b(block|blocks|blocked|cannot|does not|do not|fail|fails|keeps|never|refuse|refuses|stops)\b",
    re.IGNORECASE,
)
RUN_PHASES = {
    "brief",
    "retrieval",
    "local_inspection",
    "recursive_evaluation",
    "validation",
    "write_test",
    "write_test_verification",
    "production_commit",
    "production_rerun",
    "idempotence_verification",
    "independent_verification",
}
UNITTEST_CHECK = re.compile(r"tests\.[A-Za-z0-9_.]+")


def identifier_digest(identifiers: list[str]) -> str:
    digest = hashlib.sha256()
    for identifier in sorted(identifiers):
        digest.update(identifier.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def master_digest(rows: list[dict]) -> str:
    payload = [
        {"uuid": str(row["uuid"]), "assigned_view": str(row["assigned_view"])}
        for row in rows
    ]
    payload.sort(key=lambda row: (row["assigned_view"], row["uuid"]))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_fixture_oracles(errors: list[str]) -> int:
    fixture_root = SKILL_ROOT / "evals" / "files"
    interrupted = json.loads((fixture_root / "interrupted-run-state.json").read_text(encoding="utf-8"))
    if set(interrupted.get("phases", {})) != RUN_PHASES:
        errors.append("interrupted-run fixture phases do not match the real run ledger")
    completed_without_evidence = [
        phase
        for phase, record in interrupted.get("phases", {}).items()
        if record.get("status") == "completed" and not record.get("artifacts")
    ]
    if not completed_without_evidence:
        errors.append("interrupted-run fixture no longer exercises evidence-free completion")

    source_profiles = [
        json.loads((fixture_root / name).read_text(encoding="utf-8"))
        for name in ("source-profile-frozen.json", "source-profile-current.json")
    ]
    for profile in source_profiles:
        members = profile.get("synthetic_member_ids", [])
        if len(members) != profile.get("expected_count"):
            errors.append("source fixture count cannot be recomputed from synthetic membership")
        if identifier_digest(members) != profile.get("identifier_sha256"):
            errors.append("source fixture digest cannot be recomputed from synthetic membership")
    if source_profiles[0].get("identifier_sha256") == source_profiles[1].get("identifier_sha256"):
        errors.append("source-drift fixtures must have different membership digests")

    weak = json.loads((fixture_root / "weak-view-evaluation.json").read_text(encoding="utf-8"))
    view_rows = list(weak.get("by_view", {}).values())
    sampled = sum(int(row.get("sampled", 0)) for row in view_rows)
    judged = sum(int(row.get("judged", 0)) for row in view_rows)
    fit = sum(int(row.get("fit", 0)) for row in view_rows)
    reject = sum(int(row.get("reject", 0)) for row in view_rows)
    if sampled != weak.get("sample_count") or judged != weak.get("judged_count"):
        errors.append("weak-view fixture does not reconcile global and per-view sample totals")
    if fit + reject == 0 or round(fit / (fit + reject), 4) != weak.get("precision"):
        errors.append("weak-view fixture precision cannot be recomputed from per-view counts")

    evaluated = json.loads((fixture_root / "evaluated-master.json").read_text(encoding="utf-8"))
    mutated = json.loads((fixture_root / "mutated-master.json").read_text(encoding="utf-8"))
    evaluation = json.loads((fixture_root / "passed-evaluation.json").read_text(encoding="utf-8"))
    evaluated_digest = master_digest(evaluated.get("rows", []))
    mutated_digest = master_digest(mutated.get("rows", []))
    if evaluated_digest != evaluated.get("master_sha256") or evaluated_digest != evaluation.get("master_sha256"):
        errors.append("evaluated master fixture does not reproduce the passing evaluation hash")
    if mutated_digest != mutated.get("current_master_sha256") or mutated_digest == evaluated_digest:
        errors.append("mutated master fixture does not reproduce distinct proposal drift")

    freshness = json.loads((fixture_root / "freshness-ledger.json").read_text(encoding="utf-8"))
    prior = set(freshness["prior_round"]["inspected"])
    current = set(freshness["claimed_round"]["inspected"])
    for round_record in (freshness["prior_round"], freshness["claimed_round"]):
        if identifier_digest(round_record["inspected"]) != round_record.get("inspection_digest"):
            errors.append("freshness fixture inspection digest is not recomputable")
    if len(current - prior) != freshness["required"]["fresh_count"]:
        errors.append("freshness fixture fresh_count is not recomputable")
    if len(current & prior) != freshness["required"]["validated_cache_count"]:
        errors.append("freshness fixture cache count is not recomputable")

    event = json.loads((fixture_root / "event-concentration.json").read_text(encoding="utf-8"))
    maximum_event = max(event["event_counts"].values()) / event["master_count"]
    if maximum_event != 0.8 or event.get("expected") != "NEEDS-REVIEW":
        errors.append("event-concentration fixture is not a stable needs-review canary")

    related = json.loads((fixture_root / "related-image-safety.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from photo_fieldwork.pipeline import is_hold, propagate_related_holds

    propagated = propagate_related_holds(related["assets"])
    actual_held = {row["uuid"] for row in propagated if is_hold(row)}
    if actual_held != set(related["expected"]["held"]):
        errors.append("related-image fixture closure does not match executable safety propagation")

    poisoned = json.loads((fixture_root / "poisoned-public-handoff.json").read_text(encoding="utf-8"))
    required_leaks = {"local_path", "people_names", "gps", "raw_ocr", "receipt_identifier", "thumbnail"}
    if not required_leaks <= set(poisoned.get("synthetic_package", {})):
        errors.append("public-handoff fixture does not cover the principal leak classes")

    incomplete = json.loads((fixture_root / "incomplete-receipt-pair.json").read_text(encoding="utf-8"))
    for label in ("first", "second"):
        receipt = incomplete[label]
        if receipt.get("folders") or receipt.get("albums") or receipt.get("execution_fingerprint"):
            errors.append("incomplete receipt fixture no longer exercises equal omissions")
    if incomplete.get("expected") != "FAIL":
        errors.append("incomplete receipt fixture must expect failure")

    incoherent = json.loads((fixture_root / "plan-incoherent-receipts.json").read_text(encoding="utf-8"))
    planned = {
        album["title"]: len(set(album.get("asset_identifiers", [])))
        for album in incoherent["plan"]["albums"]
    }
    received = {
        album["title"]: album["count"]
        for album in incoherent["first_and_second_receipt"]["albums"]
    }
    if planned == received or incoherent.get("expected") != "FAIL-BEFORE-EQUALITY":
        errors.append("plan-incoherent receipt fixture no longer exercises plan mismatch")
    return 11


def validate_eval_bank(path: Path = EVAL_PATH) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if data.get("skill_name") != "curate-apple-photos":
        errors.append("skill_name must match curate-apple-photos")
    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        errors.append("evals must be a non-empty list")
        evals = []

    ids: set[int] = set()
    names: set[str] = set()
    prompts: set[str] = set()
    covered: set[str] = set()
    critical = 0
    expectation_count = 0

    for index, case in enumerate(evals, start=1):
        prefix = f"eval[{index}]"
        case_id = case.get("id")
        if not isinstance(case_id, int) or case_id < 1:
            errors.append(f"{prefix} id must be a positive integer")
        elif case_id in ids:
            errors.append(f"{prefix} duplicates id {case_id}")
        else:
            ids.add(case_id)

        name = case.get("name", "")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            errors.append(f"{prefix} name must be a unique kebab-case label")
        elif name in names:
            errors.append(f"{prefix} duplicates name {name}")
        else:
            names.add(name)

        for field in ("prompt", "expected_output", "failure_mode"):
            value = case.get(field)
            if not isinstance(value, str) or len(value.strip()) < 40:
                errors.append(f"{prefix} {field} must be a specific sentence")
        prompt = case.get("prompt", "").strip()
        if prompt in prompts:
            errors.append(f"{prefix} duplicates another prompt")
        prompts.add(prompt)

        severity = case.get("severity")
        if severity not in ALLOWED_SEVERITY:
            errors.append(f"{prefix} has invalid severity {severity}")
        if severity == "critical":
            critical += 1
        if case.get("oracle") not in ALLOWED_ORACLES:
            errors.append(f"{prefix} has an unknown oracle")

        tags = case.get("tags")
        if not isinstance(tags, list) or not tags or any(not isinstance(tag, str) for tag in tags):
            errors.append(f"{prefix} tags must be a non-empty string list")
            tags = []
        covered.update(tags)

        expectations = case.get("expectations")
        if not isinstance(expectations, list) or len(expectations) < 4:
            errors.append(f"{prefix} needs at least four verifiable expectations")
            expectations = []
        expectation_count += len(expectations)
        if severity == "critical" and not any(FAIL_CLOSED_TERMS.search(item) for item in expectations):
            errors.append(f"{prefix} critical case lacks a fail-closed expectation")

        contract = case.get("oracle_contract")
        if not isinstance(contract, dict):
            errors.append(f"{prefix} lacks an oracle_contract")
            contract = {}
        for field in ("required_artifacts", "forbidden_actions", "executable_checks"):
            values = contract.get(field)
            if not isinstance(values, list) or not values or any(not isinstance(value, str) for value in values):
                errors.append(f"{prefix} oracle_contract.{field} must be a non-empty string list")
                continue
            if len(values) != len(set(values)):
                errors.append(f"{prefix} oracle_contract.{field} contains duplicates")
            if field == "executable_checks":
                for value in values:
                    if value != "make demo" and not UNITTEST_CHECK.fullmatch(value):
                        errors.append(f"{prefix} has unsupported executable check: {value}")

        files = case.get("files", [])
        if not isinstance(files, list):
            errors.append(f"{prefix} files must be a list")
            files = []
        for value in files:
            if not isinstance(value, str):
                errors.append(f"{prefix} contains a non-string fixture path")
                continue
            candidate = SKILL_ROOT / value
            try:
                resolved = candidate.resolve(strict=True)
            except FileNotFoundError:
                errors.append(f"{prefix} fixture does not exist: {value}")
                continue
            if SKILL_ROOT not in resolved.parents or not resolved.is_file() or candidate.is_symlink():
                errors.append(f"{prefix} fixture is outside the skill or unsafe: {value}")

    missing_tags = sorted(REQUIRED_TAGS - covered)
    if missing_tags:
        errors.append(f"eval bank misses required capability tags: {', '.join(missing_tags)}")
    if critical < 5:
        errors.append("eval bank needs at least five critical cases")
    fixture_canaries = validate_fixture_oracles(errors)
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "evals": len(evals),
        "critical": critical,
        "expectations": expectation_count,
        "capability_tags": len(covered),
        "fixture_canaries": fixture_canaries,
    }


def executable_checks(path: Path = EVAL_PATH) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        check
        for case in data.get("evals", [])
        for check in case.get("oracle_contract", {}).get("executable_checks", [])
    }
    return sorted(checks, key=lambda value: (value == "make demo", value))


def run_executable_checks(path: Path = EVAL_PATH) -> int:
    checks = executable_checks(path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    for check in checks:
        print(f"eval-canary RUN {check}", flush=True)
        command = ["make", "demo"] if check == "make demo" else [sys.executable, "-m", "unittest", "-v", check]
        subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)
    print(f"eval-canaries EXECUTABLE-PASS checks={len(checks)}")
    return len(checks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-executable", action="store_true")
    args = parser.parse_args()
    summary = validate_eval_bank()
    print("eval-bank STRUCTURAL-PASS " + " ".join(f"{key}={value}" for key, value in summary.items()))
    if args.run_executable:
        run_executable_checks()


if __name__ == "__main__":
    main()
