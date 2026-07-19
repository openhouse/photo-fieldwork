from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from .decision_ledger import append_events, audit_ledger, materialize, read_ledger
from .pipeline import (
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
from .publication import scaffold as scaffold_publication
from .publication import validate as validate_publication
from .release import audit_release_seal, build_release_seal, write_release_seal
from .run_state import audit_state, mark_phase


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
    write_csv(output / "manifests" / "hold-sensitive.csv", holds, fieldnames=list(inventory[0]))
    reports = output / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "selection-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (reports / "selection-summary.md").write_text(markdown_report("Selection summary", summary), encoding="utf-8")
    print(f"selected {len(master)}; held {len(holds)}; wrote {output}")
    return 0


def command_sample(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    views = set(args.view) if args.view else None
    sample = make_sample(master, args.per_view, args.seed, views=views, round_id=args.round_id)
    write_csv(args.output, sample)
    print(f"wrote {len(sample)} evaluation rows to {args.output}")
    return 0


def command_state(args: argparse.Namespace) -> int:
    if args.action == "mark":
        if not args.phase or not args.status:
            raise ValueError("state mark requires --phase and --status")
        mark_phase(args.workspace, args.phase, args.status, args.artifact)
    report = audit_state(args.workspace)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_decisions(args: argparse.Namespace) -> int:
    if args.action == "append":
        if args.events is None:
            raise ValueError("decisions append requires --events")
        incoming = [
            json.loads(line)
            for line in args.events.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        report = append_events(args.ledger, incoming)
    elif args.action == "materialize":
        if args.inventory is None or args.output is None:
            raise ValueError("decisions materialize requires --inventory and --output")
        rows, report = materialize(read_csv(args.inventory), read_ledger(args.ledger))
        write_csv(args.output, rows)
    else:
        report = audit_ledger(args.ledger)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    master = read_csv(args.master) if args.master else None
    report, passed = evaluate(feedback, config, master=master)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    print(f"evaluation {'PASS' if passed else 'FAIL'}: precision={report['precision']}, coverage={report['coverage']}")
    return 0 if passed else 2


def command_feedback_validate(args: argparse.Namespace) -> int:
    report = validate_feedback(read_csv(args.feedback))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def command_feedback_apply(args: argparse.Namespace) -> int:
    feedback = read_csv(args.feedback)
    merged = apply_feedback(read_csv(args.sample), feedback)
    write_csv(args.output, merged)
    print(f"applied {len(feedback)} feedback rows to {args.output}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds, allow_empty=True)
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
    source_manifest = (
        json.loads(args.source_manifest.read_text(encoding="utf-8"))
        if getattr(args, "source_manifest", None) else None
    )
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        evaluation_report,
        source_manifest=source_manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_release(args: argparse.Namespace) -> int:
    if args.action == "create":
        required = {
            "source": args.source,
            "config": args.config,
            "master": args.master,
            "evaluation": args.evaluation,
            "validation": args.validation,
            "plan": args.plan,
            "output": args.output,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"release-seal create missing: {', '.join(missing)}")
        seal = build_release_seal(
            source_path=args.source,
            config_path=args.config,
            master_path=args.master,
            evaluation_path=args.evaluation,
            validation_path=args.validation,
            plan_path=args.plan,
            output_path=args.output,
        )
        write_release_seal(args.output, seal)
        report = audit_release_seal(args.output)
    else:
        if args.seal is None:
            raise ValueError("release-seal audit requires --seal")
        report = audit_release_seal(args.seal)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_publication(args: argparse.Namespace) -> int:
    if args.action == "scaffold":
        if args.master is None or args.output is None:
            raise ValueError("publication scaffold requires --master and --output")
        rows = scaffold_publication(read_csv(args.master))
        write_csv(args.output, rows)
        report = {"status": "PASS", "rows": len(rows), "publication_approved": 0}
    else:
        if args.review is None:
            raise ValueError("publication validate requires --review")
        errors, report = validate_publication(read_csv(args.review))
        report["errors"] = errors
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_demo(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    workspace = args.workspace.resolve()
    inventory = workspace / "inventory" / "practice.csv"
    config = workspace / "config.json"
    source = workspace / "source.json"
    create_demo_inventory(inventory)
    config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "config" / "starter.json", config)
    source.write_text(json.dumps({
        "schema_version": 1,
        "kind": "synthetic",
        "identifier": "SYNTHETIC-ONLY",
        "title": "Synthetic practice corpus",
        "snapshot_count": len(read_csv(inventory)),
        "predicate_version": "synthetic-practice-v1",
        "source_fingerprint": hashlib.sha256(inventory.read_bytes()).hexdigest(),
    }, indent=2) + "\n", encoding="utf-8")
    write_demo_readme(workspace / "README.md")
    command_select(argparse.Namespace(config=config, inventory=inventory, output=workspace))
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(
        argparse.Namespace(
            master=workspace / "manifests" / "proposed-master.csv",
            output=sample_path,
            per_view=3,
            seed=20260710,
            view=[],
            round_id="practice-01",
        )
    )
    practice_feedback(sample_path)
    eval_code = command_evaluate(argparse.Namespace(
        config=config,
        feedback=sample_path,
        master=workspace / "manifests" / "proposed-master.csv",
        output=workspace / "reports",
    ))
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
            source_manifest=source,
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            output=workspace / "manifests" / "catalog-plan.json",
        )
    )
    command_release(argparse.Namespace(
        action="create",
        source=source,
        config=config,
        master=workspace / "manifests" / "proposed-master.csv",
        evaluation=workspace / "reports" / "evaluation-report.json",
        validation=workspace / "reports" / "validation-report.json",
        plan=workspace / "manifests" / "catalog-plan.json",
        output=workspace / "manifests" / "release-seal.json",
        seal=None,
    ))
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
    sample.add_argument("--view", action="append", default=[], help="sample only this view; repeat as needed")
    sample.add_argument("--round-id", default="round-01")
    sample.set_defaults(func=command_sample)

    evaluation = sub.add_parser("evaluate", help="measure labeled evaluation feedback")
    evaluation.add_argument("--feedback", type=Path, required=True)
    evaluation.add_argument("--config", type=Path, required=True)
    evaluation.add_argument("--master", type=Path, help="required to certify a full-master audit")
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.set_defaults(func=command_evaluate)

    feedback = sub.add_parser("feedback-validate", help="validate structured evaluation feedback")
    feedback.add_argument("--feedback", type=Path, required=True)
    feedback.add_argument("--output", type=Path)
    feedback.set_defaults(func=command_feedback_validate)

    feedback_apply = sub.add_parser("feedback-apply", help="apply feedback to an evaluation sample")
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
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--plan-id", required=True)
    plan.add_argument("--source-title", required=True)
    plan.add_argument("--source-identifier", required=True)
    plan.add_argument("--source-manifest", type=Path)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    state = sub.add_parser("state", help="inspect or update resumable run state")
    state.add_argument("action", choices=["status", "resume", "audit", "mark"])
    state.add_argument("--workspace", type=Path, required=True)
    state.add_argument("--phase")
    state.add_argument("--status", choices=["pending", "in-progress", "complete", "blocked"])
    state.add_argument("--artifact", type=Path, action="append", default=[])
    state.set_defaults(func=command_state)

    decisions = sub.add_parser("decisions", help="append, audit, or materialize human decision lineage")
    decisions.add_argument("action", choices=["append", "audit", "materialize"])
    decisions.add_argument("--ledger", type=Path, required=True)
    decisions.add_argument("--events", type=Path)
    decisions.add_argument("--inventory", type=Path)
    decisions.add_argument("--output", type=Path)
    decisions.set_defaults(func=command_decisions)

    release = sub.add_parser("release-seal", help="create or audit a candidate-bound release seal")
    release.add_argument("action", choices=["create", "audit"])
    release.add_argument("--source", type=Path)
    release.add_argument("--config", type=Path)
    release.add_argument("--master", type=Path)
    release.add_argument("--evaluation", type=Path)
    release.add_argument("--validation", type=Path)
    release.add_argument("--plan", type=Path)
    release.add_argument("--output", type=Path)
    release.add_argument("--seal", type=Path)
    release.set_defaults(func=command_release)

    publication = sub.add_parser("publication", help="scaffold or validate default-closed publication review")
    publication.add_argument("action", choices=["scaffold", "validate"])
    publication.add_argument("--master", type=Path)
    publication.add_argument("--review", type=Path)
    publication.add_argument("--output", type=Path)
    publication.set_defaults(func=command_publication)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
