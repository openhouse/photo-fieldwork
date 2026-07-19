from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .contracts import build_source_manifest, load_source_manifest, rows_membership_sha256
from .pipeline import (
    SelectionInfeasible,
    apply_feedback,
    build_catalog_plan,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    validate_feedback,
    write_csv,
)
from .practice import create_demo_inventory, practice_feedback, write_demo_readme


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
    output = args.output
    try:
        master, holds, summary = select(inventory, config)
    except SelectionInfeasible as error:
        manifests = output / "manifests"
        reports = output / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        if error.holds:
            write_csv(manifests / "hold-sensitive.csv", error.holds)
        if error.partial_master:
            write_csv(manifests / "proposed-master-partial.csv", error.partial_master)
        report = {
            "status": "BLOCKED",
            "reason": str(error),
            "deficits": error.deficits,
            "hold_count": len(error.holds),
            "partial_master_count": len(error.partial_master),
        }
        (reports / "selection-failure.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        (reports / "selection-failure.md").write_text(
            markdown_report("Selection failure", report), encoding="utf-8"
        )
        print(f"selection blocked: {error}; deficits={error.deficits}", file=sys.stderr)
        return 2
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
    excluded_ids: set[str] = set()
    for path in args.exclude_feedback or []:
        excluded_ids.update(row["uuid"] for row in read_csv(path, {"uuid"}))
    canary_ids = {row["uuid"] for row in read_csv(args.canaries, {"uuid"})} if args.canaries else set()
    sample = make_sample(master, args.per_view, args.seed, excluded_ids, canary_ids)
    write_csv(args.output, sample)
    print(f"wrote {len(sample)} evaluation rows to {args.output}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    master = read_csv(args.master)
    source_manifest = load_source_manifest(args.source_manifest)
    report, passed = evaluate(feedback, config, master, args.scope, source_manifest)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    print(
        f"evaluation {'PASS' if passed else 'FAIL'}: "
        f"fresh_precision={report['fresh_decisive_precision']}, "
        f"sample_completion={report['sample_completion']}, "
        f"master_review_fraction={report['master_review_fraction']}"
    )
    return 0 if passed else 2


def command_feedback_validate(args: argparse.Namespace) -> int:
    feedback = read_csv(
        args.feedback,
        {"uuid", "proposal_id", "master_sha256", "sample_sha256", "judgment"},
    )
    report = validate_feedback(feedback)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def command_feedback_apply(args: argparse.Namespace) -> int:
    sample = read_csv(args.sample)
    feedback = read_csv(
        args.feedback,
        {"uuid", "proposal_id", "master_sha256", "sample_sha256", "judgment"},
    )
    merged = apply_feedback(sample, feedback)
    write_csv(args.output, merged)
    print(f"applied {len(feedback)} feedback rows to {args.output}")
    return 0


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
    print(f"validation {metrics['status']}")
    return 0 if not errors else 2


def command_plan(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    source_manifest = load_source_manifest(args.source_manifest)
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        evaluation_report,
        source_manifest,
        holds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
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
    command_select(argparse.Namespace(config=config, inventory=inventory, output=workspace))
    source_manifest_path = workspace / "manifests" / "source-manifest.json"
    inventory_rows = read_csv(inventory)
    source_manifest = build_source_manifest(
        source_adapter="synthetic-fixture",
        source_identifier="synthetic://practice-v1",
        source_title="Synthetic practice corpus",
        predicate_version="all-synthetic-records-v1",
        observed_count=len(inventory_rows),
        membership_sha256=rows_membership_sha256(inventory_rows),
        artifact_sensitivity="public-safe",
    )
    source_manifest_path.write_text(json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8")
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(
        argparse.Namespace(
            master=workspace / "manifests" / "proposed-master.csv",
            output=sample_path,
            per_view=3,
            seed=20260710,
            exclude_feedback=[],
            canaries=None,
        )
    )
    practice_feedback(sample_path)
    eval_code = command_evaluate(
        argparse.Namespace(
            config=config,
            feedback=sample_path,
            master=workspace / "manifests" / "proposed-master.csv",
            source_manifest=source_manifest_path,
            scope="final-stratified-sample",
            output=workspace / "reports",
        )
    )
    validation_code = command_validate(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            holds=workspace / "manifests" / "hold-sensitive.csv",
            output=workspace / "reports",
        )
    )
    command_plan(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            holds=workspace / "manifests" / "hold-sensitive.csv",
            plan_id="synthetic-practice-plan",
            source_manifest=source_manifest_path,
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            output=workspace / "manifests" / "catalog-plan.json",
        )
    )
    print(f"practice workspace ready: {workspace}")
    return max(eval_code, validation_code)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="photo-fieldwork", description="Build an auditable editor-ready photo corpus")
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
    sample.add_argument(
        "--exclude-feedback",
        type=Path,
        action="append",
        help="exclude UUIDs already labeled in an earlier feedback CSV; may be repeated",
    )
    sample.add_argument("--canaries", type=Path, help="append these master UUIDs as regression canaries")
    sample.set_defaults(func=command_sample)

    evaluation = sub.add_parser("evaluate", help="measure labeled evaluation feedback")
    evaluation.add_argument("--feedback", type=Path, required=True)
    evaluation.add_argument("--master", type=Path, required=True, help="bind evaluation to this exact master")
    evaluation.add_argument("--source-manifest", type=Path, required=True)
    evaluation.add_argument("--scope", choices=("learning-sample", "final-stratified-sample", "full-master", "publication-shortlist"))
    evaluation.add_argument("--config", type=Path, required=True)
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.set_defaults(func=command_evaluate)

    feedback = sub.add_parser("feedback-validate", help="validate structured evaluation feedback")
    feedback.add_argument("--feedback", type=Path, required=True)
    feedback.add_argument("--output", type=Path)
    feedback.set_defaults(func=command_feedback_validate)

    feedback_apply = sub.add_parser("feedback-apply", help="apply validated feedback to an evaluation sample")
    feedback_apply.add_argument("--sample", type=Path, required=True)
    feedback_apply.add_argument("--feedback", type=Path, required=True)
    feedback_apply.add_argument("--output", type=Path, required=True)
    feedback_apply.set_defaults(func=command_feedback_apply)

    validation = sub.add_parser("validate", help="validate a proposed master against invariants")
    validation.add_argument("--master", type=Path, required=True)
    validation.add_argument("--holds", type=Path, required=True)
    validation.add_argument("--config", type=Path, required=True)
    validation.add_argument("--output", type=Path, required=True)
    validation.set_defaults(func=command_validate)

    plan = sub.add_parser("plan", help="build an adapter-neutral, membership-only catalog plan")
    plan.add_argument("--master", type=Path, required=True)
    plan.add_argument("--holds", type=Path, required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--plan-id", required=True)
    plan.add_argument("--source-manifest", type=Path, required=True)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
