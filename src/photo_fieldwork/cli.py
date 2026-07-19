from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .handoff import PUBLIC_FIELDS, build_public_handoff
from .pipeline import (
    build_catalog_plan,
    effective_final_config,
    evaluate,
    make_final_holdout,
    make_sample,
    read_config,
    read_csv,
    select,
    unsupported_view_gap_report,
    validate,
    write_csv,
)
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .review import build_review_workbench, serve_review
from .run_state import (
    append_config_decision,
    atomic_json,
    freeze_lock,
    initialize,
    record_transition,
    verify_lock,
)


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
    if args.mode == "final-holdout":
        excluded_ids: set[str] = set()
        for path in args.exclude_feedback:
            excluded_ids.update(row["uuid"] for row in read_csv(path))
        sample = make_final_holdout(
            master,
            args.sample_size,
            args.minimum_per_view,
            args.seed,
            excluded_ids,
        )
    else:
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
    print(
        f"evaluation {'PASS' if passed else 'FAIL'}: "
        f"decisive_fit_rate={report['decisive_fit_rate']}, "
        f"review_completion={report['review_completion']}, "
        f"view_sampling_coverage={report['view_sampling_coverage']}"
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
    plan = build_catalog_plan(master, config, args.plan_id, args.source_title, args.source_identifier)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def key_paths(values: list[str]) -> dict[str, Path]:
    output = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"artifact must use NAME=PATH: {value}")
        key, path = value.split("=", 1)
        if not key or not path:
            raise ValueError(f"artifact must use NAME=PATH: {value}")
        output[key] = Path(path)
    return output


def command_run_init(args: argparse.Namespace) -> int:
    state = initialize(
        args.workspace.resolve(),
        args.version,
        args.target,
        args.source_identifier,
        args.expected_source_count,
    )
    print(json.dumps(state, indent=2))
    return 0


def command_run_transition(args: argparse.Namespace) -> int:
    facts = json.loads(args.facts) if args.facts else {}
    state = record_transition(
        args.workspace.resolve(),
        args.phase,
        args.status,
        key_paths(args.input),
        key_paths(args.output),
        facts,
    )
    print(json.dumps(state["phases"][args.phase], indent=2))
    return 0


