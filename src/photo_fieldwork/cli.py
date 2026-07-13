from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from .pipeline import (
    apply_feedback,
    apply_feedback_to_evidence,
    build_catalog_plan,
    candidate_view_evidence,
    canonical_id,
    evaluate,
    make_sample,
    normalize_evidence_edges,
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
    edges = (
        normalize_evidence_edges(read_csv(args.edges, {"uuid", "view_id"}), config)
        if args.edges
        else candidate_view_evidence(inventory, config)
    )
    feedback = []
    for path in args.feedback or []:
        feedback.extend(read_csv(path, {"uuid", "judgment"}))
    if feedback:
        inventory, edges = apply_feedback_to_evidence(inventory, edges, feedback)
    master, holds, summary = select(inventory, config, evidence_edges=edges)
    output = args.output
    write_csv(output / "manifests" / "proposed-master.csv", master)
    inventory_fields = list(dict.fromkeys(key for row in inventory for key in row))
    write_csv(output / "manifests" / "hold-sensitive.csv", holds, inventory_fields)
    write_csv(output / "manifests" / "candidate-view-evidence.csv", edges)
    reports = output / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "selection-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (reports / "selection-summary.md").write_text(markdown_report("Selection summary", summary), encoding="utf-8")
    print(f"selected {len(master)}; held {len(holds)}; wrote {output}")
    return 0


def command_sample(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    excluded = set()
    for path in args.exclude_feedback or []:
        excluded.update(canonical_id(row["uuid"]) for row in read_csv(path, {"uuid"}))
    regressions = read_csv(args.known_regressions, {"uuid", "primary_view"}) if args.known_regressions else []
    sample = make_sample(master, args.per_view, args.seed, excluded, args.novel_only, regressions)
    write_csv(args.output, sample)
    report = {
        "sample_count": len(sample),
        "prior_reviewed_id_count": len(excluded),
        "prior_review_overlap_count": sum(row.get("prior_review_overlap") == "true" for row in sample),
        "novel_only": args.novel_only,
        "by_view": dict(sorted(Counter(row.get("primary_view", "") for row in sample).items())),
    }
    args.output.with_suffix(".report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(sample)} evaluation rows to {args.output}")
    return 0


def command_apply_feedback(args: argparse.Namespace) -> int:
    sample = read_csv(args.sample)
    feedback = []
    for path in args.feedback:
        feedback.extend(read_csv(path, {"uuid", "judgment", "proposal_id", "master_sha256"}))
    summary = validate_feedback(feedback)
    merged = apply_feedback(sample, feedback)
    write_csv(args.output, merged)
    if args.ledger:
        ledger = read_csv(args.ledger, {"uuid", "judgment"}) if args.ledger.exists() else []
        starting_sequence = len(ledger) + 1
        for sequence, row in enumerate(feedback, start=starting_sequence):
            item = dict(row)
            item["ledger_sequence"] = str(sequence)
            ledger.append(item)
        write_csv(args.ledger, ledger)
    print(json.dumps(summary, indent=2))
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    report, passed = evaluate(feedback, config)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    print(f"evaluation {'PASS' if passed else 'FAIL'}: precision={report['precision']}, coverage={report['coverage']}")
    return 0 if passed else 2


def command_validate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds, {"uuid"}, allow_empty=True)
    feedback = []
    for path in args.feedback or []:
        feedback.extend(read_csv(path, {"uuid", "judgment"}))
    errors, metrics = validate(master, holds, config, feedback)
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
    plan = build_catalog_plan(master, config, args.plan_id, args.source_title, args.source_identifier, evaluation_report)
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
    command_select(argparse.Namespace(config=config, inventory=inventory, output=workspace, edges=None, feedback=[]))
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(
        argparse.Namespace(
            master=workspace / "manifests" / "proposed-master.csv",
            output=sample_path,
            per_view=3,
            seed=20260710,
            exclude_feedback=[],
            novel_only=False,
            known_regressions=None,
        )
    )
    practice_feedback(sample_path)
    eval_code = command_evaluate(argparse.Namespace(config=config, feedback=sample_path, output=workspace / "reports"))
    validation_code = command_validate(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            holds=workspace / "manifests" / "hold-sensitive.csv",
            output=workspace / "reports",
            feedback=[],
        )
    )
    command_plan(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            plan_id="synthetic-practice-plan",
            source_title="Synthetic practice corpus",
            source_identifier="SYNTHETIC-ONLY",
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
    selection.add_argument("--edges", type=Path, help="normalized image-view evidence CSV")
    selection.add_argument("--feedback", type=Path, action="append", default=[], help="cumulative feedback CSV; repeatable")
    selection.set_defaults(func=command_select)

    assignment = sub.add_parser("assign", help="alias for select using exact constrained image-view assignment")
    assignment.add_argument("--inventory", type=Path, required=True)
    assignment.add_argument("--config", type=Path, required=True)
    assignment.add_argument("--output", type=Path, required=True)
    assignment.add_argument("--edges", type=Path)
    assignment.add_argument("--feedback", type=Path, action="append", default=[])
    assignment.set_defaults(func=command_select)

    sample = sub.add_parser("sample", help="make a score-stratified evaluation sample")
    sample.add_argument("--master", type=Path, required=True)
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--per-view", type=int, default=3)
    sample.add_argument("--seed", type=int, default=20260710)
    sample.add_argument("--exclude-feedback", type=Path, action="append", default=[])
    sample.add_argument("--novel-only", action="store_true")
    sample.add_argument("--known-regressions", type=Path)
    sample.set_defaults(func=command_sample)

    apply_command = sub.add_parser("apply-feedback", help="validate feedback and apply it to an evaluation sample")
    apply_command.add_argument("--sample", type=Path, required=True)
    apply_command.add_argument("--feedback", type=Path, action="append", required=True)
    apply_command.add_argument("--output", type=Path, required=True)
    apply_command.add_argument("--ledger", type=Path, help="optional append-only normalized feedback ledger")
    apply_command.set_defaults(func=command_apply_feedback)

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
    validation.add_argument("--feedback", type=Path, action="append", default=[])
    validation.set_defaults(func=command_validate)

    plan = sub.add_parser("plan", help="build an adapter-neutral, membership-only catalog plan")
    plan.add_argument("--master", type=Path, required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--plan-id", required=True)
    plan.add_argument("--source-title", required=True)
    plan.add_argument("--source-identifier", required=True)
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
