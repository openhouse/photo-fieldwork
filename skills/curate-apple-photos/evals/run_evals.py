#!/usr/bin/env python3
"""Run synthetic skill-behavior evals through Codex and grade the outputs."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from validate_response import ROOT, grade_response, read_json, suite_index


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(root: Path, excluded_names: set[str] | None = None) -> str:
    excluded_names = excluded_names or set()
    digest = hashlib.sha256()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        relative = path.relative_to(root)
        if any(part in excluded_names for part in relative.parts):
            continue
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def parse_ids(value: str, available: set[int]) -> list[int]:
    if value == "all":
        return sorted(available)
    selected = [int(part) for part in value.split(",") if part]
    if not selected:
        raise ValueError("at least one eval ID is required")
    unknown = set(selected) - available
    if unknown:
        raise ValueError(f"unknown eval IDs: {sorted(unknown)}")
    return selected


def prompt_for(eval_id: int, item: dict[str, Any], skill_path: Path, fixture_path: Path) -> str:
    return f"""You are running a synthetic behavior evaluation for a local photo-curation skill.

Read and follow the skill at `{skill_path / 'SKILL.md'}`. Read the complete synthetic evidence bundle at `{fixture_path}` before deciding. Do not inspect `evals.json`, `rubric.json`, grader code, or any other skill version. Do not use the network. Do not access Apple Photos or any private archive. Do not mutate anything.

Task from the user:
{item['prompt']}

Return one JSON object matching the supplied schema. Set `eval_id` to {eval_id}. Every finding and supported claim must cite exact evidence `id` values from the bundle. Use `mutates_photos: false` for analysis, repair, review, or reporting actions. BLOCKED means the requested transition cannot safely advance; READY_FOR_NEXT_PHASE means the described correction can advance without claiming completion; EDITOR_FIELD_VERIFIED means the attached evidence closes every editor-field gate. Publication is a separate destination-specific state.

Role-play is optional unless the task requests it. When requested, label each speaker and use `delegated-editorial-inference`; never manufacture first-hand memory, testimony, or endorsement.
"""


def run_one(
    eval_id: int,
    run_number: int,
    item: dict[str, Any],
    rubric: dict[str, Any],
    source_skill: Path,
    output_root: Path,
    codex_bin: str,
    model: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    run_dir = output_root / f"eval-{eval_id:02d}-run-{run_number:02d}"
    input_dir = run_dir / "input"
    copied_skill = input_dir / "skill"
    run_dir.mkdir(parents=True, exist_ok=True)
    if input_dir.exists():
        shutil.rmtree(input_dir)
    shutil.copytree(source_skill, copied_skill, ignore=shutil.ignore_patterns("evals", "__pycache__", "*.pyc"))

    source_fixture = ROOT.parent / item["files"][0]
    fixture_path = input_dir / "scenario.json"
    shutil.copy2(source_fixture, fixture_path)
    prompt = prompt_for(eval_id, item, copied_skill, fixture_path)
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    response_path = run_dir / "response.json"
    transcript_path = run_dir / "transcript.jsonl"
    grading_path = run_dir / "grading.json"
    for stale_path in (response_path, transcript_path, grading_path):
        stale_path.unlink(missing_ok=True)

    command = [
        codex_bin,
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(input_dir),
        "--output-schema",
        str(ROOT / "response.schema.json"),
        "--output-last-message",
        str(response_path),
        "--json",
    ]
    if model:
        command.extend(["--model", model])
    command.append(prompt)

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        completed = subprocess.CompletedProcess(command, 124, stdout, stderr + "\nexecutor timed out\n")
    duration = time.monotonic() - started
    transcript_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")

    if completed.returncode != 0 or not response_path.is_file():
        grading = {
            "expectations": [],
            "summary": {"passed": 0, "failed": 1, "total": 1, "pass_rate": 0.0},
            "error": f"executor failed with exit code {completed.returncode}",
        }
    else:
        try:
            response = read_json(response_path)
            fixture = read_json(fixture_path)
            grading = grade_response(eval_id, response, fixture, rubric)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            grading = {
                "expectations": [],
                "summary": {"passed": 0, "failed": 1, "total": 1, "pass_rate": 0.0},
                "error": f"response could not be graded: {exc}",
            }

    grading["timing"] = {"executor_duration_seconds": round(duration, 3)}
    grading_path.write_text(json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "eval_id": eval_id,
        "run_number": run_number,
        "name": item["name"],
        "pass_rate": grading["summary"]["pass_rate"],
        "passed": grading["summary"]["passed"],
        "failed": grading["summary"]["failed"],
        "total": grading["summary"]["total"],
        "duration_seconds": round(duration, 3),
        "executor_exit_code": completed.returncode,
        "prompt_sha256": file_sha256(prompt_path),
        "response_sha256": file_sha256(response_path) if response_path.is_file() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--evals", default="all", help="Comma-separated IDs or all")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--runs-per-eval", type=int, default=1)
    parser.add_argument("--model")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    evals_path = ROOT / "evals.json"
    evals = suite_index(evals_path)
    rubrics = read_json(ROOT / "rubric.json")["evals"]
    try:
        selected = parse_ids(args.evals, set(evals))
    except ValueError as exc:
        parser.error(str(exc))
    skill_path = args.skill.resolve()
    if not (skill_path / "SKILL.md").is_file():
        parser.error(f"skill does not contain SKILL.md: {skill_path}")
    output_root = args.workspace / args.label
    output_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    if args.runs_per_eval < 1:
        parser.error("--runs-per-eval must be at least 1")
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be at least 1")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        futures = {
            executor.submit(
                run_one,
                eval_id,
                run_number,
                evals[eval_id],
                rubrics[str(eval_id)],
                skill_path,
                output_root,
                args.codex_bin,
                args.model,
                args.timeout_seconds,
            ): (eval_id, run_number)
            for eval_id in selected
            for run_number in range(1, args.runs_per_eval + 1)
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"eval={result['eval_id']} pass_rate={result['pass_rate']:.3f} "
                f"duration_seconds={result['duration_seconds']:.3f}"
            )

    results.sort(key=lambda item: (item["eval_id"], item["run_number"]))
    passed = sum(item["passed"] for item in results)
    total = sum(item["total"] for item in results)
    summary = {
        "skill_name": "curate-apple-photos",
        "label": args.label,
        "skill_path": str(skill_path),
        "model": args.model or "codex-default",
        "eval_ids": selected,
        "runs_per_eval": args.runs_per_eval,
        "timeout_seconds": args.timeout_seconds,
        "skill_tree_sha256": tree_sha256(skill_path, {"evals", "__pycache__"}),
        "suite_sha256": tree_sha256(ROOT, {"__pycache__", "history.json"}),
        "results": results,
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": passed / total if total else 0.0,
        },
    }
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"summary_pass_rate={summary['summary']['pass_rate']:.3f}")
    return 0 if summary["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
