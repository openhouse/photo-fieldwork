from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .artifacts import build_source_snapshot, verify_source_snapshot
from .pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate, write_csv
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .run_ledger import PHASES, derive_state, initialize_run, next_phase, record_phase


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
    source_snapshot_path = getattr(args, "source_snapshot", None)
    source_snapshot = json.loads(source_snapshot_path.read_text(encoding="utf-8")) if source_snapshot_path else None
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        source_snapshot,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def inventory_ids(path: Path, id_column: str) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or id_column not in rows[0]:
        raise ValueError(f"inventory requires {id_column} rows: {path}")
    identifiers = [row[id_column].strip() for row in rows if row[id_column].strip()]
    if not identifiers:
        raise ValueError(f"inventory contains no {id_column} values: {path}")
    return identifiers


def command_source_snapshot(args: argparse.Namespace) -> int:
    identifiers = inventory_ids(args.inventory, args.id_column)
    snapshot = build_source_snapshot(
        identifiers,
        args.query_id,
        query_definition_version=args.query_definition_version,
    )
    if args.expected_count is not None and snapshot["observed_count"] != args.expected_count:
        raise ValueError(
            f"source count changed: {snapshot['observed_count']} != {args.expected_count}"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"source_count={snapshot['observed_count']}")
    print(f"membership_sha256={snapshot['membership_sha256']}")
    return 0


def command_source_verify(args: argparse.Namespace) -> int:
    identifiers = inventory_ids(args.inventory, args.id_column)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    errors = verify_source_snapshot(identifiers, snapshot)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"source verification PASS: {len(set(identifiers))} members")
    return 0


def command_run_init(args: argparse.Namespace) -> int:
    snapshot = json.loads(args.source_snapshot.read_text(encoding="utf-8"))
    initialize_run(args.workspace, args.run_id, args.target_count, snapshot, args.version)
    print(args.workspace)
    return 0


def command_run_record(args: argparse.Namespace) -> int:
    details = json.loads(args.details.read_text(encoding="utf-8")) if args.details else {}
    event = record_phase(args.workspace, args.phase, args.status, details, args.attempt_id)
    print(event["event_id"])
    return 0


def command_run_status(args: argparse.Namespace) -> int:
    state = derive_state(args.workspace)
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
    else:
        print(f"run={state['run_id']}")
        print(f"status={state['status']}")
        print(f"events={state['event_count']}")
        print(f"next={next_phase(state) or 'none'}")
        for phase, status in state["phases"].items():
            print(f"{phase}={status}")
    return 0


def command_run_next(args: argparse.Namespace) -> int:
    phase = next_phase(derive_state(args.workspace))
    print(phase or "complete")
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
            output=workspace / "manifests" / "catalog-plan.json",
        )
    )
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
    plan.add_argument("--source-snapshot", type=Path)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    snapshot = sub.add_parser("source-snapshot", help="freeze source membership with a count and digest")
    snapshot.add_argument("--inventory", type=Path, required=True)
    snapshot.add_argument("--id-column", default="uuid")
    snapshot.add_argument("--query-id", required=True)
    snapshot.add_argument("--query-definition-version", type=int, default=1)
    snapshot.add_argument("--expected-count", type=int)
    snapshot.add_argument("--output", type=Path, required=True)
    snapshot.set_defaults(func=command_source_snapshot)

    source_verify = sub.add_parser("source-verify", help="compare an inventory with a frozen source snapshot")
    source_verify.add_argument("--inventory", type=Path, required=True)
    source_verify.add_argument("--id-column", default="uuid")
    source_verify.add_argument("--snapshot", type=Path, required=True)
    source_verify.set_defaults(func=command_source_verify)

    run_init = sub.add_parser("run-init", help="initialize an append-only run ledger")
    run_init.add_argument("--workspace", type=Path, required=True)
    run_init.add_argument("--run-id", required=True)
    run_init.add_argument("--target-count", type=int, required=True)
    run_init.add_argument("--source-snapshot", type=Path, required=True)
    run_init.add_argument("--version")
    run_init.set_defaults(func=command_run_init)

    run_record = sub.add_parser("run-record", help="append a phase event and refresh derived status")
    run_record.add_argument("--workspace", type=Path, required=True)
    run_record.add_argument("--phase", choices=PHASES, required=True)
    run_record.add_argument("--status", choices=("pending", "in_progress", "completed", "failed"), required=True)
    run_record.add_argument("--attempt-id")
    run_record.add_argument("--details", type=Path)
    run_record.set_defaults(func=command_run_record)

    run_status = sub.add_parser("run-status", help="derive current status from the append-only run ledger")
    run_status.add_argument("--workspace", type=Path, required=True)
    run_status.add_argument("--json", action="store_true")
    run_status.set_defaults(func=command_run_status)

    run_next = sub.add_parser("run-next", help="print the next incomplete run phase")
    run_next.add_argument("--workspace", type=Path, required=True)
    run_next.set_defaults(func=command_run_next)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
