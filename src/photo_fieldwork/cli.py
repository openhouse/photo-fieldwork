from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .pipeline import (
    build_catalog_plan,
    evaluate,
    make_sample,
    membership_sha256,
    read_config,
    read_csv,
    select,
    validate,
    write_csv,
)
from .practice import create_demo_inventory, practice_feedback, write_demo_readme, write_starter_config
from .profile import check_profile, load_profile
from .review import render_workbench
from .runstate import cleanup_report, derive_state, init_run, record_phase, render_report


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
    print(f"selected {len(master)}; held {len(holds)}; wrote {output}")
    return 0


def command_sample(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    sample = make_sample(master, args.per_view, args.seed)
    write_csv(args.output, sample)
    print(f"wrote {len(sample)} evaluation rows to {args.output}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    report, passed = evaluate(feedback, config, final_field=args.final_field)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    print(f"evaluation {'PASS' if passed else 'FAIL'}: precision={report['precision']}, coverage={report['coverage']}")
    return 0 if passed else 2


def command_validate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    evaluation_report = (
        json.loads(args.evaluation_report.read_text(encoding="utf-8"))
        if args.evaluation_report else None
    )
    final_feedback = read_csv(args.final_feedback) if args.final_feedback else None
    errors, metrics = validate(master, holds, config, evaluation_report, final_feedback)
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(metrics)
    report["errors"] = errors
    (args.output / "validation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "validation-report.md").write_text(markdown_report("Validation report", report), encoding="utf-8")
    print(f"validation {metrics['status']}")
    return 0 if not errors else 2


def command_plan(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    validation_report = json.loads(args.validation_report.read_text(encoding="utf-8"))
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        evaluation_report=evaluation_report,
        validation_report=validation_report,
        source_count=args.source_count,
        source_membership_sha256=args.source_membership_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_review(args: argparse.Namespace) -> int:
    rows = read_csv(args.feedback)
    render_workbench(rows, args.previews, args.output)
    print(f"wrote local review workbench to {args.output}")
    return 0


def command_profile_check(args: argparse.Namespace) -> int:
    report = check_profile(load_profile(args.profile), args.minimum_free_gb)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_run_init(args: argparse.Namespace) -> int:
    workspace = init_run(
        root=args.root,
        version=args.version,
        slug=args.slug,
        target_count=args.target,
        source_identifier=args.source_identifier,
        expected_source_count=args.source_count,
        code_commit=args.code_commit,
        parent_run=args.parent_run,
    )
    print(workspace)
    return 0


def command_run_status(args: argparse.Namespace) -> int:
    state = derive_state(args.workspace)
    print(json.dumps(state, indent=2))
    return 0 if state["status"] == "complete" else 2


def parse_metrics(values: list[str]) -> dict:
    metrics = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"metric must use key=value: {value}")
        key, raw = value.split("=", 1)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        metrics[key] = parsed
    return metrics


def command_run_record(args: argparse.Namespace) -> int:
    receipt = record_phase(
        workspace=args.workspace,
        phase=args.phase,
        status=args.status,
        inputs=args.input,
        outputs=args.output,
        metrics=parse_metrics(args.metric),
        note=args.note,
    )
    print(json.dumps(receipt, indent=2))
    return 0 if args.status in {"pass", "complete"} else 2


def command_run_report(args: argparse.Namespace) -> int:
    report = render_report(args.workspace)
    output = args.output or args.workspace / "reports" / "completion-report.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(output)
    return 0


def command_run_cleanup_report(args: argparse.Namespace) -> int:
    report = cleanup_report(args.workspace)
    output = args.output or args.workspace / "reports" / "cleanup-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


def command_demo(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    inventory = workspace / "inventory" / "practice.csv"
    config = workspace / "config.json"
    create_demo_inventory(inventory)
    write_starter_config(config)
    write_demo_readme(workspace / "README.md")
    command_select(argparse.Namespace(config=config, inventory=inventory, output=workspace))
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(argparse.Namespace(master=workspace / "manifests" / "proposed-master.csv", output=sample_path, per_view=3, seed=20260710))
    practice_feedback(sample_path)
    eval_code = command_evaluate(argparse.Namespace(config=config, feedback=sample_path, output=workspace / "reports", final_field=True))
    validation_code = command_validate(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            holds=workspace / "manifests" / "hold-sensitive.csv",
            output=workspace / "reports",
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            final_feedback=sample_path,
        )
    )
    source_ids = [row["uuid"] for row in read_csv(inventory)]
    command_plan(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            plan_id="synthetic-practice-plan",
            source_title="Synthetic practice corpus",
            source_identifier="SYNTHETIC-ONLY",
            source_count=len(source_ids),
            source_membership_sha256=membership_sha256(source_ids),
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            validation_report=workspace / "reports" / "validation-report.json",
            output=workspace / "manifests" / "catalog-plan.json",
        )
    )
    command_review(argparse.Namespace(feedback=sample_path, previews=workspace / "previews", output=workspace / "reports" / "review-workbench.html"))
    print(f"practice workspace ready: {workspace}")
    return max(eval_code, validation_code)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="photo-fieldwork", description="Build an auditable editor-ready photo corpus")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
    evaluation.add_argument("--final-field", action="store_true", help="mark this as the frozen-field audit")
    evaluation.set_defaults(func=command_evaluate)

    validation = sub.add_parser("validate", help="validate a proposed master against invariants")
    validation.add_argument("--master", type=Path, required=True)
    validation.add_argument("--holds", type=Path, required=True)
    validation.add_argument("--config", type=Path, required=True)
    validation.add_argument("--evaluation-report", type=Path)
    validation.add_argument("--final-feedback", type=Path)
    validation.add_argument("--output", type=Path, required=True)
    validation.set_defaults(func=command_validate)

    plan = sub.add_parser("plan", help="build an adapter-neutral, membership-only catalog plan")
    plan.add_argument("--master", type=Path, required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--plan-id", required=True)
    plan.add_argument("--source-title", required=True)
    plan.add_argument("--source-identifier", required=True)
    plan.add_argument("--source-count", type=int, required=True)
    plan.add_argument("--source-membership-sha256", required=True)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--validation-report", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    review = sub.add_parser("review", help="generate a private local review workbench")
    review.add_argument("--feedback", type=Path, required=True)
    review.add_argument("--previews", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    review.set_defaults(func=command_review)

    profile = sub.add_parser("profile", help="validate a local machine profile")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_check = profile_sub.add_parser("check")
    profile_check.add_argument("--profile", type=Path)
    profile_check.add_argument("--minimum-free-gb", type=float, default=10.0)
    profile_check.set_defaults(func=command_profile_check)

    run = sub.add_parser("run", help="manage a resumable, receipt-backed production run")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_init = run_sub.add_parser("init", help="reserve a semantic version and create a run")
    run_init.add_argument("--root", type=Path, required=True)
    run_init.add_argument("--version", required=True)
    run_init.add_argument("--slug", required=True)
    run_init.add_argument("--target", type=int, required=True)
    run_init.add_argument("--source-identifier", required=True)
    run_init.add_argument("--source-count", type=int)
    run_init.add_argument("--code-commit")
    run_init.add_argument("--parent-run")
    run_init.set_defaults(func=command_run_init)

    run_status = run_sub.add_parser("status", help="derive current state from receipts")
    run_status.add_argument("--workspace", type=Path, required=True)
    run_status.set_defaults(func=command_run_status)

    run_record = run_sub.add_parser("record", help="append a checksummed phase receipt")
    run_record.add_argument("--workspace", type=Path, required=True)
    run_record.add_argument("--phase", choices=("preflight", "retrieval", "inspection", "review", "validation", "write_test", "production_commit", "independent_verification"), required=True)
    run_record.add_argument("--status", choices=("pass", "fail", "complete"), required=True)
    run_record.add_argument("--input", type=Path, action="append", default=[])
    run_record.add_argument("--output", type=Path, action="append", default=[])
    run_record.add_argument("--metric", action="append", default=[])
    run_record.add_argument("--note")
    run_record.set_defaults(func=command_run_record)

    run_report = run_sub.add_parser("report", help="render an evidence-derived completion report")
    run_report.add_argument("--workspace", type=Path, required=True)
    run_report.add_argument("--output", type=Path)
    run_report.set_defaults(func=command_run_report)

    cleanup = run_sub.add_parser("cleanup-report", help="report disposable run storage without deleting it")
    cleanup.add_argument("--workspace", type=Path, required=True)
    cleanup.add_argument("--output", type=Path)
    cleanup.set_defaults(func=command_run_cleanup_report)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
