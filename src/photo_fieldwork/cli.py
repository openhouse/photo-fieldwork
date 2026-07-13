from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .contracts import load_source_profile, read_json, write_json
from .pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate, write_csv
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .safety import apply_safety_policy
from .workflow import (
    apply_feedback,
    build_inspection_ledger,
    completion_report,
    duplicate_audit,
    lint_catalog_plan,
    read_jsonl,
    transition_run_state,
    write_jsonl,
)


def emit(args: argparse.Namespace, data: object, message: str) -> None:
    output_format = getattr(args, "format", "text")
    if output_format == "silent":
        return
    if output_format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(message)


def markdown_report(title: str, data: dict) -> str:
    lines = [f"# {title}", ""]
    for key, value in data.items():
        if isinstance(value, dict):
            lines.extend([f"## {key.replace('_', ' ').title()}", ""])
            lines.extend(f"- `{child}`: {amount}" for child, amount in value.items())
            lines.append("")
        else:
            lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    return "\n".join(lines) + "\n"


def command_select(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    inventory = read_csv(args.inventory)
    master, holds, summary = select(inventory, config)
    output = args.output
    write_csv(output / "manifests" / "proposed-master.csv", master)
    write_csv(output / "manifests" / "hold-sensitive.csv", holds)
    reports = output / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "selection-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (reports / "selection-summary.md").write_text(markdown_report("Selection summary", summary), encoding="utf-8")
    emit(args, summary, f"selected {len(master)}; held {len(holds)}; wrote {output}")
    return 0


def command_sample(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    sample = make_sample(master, args.per_view, args.seed)
    write_csv(args.output, sample)
    emit(args, {"sample_count": len(sample), "output": str(args.output)}, f"wrote {len(sample)} evaluation rows to {args.output}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    report, passed = evaluate(feedback, config)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    emit(args, report, f"evaluation {'PASS' if passed else 'FAIL'}: precision={report['precision']}, coverage={report['coverage']}")
    return 0 if passed else 2


def command_validate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    errors, metrics = validate(master, holds, config)
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(metrics)
    report["errors"] = errors
    (args.output / "validation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "validation-report.md").write_text(markdown_report("Validation report", report), encoding="utf-8")
    emit(args, report, f"validation {metrics['status']}")
    return 0 if not errors else 2


def command_plan(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    source_count: int | None
    source_fingerprint: str | None
    if getattr(args, "source_profile", None):
        profile = load_source_profile(args.source_profile)
        source_title = str(profile["title"])
        source_identifier = str(profile["id"])
        source_count = int(profile["expected_count"])
        source_fingerprint = str(profile["fingerprint"])
    else:
        if not args.source_title or not args.source_identifier:
            raise ValueError("provide --source-profile or both --source-title and --source-identifier")
        source_title = args.source_title
        source_identifier = args.source_identifier
        source_count = getattr(args, "source_count", None)
        source_fingerprint = None
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        source_title,
        source_identifier,
        source_count,
        source_fingerprint,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    emit(args, plan, f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_source_check(args: argparse.Namespace) -> int:
    profile = load_source_profile(args.source_profile)
    emit(args, profile, f"source profile PASS: {profile['id']} ({profile['expected_count']})")
    return 0


def command_safety(args: argparse.Namespace) -> int:
    rows = read_csv(args.inventory)
    policy = read_json(args.policy)
    updated, decisions = apply_safety_policy(rows, policy)
    write_csv(args.output, updated)
    write_jsonl(args.decisions, decisions)
    report = {
        "rows": len(updated),
        "decisions": len(decisions),
        "holds": sum(row.get("safety_status") == "hold" for row in updated),
        "needs_review": sum(row.get("safety_status") == "needs-review" for row in updated),
    }
    emit(args, report, f"applied {len(decisions)} relational safety decisions")
    return 0


def command_inspection_ledger(args: argparse.Namespace) -> int:
    entries, report = build_inspection_ledger(read_json(args.batch_manifest))
    write_jsonl(args.output, entries)
    write_json(args.report, report)
    emit(args, report, f"indexed {report['unique_assets']} unique inspections")
    return 0 if report["status"] == "PASS" else 2


def command_duplicate_audit(args: argparse.Namespace) -> int:
    rows = read_csv(args.inventory)
    audit, report = duplicate_audit(rows)
    write_csv(args.output, audit, ["uuid", "duplicate_cluster", "match_method", "review_status"])
    write_json(args.report, report)
    emit(args, report, f"found {report['duplicate_clusters']} cross-UUID duplicate clusters")
    return 2 if report["unresolved"] else 0


def command_apply_feedback(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    candidates = read_csv(args.candidates)
    feedback = read_csv(args.feedback)
    next_master, holds, decisions, replacements = apply_feedback(master, candidates, feedback, config)
    manifests = args.output / "manifests"
    write_csv(manifests / "proposed-master.csv", next_master)
    write_csv(manifests / "hold-sensitive.csv", holds)
    write_jsonl(manifests / "decision-ledger.jsonl", decisions)
    write_csv(manifests / "replacement-review.csv", replacements)
    report = {
        "master_count": len(next_master),
        "hold_count": len(holds),
        "decisions": len(decisions),
        "pending_replacement_reviews": len(replacements),
    }
    write_json(args.output / "reports" / "feedback-application.json", report)
    emit(args, report, f"applied feedback; {len(replacements)} replacements require review")
    return 2 if replacements else 0


def command_lint_plan(args: argparse.Namespace) -> int:
    plan = read_json(args.plan)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    config = read_config(args.config)
    profile = load_source_profile(args.source_profile) if args.source_profile else None
    inspected_ids = None
    if args.inspection_ledger:
        inspected_ids = {row["uuid"] for row in read_jsonl(args.inspection_ledger)}
    report = lint_catalog_plan(
        plan,
        master,
        holds,
        config,
        inspected_ids=inspected_ids,
        source_profile=profile,
    )
    write_json(args.output, report)
    emit(args, report, f"plan lint {report['status']}: {len(report['errors'])} errors")
    return 0 if report["status"] == "PASS" else 2


def command_state(args: argparse.Namespace) -> int:
    state = transition_run_state(args.run_state, args.phase, args.status, args.evidence)
    emit(args, state, f"{args.phase}: {args.status}")
    return 0


def command_report(args: argparse.Namespace) -> int:
    report, markdown = completion_report(args.run)
    write_json(args.output.with_suffix(".json"), report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    emit(args, report, f"wrote artifact-derived completion report to {args.output}")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    workspace = args.workspace.resolve()
    inventory = workspace / "inventory" / "practice.csv"
    config = workspace / "config.json"
    create_demo_inventory(inventory)
    config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "config" / "starter.json", config)
    write_demo_readme(workspace / "README.md")
    command_select(argparse.Namespace(config=config, inventory=inventory, output=workspace, format="silent"))
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(
        argparse.Namespace(
            master=workspace / "manifests" / "proposed-master.csv",
            output=sample_path,
            per_view=3,
            seed=20260710,
            format="silent",
        )
    )
    practice_feedback(sample_path)
    eval_code = command_evaluate(argparse.Namespace(config=config, feedback=sample_path, output=workspace / "reports", format="silent"))
    validation_code = command_validate(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            holds=workspace / "manifests" / "hold-sensitive.csv",
            output=workspace / "reports",
            format="silent",
        )
    )
    command_plan(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            plan_id="synthetic-practice-plan",
            source_title="Synthetic practice corpus",
            source_identifier="SYNTHETIC-ONLY",
            output=workspace / "manifests" / "catalog-plan.json",
            format="silent",
        )
    )
    emit(
        args,
        {"workspace": str(workspace), "evaluation_exit": eval_code, "validation_exit": validation_code},
        f"practice workspace ready: {workspace}",
    )
    return max(eval_code, validation_code)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="photo-fieldwork", description="Build an auditable editor-ready photo corpus")
    root.add_argument("--format", choices=("text", "json"), default="text")
    sub = root.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run the complete workflow on synthetic records")
    demo.add_argument("--workspace", type=Path, default=Path("runs/practice"))
    demo.set_defaults(func=command_demo)

    selection = sub.add_parser("select", help="select a proposed master and safety holds")
    selection.add_argument("--inventory", type=Path, required=True)
    selection.add_argument("--config", type=Path, required=True)
    selection.add_argument("--output", type=Path, required=True)
    selection.set_defaults(func=command_select)

    sample = sub.add_parser("sample", help="make a score-stratified evaluation sample")
    sample.add_argument("--master", type=Path, required=True)
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--per-view", type=int, default=3)
    sample.add_argument("--seed", type=int, default=20260710)
    sample.set_defaults(func=command_sample)

    evaluation = sub.add_parser("evaluate", help="measure labeled evaluation feedback")
    evaluation.add_argument("--feedback", type=Path, required=True)
    evaluation.add_argument("--config", type=Path, required=True)
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.set_defaults(func=command_evaluate)

    validation = sub.add_parser("validate", help="validate a proposed master against invariants")
    validation.add_argument("--master", type=Path, required=True)
    validation.add_argument("--holds", type=Path, required=True)
    validation.add_argument("--config", type=Path, required=True)
    validation.add_argument("--output", type=Path, required=True)
    validation.set_defaults(func=command_validate)

    plan = sub.add_parser("plan", help="build an adapter-neutral, membership-only catalog plan")
    plan.add_argument("--master", type=Path, required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--plan-id", required=True)
    plan.add_argument("--source-title")
    plan.add_argument("--source-identifier")
    plan.add_argument("--source-count", type=int)
    plan.add_argument("--source-profile", type=Path)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    source = sub.add_parser("source-check", help="validate and fingerprint an active source profile")
    source.add_argument("--source-profile", type=Path, required=True)
    source.set_defaults(func=command_source_check)

    safety = sub.add_parser("safety", help="propagate declarative relational safety rules")
    safety.add_argument("--inventory", type=Path, required=True)
    safety.add_argument("--policy", type=Path, required=True)
    safety.add_argument("--output", type=Path, required=True)
    safety.add_argument("--decisions", type=Path, required=True)
    safety.set_defaults(func=command_safety)

    ledger = sub.add_parser("inspection-ledger", help="merge and fingerprint local inspection batches")
    ledger.add_argument("--batch-manifest", type=Path, required=True)
    ledger.add_argument("--output", type=Path, required=True)
    ledger.add_argument("--report", type=Path, required=True)
    ledger.set_defaults(func=command_inspection_ledger)

    duplicates = sub.add_parser("duplicate-audit", help="find cross-UUID duplicate candidates")
    duplicates.add_argument("--inventory", type=Path, required=True)
    duplicates.add_argument("--output", type=Path, required=True)
    duplicates.add_argument("--report", type=Path, required=True)
    duplicates.set_defaults(func=command_duplicate_audit)

    feedback = sub.add_parser("apply-feedback", help="apply explicit judgments and audit cascading replacements")
    feedback.add_argument("--master", type=Path, required=True)
    feedback.add_argument("--candidates", type=Path, required=True)
    feedback.add_argument("--feedback", type=Path, required=True)
    feedback.add_argument("--config", type=Path, required=True)
    feedback.add_argument("--output", type=Path, required=True)
    feedback.set_defaults(func=command_apply_feedback)

    lint = sub.add_parser("lint-plan", help="validate a membership plan before catalog mutation")
    lint.add_argument("--plan", type=Path, required=True)
    lint.add_argument("--master", type=Path, required=True)
    lint.add_argument("--holds", type=Path, required=True)
    lint.add_argument("--config", type=Path, required=True)
    lint.add_argument("--source-profile", type=Path)
    lint.add_argument("--inspection-ledger", type=Path)
    lint.add_argument("--output", type=Path, required=True)
    lint.set_defaults(func=command_lint_plan)

    state = sub.add_parser("state", help="append a validated run-state transition")
    state.add_argument("--run-state", type=Path, required=True)
    state.add_argument("--phase", required=True)
    state.add_argument("--status", choices=("pending", "in_progress", "completed", "blocked"), required=True)
    state.add_argument("--evidence")
    state.set_defaults(func=command_state)

    report = sub.add_parser("report", help="derive a completion report from run artifacts")
    report.add_argument("--run", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    report.set_defaults(func=command_report)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
