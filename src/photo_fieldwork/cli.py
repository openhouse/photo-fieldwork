from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .audit import audit_paths, repository_paths
from .handoff import build_public_handoff
from .ledger import build_events
from .pipeline import (
    audit_holdout_split,
    build_catalog_plan,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
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
    excluded_ids = set()
    known_regressions = None
    exclude_feedback = getattr(args, "exclude_feedback", None)
    if exclude_feedback:
        excluded_ids = {row["uuid"] for row in read_csv(exclude_feedback)}
    if getattr(args, "known_regressions", None):
        known_regressions = read_csv(args.known_regressions)
    sample = make_sample(
        master,
        args.per_view,
        args.seed,
        excluded_ids=excluded_ids,
        novel_only=getattr(args, "novel_only", False),
        known_regressions=known_regressions,
    )
    write_csv(args.output, sample)
    overlap = sum(row.get("prior_review_overlap") == "true" for row in sample)
    canaries = sum(row.get("sample_role") == "regression-canary" for row in sample)
    print(
        f"wrote {len(sample)} evaluation rows to {args.output}; "
        f"prior UUID overlap={overlap}; regression canaries={canaries}"
    )
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    report, passed = evaluate(feedback, config)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    print(
        f"evaluation {'PASS' if passed else 'FAIL'}: "
        f"decisive_precision={report['decisive_precision']}, "
        f"uncertainty={report['uncertainty_rate']}, coverage={report['coverage']}"
    )
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
    print(f"validation {metrics['status']}")
    return 0 if not errors else 2


def command_plan(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        evaluation_report,
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
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(
        argparse.Namespace(
            master=workspace / "manifests" / "proposed-master.csv",
            output=sample_path,
            per_view=3,
            seed=20260710,
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


def command_audit_public(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    failures = audit_paths(root, repository_paths(root))
    if failures:
        print("public-safety audit FAIL", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 2
    print("public-safety audit PASS")
    return 0


def command_ledger(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    feedback = read_csv(args.feedback)
    events = build_events(master, holds, feedback)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    print(f"wrote {len(events)} lineage events to {args.output}")
    return 0


def command_audit_holdout(args: argparse.Namespace) -> int:
    tuning = read_csv(args.tuning)
    holdout = read_csv(args.holdout)
    report, passed = audit_holdout_split(tuning, holdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"holdout audit {report['status']}")
    return 0 if passed else 2


def command_public_handoff(args: argparse.Namespace) -> int:
    rows = read_csv(args.input)
    manifest, report = build_public_handoff(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"public handoff {report['status']}: "
        f"included={report['included_count']}, excluded={report['excluded_count']}"
    )
    return 0 if manifest["publication_clearance"] else 2


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="photo-fieldwork", description="Build an auditable editor-ready photo corpus")
    sub = root.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run the complete workflow on synthetic records")
    demo.add_argument("--workspace", type=Path, default=Path("runs/practice"))
    demo.set_defaults(func=command_demo)

    audit = sub.add_parser("audit-public", help="reject likely private archive artifacts from the public repository")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.set_defaults(func=command_audit_public)

    ledger = sub.add_parser("ledger", help="build a stable per-asset decision-lineage JSONL")
    ledger.add_argument("--master", type=Path, required=True)
    ledger.add_argument("--holds", type=Path, required=True)
    ledger.add_argument("--feedback", type=Path, required=True)
    ledger.add_argument("--output", type=Path, required=True)
    ledger.set_defaults(func=command_ledger)

    holdout = sub.add_parser(
        "audit-holdout",
        help="fail on UUID, duplicate, perceptual-cluster, or burst leakage",
    )
    holdout.add_argument("--tuning", type=Path, required=True)
    holdout.add_argument("--holdout", type=Path, required=True)
    holdout.add_argument("--output", type=Path, required=True)
    holdout.set_defaults(func=command_audit_holdout)

    handoff = sub.add_parser(
        "public-handoff",
        help="project explicitly cleared derivatives into an allowlisted manifest",
    )
    handoff.add_argument("--input", type=Path, required=True)
    handoff.add_argument("--output", type=Path, required=True)
    handoff.add_argument("--report", type=Path, required=True)
    handoff.set_defaults(func=command_public_handoff)

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
    sample.add_argument("--exclude-feedback", type=Path, help="prior evaluation CSV whose UUIDs should be tracked")
    sample.add_argument("--novel-only", action="store_true", help="fail unless the sample has zero prior UUID overlap")
    sample.add_argument(
        "--known-regressions",
        type=Path,
        help="CSV of master rows with expected_judgment and optional expected_safety_state",
    )
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
