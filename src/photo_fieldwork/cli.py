from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from .ledger import append_event, connect as connect_ledger, export_jsonl
from .pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate, write_csv
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .rounds import apply_feedback, convergence
from .run_state import finalize as finalize_run
from .run_state import initialize as initialize_run
from .run_state import read_json, reconcile as reconcile_run


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    report, passed = evaluate(feedback, config)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    print(f"evaluation {'PASS' if passed else 'FAIL'}: precision={report['precision']}, coverage={report['coverage']}")
    return 0 if passed else 2


def command_validate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    evaluation_path = getattr(args, "evaluation_report", None)
    summary_path = getattr(args, "candidate_summary", None)
    evaluation_report = read_json(evaluation_path) if evaluation_path else None
    candidate_summary = read_json(summary_path) if summary_path else None
    errors, metrics = validate(
        master,
        holds,
        config,
        evaluation_report=evaluation_report,
        candidate_summary=candidate_summary,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(metrics)
    report["errors"] = errors
    (args.output / "validation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "validation-report.md").write_text(markdown_report("Validation report", report), encoding="utf-8")
    print(f"validation {metrics['status']}")
    return 0 if not errors else 2


def command_run_init(args: argparse.Namespace) -> int:
    state = initialize_run(
        args.workspace,
        run_id=args.run_id,
        version=args.version,
        target_count=args.target,
        source_identifier=args.source_identifier,
        expected_source_count=args.source_count,
        config_hash=file_hash(args.config) if args.config else None,
        code_version=args.code_version,
    )
    print(json.dumps(state, indent=2))
    return 0


def command_run_status(args: argparse.Namespace) -> int:
    state = read_json(args.workspace / "run-state.json")
    print(json.dumps(state, indent=2))
    return 0


def command_run_reconcile(args: argparse.Namespace) -> int:
    state = reconcile_run(args.workspace)
    print(json.dumps(state, indent=2))
    return 0


def command_run_finalize(args: argparse.Namespace) -> int:
    state = finalize_run(args.workspace)
    print(json.dumps(state, indent=2))
    return 0


def command_ledger_init(args: argparse.Namespace) -> int:
    with connect_ledger(args.ledger) as conn:
        version = conn.execute("SELECT value FROM ledger_meta WHERE key='schema_version'").fetchone()[0]
    print(f"ledger={args.ledger}")
    print(f"schema_version={version}")
    return 0


def command_ledger_append(args: argparse.Namespace) -> int:
    payload = json.loads(args.payload) if args.payload else {}
    event_id = append_event(
        args.ledger,
        run_id=args.run_id,
        round_id=args.round_id,
        asset_uuid=args.asset_uuid,
        event_type=args.event_type,
        actor=args.actor,
        previous_state=args.previous_state,
        new_state=args.new_state,
        reason=args.reason,
        payload=payload,
        config_hash=args.config_hash,
        inspection_profile_hash=args.inspection_profile_hash,
        code_version=args.code_version,
    )
    print(f"event_id={event_id}")
    return 0


def command_ledger_export(args: argparse.Namespace) -> int:
    count = export_jsonl(args.ledger, args.output)
    print(f"events={count}")
    print(f"output={args.output}")
    return 0


def command_round_apply(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    inventory = read_csv(args.inventory)
    feedback = read_csv(args.feedback)
    updated, events = apply_feedback(
        master,
        inventory,
        feedback,
        round_id=args.round_id,
        allow_uninspected=args.allow_uninspected,
    )
    write_csv(args.output, updated)
    if args.ledger:
        for event in events:
            append_event(
                args.ledger,
                run_id=args.run_id,
                round_id=args.round_id,
                actor=args.actor,
                config_hash=args.config_hash,
                inspection_profile_hash=args.inspection_profile_hash,
                code_version=args.code_version,
                **event,
            )
    print(f"selected={len(updated)}")
    print(f"decision_events={len(events)}")
    print(f"output={args.output}")
    return 0


def command_round_convergence(args: argparse.Namespace) -> int:
    reports = [read_json(path) for path in args.reports]
    report = convergence(reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"rounds={report['round_count']}")
    print(f"final_passed={str(report['final_passed']).lower()}")
    return 0 if report["final_passed"] else 2


def command_plan(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    plan = build_catalog_plan(master, config, args.plan_id, args.source_title, args.source_identifier)
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
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            candidate_summary=None,
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
    validation.add_argument("--evaluation-report", type=Path)
    validation.add_argument("--candidate-summary", type=Path)
    validation.set_defaults(func=command_validate)

    plan = sub.add_parser("plan", help="build an adapter-neutral, membership-only catalog plan")
    plan.add_argument("--master", type=Path, required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--plan-id", required=True)
    plan.add_argument("--source-title", required=True)
    plan.add_argument("--source-identifier", required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    run = sub.add_parser("run", help="manage a resumable run lifecycle")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_init = run_sub.add_parser("init", help="initialize a versioned run")
    run_init.add_argument("--workspace", type=Path, required=True)
    run_init.add_argument("--run-id", required=True)
    run_init.add_argument("--version", required=True)
    run_init.add_argument("--target", type=int, required=True)
    run_init.add_argument("--source-identifier", required=True)
    run_init.add_argument("--source-count", type=int, required=True)
    run_init.add_argument("--config", type=Path)
    run_init.add_argument("--code-version")
    run_init.set_defaults(func=command_run_init)
    for name, handler in (
        ("status", command_run_status),
        ("reconcile", command_run_reconcile),
        ("finalize", command_run_finalize),
    ):
        command = run_sub.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.set_defaults(func=handler)

    ledger = sub.add_parser("ledger", help="append and export decision events")
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_init = ledger_sub.add_parser("init")
    ledger_init.add_argument("--ledger", type=Path, required=True)
    ledger_init.set_defaults(func=command_ledger_init)
    ledger_append = ledger_sub.add_parser("append")
    ledger_append.add_argument("--ledger", type=Path, required=True)
    ledger_append.add_argument("--run-id", required=True)
    ledger_append.add_argument("--round-id")
    ledger_append.add_argument("--asset-uuid")
    ledger_append.add_argument("--event-type", required=True)
    ledger_append.add_argument("--actor", required=True)
    ledger_append.add_argument("--previous-state")
    ledger_append.add_argument("--new-state")
    ledger_append.add_argument("--reason")
    ledger_append.add_argument("--payload")
    ledger_append.add_argument("--config-hash")
    ledger_append.add_argument("--inspection-profile-hash")
    ledger_append.add_argument("--code-version")
    ledger_append.set_defaults(func=command_ledger_append)
    ledger_export = ledger_sub.add_parser("export")
    ledger_export.add_argument("--ledger", type=Path, required=True)
    ledger_export.add_argument("--output", type=Path, required=True)
    ledger_export.set_defaults(func=command_ledger_export)

    round_parser = sub.add_parser("round", help="apply reviewed feedback and report convergence")
    round_sub = round_parser.add_subparsers(dest="round_command", required=True)
    round_apply = round_sub.add_parser("apply")
    round_apply.add_argument("--master", type=Path, required=True)
    round_apply.add_argument("--inventory", type=Path, required=True)
    round_apply.add_argument("--feedback", type=Path, required=True)
    round_apply.add_argument("--output", type=Path, required=True)
    round_apply.add_argument("--round-id", required=True)
    round_apply.add_argument("--ledger", type=Path)
    round_apply.add_argument("--run-id", default="unspecified-run")
    round_apply.add_argument("--actor", default="editorial-review")
    round_apply.add_argument("--config-hash")
    round_apply.add_argument("--inspection-profile-hash")
    round_apply.add_argument("--code-version")
    round_apply.add_argument("--allow-uninspected", action="store_true")
    round_apply.set_defaults(func=command_round_apply)
    round_convergence = round_sub.add_parser("convergence")
    round_convergence.add_argument("--reports", type=Path, nargs="+", required=True)
    round_convergence.add_argument("--output", type=Path, required=True)
    round_convergence.set_defaults(func=command_round_convergence)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
