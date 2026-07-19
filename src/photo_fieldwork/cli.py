from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .handoff import build_public_handoff
from .pipeline import (
    apply_feedback,
    build_catalog_plan,
    ensure_private_directory,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    validate_feedback,
    write_csv,
    write_private_text,
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
    master, holds, summary = select(inventory, config)
    output = args.output
    write_csv(output / "manifests" / "proposed-master.csv", master)
    write_csv(output / "manifests" / "hold-sensitive.csv", holds)
    reports = output / "reports"
    ensure_private_directory(reports)
    write_private_text(reports / "selection-summary.json", json.dumps(summary, indent=2) + "\n")
    write_private_text(reports / "selection-summary.md", markdown_report("Selection summary", summary))
    print(f"selected {len(master)}; held {len(holds)}; wrote {output}")
    return 0


def command_sample(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    config = read_config(args.config)
    sampling_history = (
        json.loads(args.sampling_history.read_text(encoding="utf-8"))
        if args.sampling_history
        else None
    )
    sample = make_sample(
        master,
        int(config["evaluation_sample_per_view"]),
        int(config["seed"]),
        args.round_id,
        sampling_history,
    )
    write_csv(args.output, sample)
    print(f"wrote {len(sample)} evaluation rows to {args.output}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    master = read_csv(args.master)
    sampling_history = (
        json.loads(args.sampling_history.read_text(encoding="utf-8"))
        if args.sampling_history
        else None
    )
    report, passed = evaluate(feedback, config, master, sampling_history)
    ensure_private_directory(args.output)
    write_private_text(args.output / "evaluation-report.json", json.dumps(report, indent=2) + "\n")
    write_private_text(args.output / "evaluation-report.md", markdown_report("Evaluation report", report))
    print(f"evaluation {'PASS' if passed else 'FAIL'}: precision={report['precision']}, coverage={report['coverage']}")
    return 0 if passed else 2


def command_feedback_validate(args: argparse.Namespace) -> int:
    feedback = read_csv(args.feedback, {"uuid", "proposal_id", "master_sha256", "judgment"})
    report = validate_feedback(feedback)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def command_feedback_apply(args: argparse.Namespace) -> int:
    sample = read_csv(args.sample)
    feedback = read_csv(args.feedback, {"uuid", "proposal_id", "master_sha256", "judgment"})
    merged = apply_feedback(sample, feedback)
    write_csv(args.output, merged)
    print(f"applied {len(feedback)} feedback rows to {args.output}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    errors, metrics = validate(master, holds, config)
    ensure_private_directory(args.output)
    report = dict(metrics)
    report["errors"] = errors
    write_private_text(args.output / "validation-report.json", json.dumps(report, indent=2) + "\n")
    write_private_text(args.output / "validation-report.md", markdown_report("Validation report", report))
    print(f"validation {metrics['status']}")
    return 0 if not errors else 2


def command_plan(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    feedback = read_csv(args.feedback)
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    validation_report = json.loads(args.validation_report.read_text(encoding="utf-8"))
    plan = build_catalog_plan(
        master,
        holds,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        args.source_count,
        args.source_sha256,
        evaluation_report,
        feedback,
        validation_report,
    )
    write_private_text(args.output, json.dumps(plan, indent=2) + "\n")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_public_handoff(args: argparse.Namespace) -> int:
    rows = read_csv(args.manifest, {"uuid", "publication_status"})
    if args.salt_file.is_symlink() or not args.salt_file.is_file():
        raise ValueError("public handoff salt must be a regular non-symlink file")
    if args.salt_file.stat().st_mode & 0o077:
        raise ValueError("public handoff salt file must have mode 0600")
    salt = args.salt_file.read_text(encoding="utf-8").strip()
    handoff, errors = build_public_handoff(rows, salt, args.destination)
    if errors:
        raise ValueError("public handoff blocked: " + "; ".join(errors))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(handoff, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"wrote {len(handoff)} public-safe rows to {args.output}")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    workspace = args.workspace.resolve()
    inventory = workspace / "inventory" / "practice.csv"
    config = workspace / "config.json"
    create_demo_inventory(inventory)
    ensure_private_directory(config.parent)
    shutil.copy2(root / "config" / "starter.json", config)
    config.chmod(0o600)
    write_demo_readme(workspace / "README.md")
    command_select(argparse.Namespace(config=config, inventory=inventory, output=workspace))
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(
        argparse.Namespace(
            master=workspace / "manifests" / "proposed-master.csv",
            config=config,
            output=sample_path,
            round_id="practice-round-01",
            sampling_history=None,
        )
    )
    practice_feedback(sample_path)
    eval_code = command_evaluate(
        argparse.Namespace(
            config=config,
            feedback=sample_path,
            master=workspace / "manifests" / "proposed-master.csv",
            sampling_history=None,
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
            feedback=sample_path,
            plan_id="synthetic-practice-plan",
            source_title="Synthetic practice corpus",
            source_identifier="SYNTHETIC-ONLY",
            source_count=30,
            source_sha256="50ce7a9ce8269931cee4ed617a22fd1214f27fcde9aada68e23ae8a4b373af74",
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            validation_report=workspace / "reports" / "validation-report.json",
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
    sample.add_argument("--config", type=Path, required=True)
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--round-id", default="round-01")
    sample.add_argument(
        "--sampling-history",
        type=Path,
        help="JSON with excluded_ids and canary_ids bound into the sample identity",
    )
    sample.set_defaults(func=command_sample)

    evaluation = sub.add_parser("evaluate", help="measure labeled evaluation feedback")
    evaluation.add_argument("--feedback", type=Path, required=True)
    evaluation.add_argument("--master", type=Path, required=True)
    evaluation.add_argument("--config", type=Path, required=True)
    evaluation.add_argument(
        "--sampling-history",
        type=Path,
        help="the same sampling-history JSON used to create the sample",
    )
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
    plan.add_argument("--feedback", type=Path, required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--plan-id", required=True)
    plan.add_argument("--source-title", required=True)
    plan.add_argument("--source-identifier", required=True)
    plan.add_argument("--source-count", type=int, required=True)
    plan.add_argument("--source-sha256", required=True)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--validation-report", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    handoff = sub.add_parser(
        "public-handoff",
        help="create an allowlisted, destination-scoped publication derivative",
    )
    handoff.add_argument("--manifest", type=Path, required=True)
    handoff.add_argument("--destination", required=True)
    handoff.add_argument("--salt-file", type=Path, required=True)
    handoff.add_argument("--output", type=Path, required=True)
    handoff.set_defaults(func=command_public_handoff)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