def command_freeze_final(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    intent = read_config(args.intent_config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    effective = effective_final_config(intent, master)
    effective_path = workspace / "final" / "effective-final-config.json"
    atomic_json(effective_path, effective)
    gap_report_path = workspace / "reports" / "unsupported-view-gaps.json"
    atomic_json(gap_report_path, unsupported_view_gap_report(effective))
    errors, metrics = validate(master, holds, effective)
    report = {**metrics, "errors": errors}
    report_path = workspace / "reports" / "final-replay-validation.json"
    atomic_json(report_path, report)
    if errors:
        print(json.dumps(report, indent=2))
        return 2
    record_transition(
        workspace,
        "final_freeze",
        "complete",
        {"intent_config": args.intent_config},
        {
            "effective_config": effective_path,
            "master": args.master,
            "holds": args.holds,
            "replay_validation": report_path,
            "unsupported_view_gaps": gap_report_path,
        },
        {"master_count": len(master), "hold_count": len(holds)},
    )
    additional = {
        "replay_validation": report_path,
        "unsupported_view_gaps": gap_report_path,
    }
    decisions = workspace / "config-decisions.jsonl"
    if decisions.exists():
        additional["config_decisions"] = decisions
    lock = freeze_lock(
        workspace,
        effective_path,
        args.master,
        args.holds,
        additional,
    )
    print(json.dumps(lock, indent=2))
    return 0


def command_run_verify(args: argparse.Namespace) -> int:
    errors, report = verify_lock(args.workspace.resolve())
    output = args.workspace.resolve() / "reports" / "run-lock-verification.json"
    atomic_json(output, report)
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


def json_value(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def command_run_decision(args: argparse.Namespace) -> int:
    record = append_config_decision(
        args.workspace.resolve(),
        args.round_id,
        args.field,
        json_value(args.before),
        json_value(args.after),
        args.reason,
        args.reviewer,
    )
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


def command_review_build(args: argparse.Namespace) -> int:
    sample = read_csv(args.sample)
    build_review_workbench(sample, args.previews.resolve(), args.output.resolve())
    print(f"wrote private offline review workbench to {args.output.resolve()}")
    return 0


def command_review_serve(args: argparse.Namespace) -> int:
    serve_review(args.directory.resolve(), args.host, args.port)
    return 0


def command_handoff(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    rows, errors = build_public_handoff(master, args.salt)
    write_csv(args.output, rows, list(PUBLIC_FIELDS))
    report = {
        "status": "PASS" if not errors else "FAIL",
        "input_rows": len(master),
        "public_rows": len(rows),
        "errors": errors,
        "excluded_private_fields": [
            "uuid",
            "persons",
            "albums",
            "place",
            "local_path",
            "vision_labels_all",
            "safety_reason",
            "hold membership",
            "raw OCR",
        ],
    }
    report_path = args.output.with_suffix(".report.json")
    atomic_json(report_path, report)
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


def command_demo(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    inventory = workspace / "inventory" / "practice.csv"
    config = workspace / "config.json"
    create_demo_inventory(inventory)
    config.parent.mkdir(parents=True, exist_ok=True)
    starter = files("photo_fieldwork").joinpath("resources/starter.json")
    config.write_text(starter.read_text(encoding="utf-8"), encoding="utf-8")
    write_demo_readme(workspace / "README.md")
    command_select(argparse.Namespace(config=config, inventory=inventory, output=workspace))
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(
        argparse.Namespace(
            master=workspace / "manifests" / "proposed-master.csv",
            output=sample_path,
            per_view=3,
            mode="working",
            sample_size=200,
            minimum_per_view=15,
            exclude_feedback=[],
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
    root.add_argument("--version", action="version", version=f"photo-fieldwork {__version__}")
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
    sample.add_argument("--mode", choices=("working", "final-holdout"), default="working")
    sample.add_argument("--sample-size", type=int, default=200)
    sample.add_argument("--minimum-per-view", type=int, default=15)
    sample.add_argument("--exclude-feedback", action="append", type=Path, default=[])
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
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    run = sub.add_parser("run", help="manage a durable, hash-linked run state")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_init = run_sub.add_parser("init", help="initialize a private run workspace")
    run_init.add_argument("--workspace", type=Path, required=True)
    run_init.add_argument("--version", required=True)
    run_init.add_argument("--target", type=int, required=True)
    run_init.add_argument("--source-identifier", required=True)
    run_init.add_argument("--expected-source-count", type=int)
    run_init.set_defaults(func=command_run_init)
    transition = run_sub.add_parser("transition", help="atomically record a phase attempt")
    transition.add_argument("--workspace", type=Path, required=True)
    transition.add_argument("--phase", required=True)
    transition.add_argument("--status", required=True)
    transition.add_argument("--input", action="append", default=[])
    transition.add_argument("--output", action="append", default=[])
    transition.add_argument("--facts")
    transition.set_defaults(func=command_run_transition)
    run_verify = run_sub.add_parser("verify", help="verify frozen artifact hashes")
    run_verify.add_argument("--workspace", type=Path, required=True)
    run_verify.set_defaults(func=command_run_verify)
    decision = run_sub.add_parser("decision", help="append a hash-linked config decision")
    decision.add_argument("--workspace", type=Path, required=True)
    decision.add_argument("--round-id", required=True)
    decision.add_argument("--field", required=True)
    decision.add_argument("--before", required=True)
    decision.add_argument("--after", required=True)
    decision.add_argument("--reason", required=True)
    decision.add_argument("--reviewer", required=True)
    decision.set_defaults(func=command_run_decision)

    freeze = sub.add_parser("freeze-final", help="freeze effective config and replay validation")
    freeze.add_argument("--workspace", type=Path, required=True)
    freeze.add_argument("--intent-config", type=Path, required=True)
    freeze.add_argument("--master", type=Path, required=True)
    freeze.add_argument("--holds", type=Path, required=True)
    freeze.set_defaults(func=command_freeze_final)

    review_build = sub.add_parser("review-build", help="build a private offline review workbench")
    review_build.add_argument("--sample", type=Path, required=True)
    review_build.add_argument("--previews", type=Path, required=True)
    review_build.add_argument("--output", type=Path, required=True)
    review_build.set_defaults(func=command_review_build)
    review_serve = sub.add_parser("review-serve", help="serve a workbench on loopback only")
    review_serve.add_argument("--directory", type=Path, required=True)
    review_serve.add_argument("--host", default="127.0.0.1")
    review_serve.add_argument("--port", type=int, default=0)
    review_serve.set_defaults(func=command_review_serve)

    handoff = sub.add_parser("handoff", help="build a redacted publication projection")
    handoff.add_argument("--master", type=Path, required=True)
    handoff.add_argument("--output", type=Path, required=True)
    handoff.add_argument("--salt", required=True, help="private run-specific public ID salt")
    handoff.set_defaults(func=command_handoff)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
