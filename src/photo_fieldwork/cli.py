from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .artifacts import diff_csv, merge_jsonl, replacement_audit, subtract_csv, union_csv, write_jsonl
from .decisions import append_decisions, apply_decisions, merge_compact_feedback, normalize_feedback
from .history import compare_versions, register_version, verify_registry
from .pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate, write_csv
from .publication import CLEARANCE_FIELDS, scaffold, validate_clearance
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .review import build_review_surface
from .runstate import advance, initialize, load, next_phase, verify


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
    plan = build_catalog_plan(master, config, args.plan_id, args.source_title, args.source_identifier)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_candidate_union(args: argparse.Namespace) -> int:
    rows, report = union_csv(args.input)
    write_csv(args.output, rows)
    print(json.dumps(report, indent=2))
    return 0


def command_candidate_subtract(args: argparse.Namespace) -> int:
    rows, report = subtract_csv(args.input, args.exclude)
    write_csv(args.output, rows)
    print(json.dumps(report, indent=2))
    return 0


def command_manifest_diff(args: argparse.Namespace) -> int:
    added, removed, report = diff_csv(args.before, args.after)
    fields = []
    for row in (read_csv(args.before)[0], read_csv(args.after)[0]):
        fields.extend(field for field in row if field not in fields)
    write_csv(args.output / "added.csv", added, fields)
    write_csv(args.output / "removed.csv", removed, fields)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "diff-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def command_inspection_merge(args: argparse.Namespace) -> int:
    rows, report = merge_jsonl(args.input, args.identifier_field)
    write_jsonl(args.output, rows)
    print(json.dumps(report, indent=2))
    return 0


def command_replacement_audit(args: argparse.Namespace) -> int:
    entrants, report = replacement_audit(args.master, args.evaluated)
    write_csv(args.output, entrants, list(read_csv(args.master)[0]))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_decisions_append(args: argparse.Namespace) -> int:
    existing = read_csv(args.ledger) if args.ledger.exists() else []
    incoming = normalize_feedback(read_csv(args.feedback), args.round_id, args.reviewer_actor)
    ledger = append_decisions(existing, incoming)
    write_csv(args.ledger, ledger)
    print(f"appended {len(ledger) - len(existing)} decisions; ledger rows={len(ledger)}")
    return 0


def command_decisions_apply(args: argparse.Namespace) -> int:
    inventory = read_csv(args.inventory)
    decisions = read_csv(args.ledger)
    rows, report = apply_decisions(inventory, decisions, not args.no_propagate_holds)
    write_csv(args.output, rows)
    print(json.dumps(report, indent=2))
    return 0


def command_feedback_merge(args: argparse.Namespace) -> int:
    rows = merge_compact_feedback(read_csv(args.sample), read_csv(args.feedback))
    write_csv(args.output, rows)
    print(f"wrote {len(rows)} merged feedback rows")
    return 0


def command_run_init(args: argparse.Namespace) -> int:
    state = initialize(args.state, args.run_id, args.target, args.source_identifier)
    print(json.dumps(state, indent=2))
    return 0


def command_run_advance(args: argparse.Namespace) -> int:
    state = advance(args.state, args.phase, args.receipt, args.note)
    print(json.dumps({"phase": state["phase"], "next_phase": next_phase(state)}, indent=2))
    return 0


def command_run_verify(args: argparse.Namespace) -> int:
    state = load(args.state)
    errors = verify(state)
    report = {"phase": state["phase"], "status": "PASS" if not errors else "FAIL", "errors": errors}
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


def command_review(args: argparse.Namespace) -> int:
    report = build_review_surface(read_csv(args.sample), args.previews, args.output)
    print(json.dumps(report, indent=2))
    return 0


def command_publication_scaffold(args: argparse.Namespace) -> int:
    rows = scaffold(read_csv(args.master))
    write_csv(args.output, rows, CLEARANCE_FIELDS)
    print(f"wrote {len(rows)} uncleared publication review rows")
    return 0


def command_publication_validate(args: argparse.Namespace) -> int:
    errors, report = validate_clearance(read_csv(args.clearance))
    report["errors"] = errors
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


def command_version_register(args: argparse.Namespace) -> int:
    entry = register_version(
        args.registry,
        args.version,
        args.manifest,
        args.source_identifier,
        args.source_count,
        args.album_identifier,
        args.verification_receipt,
    )
    print(json.dumps(entry, indent=2))
    return 0


def command_version_verify(args: argparse.Namespace) -> int:
    errors, report = verify_registry(args.registry)
    report["errors"] = errors
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


def command_version_compare(args: argparse.Namespace) -> int:
    print(json.dumps(compare_versions(args.before, args.after), indent=2))
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
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    union = sub.add_parser("candidate-union", help="merge candidate CSVs without conflicting duplicate UUIDs")
    union.add_argument("--input", type=Path, action="append", required=True)
    union.add_argument("--output", type=Path, required=True)
    union.set_defaults(func=command_candidate_union)

    subtract = sub.add_parser("candidate-subtract", help="remove UUIDs already present in one or more CSVs")
    subtract.add_argument("--input", type=Path, required=True)
    subtract.add_argument("--exclude", type=Path, action="append", required=True)
    subtract.add_argument("--output", type=Path, required=True)
    subtract.set_defaults(func=command_candidate_subtract)

    difference = sub.add_parser("manifest-diff", help="report manifest additions, removals, and changed rows")
    difference.add_argument("--before", type=Path, required=True)
    difference.add_argument("--after", type=Path, required=True)
    difference.add_argument("--output", type=Path, required=True)
    difference.set_defaults(func=command_manifest_diff)

    inspection = sub.add_parser("inspection-merge", help="merge nonconflicting inspection JSONL batches")
    inspection.add_argument("--input", type=Path, action="append", required=True)
    inspection.add_argument("--identifier-field", default="asset_identifier")
    inspection.add_argument("--output", type=Path, required=True)
    inspection.set_defaults(func=command_inspection_merge)

    entrants = sub.add_parser("replacement-audit", help="identify final entrants absent from evaluation records")
    entrants.add_argument("--master", type=Path, required=True)
    entrants.add_argument("--evaluated", type=Path, action="append", required=True)
    entrants.add_argument("--output", type=Path, required=True)
    entrants.set_defaults(func=command_replacement_audit)

    decisions_append = sub.add_parser("decisions-append", help="append normalized judgments to a durable ledger")
    decisions_append.add_argument("--feedback", type=Path, required=True)
    decisions_append.add_argument("--ledger", type=Path, required=True)
    decisions_append.add_argument("--round-id", default="")
    decisions_append.add_argument("--reviewer-actor", default="")
    decisions_append.set_defaults(func=command_decisions_append)

    decisions_apply = sub.add_parser("decisions-apply", help="apply the latest ledger decisions to candidates")
    decisions_apply.add_argument("--inventory", type=Path, required=True)
    decisions_apply.add_argument("--ledger", type=Path, required=True)
    decisions_apply.add_argument("--output", type=Path, required=True)
    decisions_apply.add_argument("--no-propagate-holds", action="store_true")
    decisions_apply.set_defaults(func=command_decisions_apply)

    feedback_merge = sub.add_parser("feedback-merge", help="merge compact reviewer feedback into a full sample")
    feedback_merge.add_argument("--sample", type=Path, required=True)
    feedback_merge.add_argument("--feedback", type=Path, required=True)
    feedback_merge.add_argument("--output", type=Path, required=True)
    feedback_merge.set_defaults(func=command_feedback_merge)

    run_init = sub.add_parser("run-init", help="initialize a resumable phase state file")
    run_init.add_argument("--state", type=Path, required=True)
    run_init.add_argument("--run-id", required=True)
    run_init.add_argument("--target", type=int, required=True)
    run_init.add_argument("--source-identifier", required=True)
    run_init.set_defaults(func=command_run_init)

    run_advance = sub.add_parser("run-advance", help="advance one phase and hash its receipt files")
    run_advance.add_argument("--state", type=Path, required=True)
    run_advance.add_argument("--phase", required=True)
    run_advance.add_argument("--receipt", type=Path, action="append", default=[])
    run_advance.add_argument("--note", default="")
    run_advance.set_defaults(func=command_run_advance)

    run_verify = sub.add_parser("run-verify", help="verify all recorded phase receipts")
    run_verify.add_argument("--state", type=Path, required=True)
    run_verify.set_defaults(func=command_run_verify)

    review = sub.add_parser("review", help="build a local offline editorial review surface")
    review.add_argument("--sample", type=Path, required=True)
    review.add_argument("--previews", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    review.set_defaults(func=command_review)

    publication_scaffold = sub.add_parser("publication-scaffold", help="create an uncleared publication manifest")
    publication_scaffold.add_argument("--master", type=Path, required=True)
    publication_scaffold.add_argument("--output", type=Path, required=True)
    publication_scaffold.set_defaults(func=command_publication_scaffold)

    publication_validate = sub.add_parser("publication-validate", help="validate rows explicitly cleared for publication")
    publication_validate.add_argument("--clearance", type=Path, required=True)
    publication_validate.set_defaults(func=command_publication_validate)

    version_register = sub.add_parser("version-register", help="register an immutable version manifest and evidence")
    version_register.add_argument("--registry", type=Path, required=True)
    version_register.add_argument("--version", required=True)
    version_register.add_argument("--manifest", type=Path, required=True)
    version_register.add_argument("--source-identifier", required=True)
    version_register.add_argument("--source-count", type=int, required=True)
    version_register.add_argument("--album-identifier", default="")
    version_register.add_argument("--verification-receipt", type=Path)
    version_register.set_defaults(func=command_version_register)

    version_verify = sub.add_parser("version-verify", help="verify registered manifests and receipts remain unchanged")
    version_verify.add_argument("--registry", type=Path, required=True)
    version_verify.set_defaults(func=command_version_verify)

    version_compare = sub.add_parser("version-compare", help="measure overlap and change between two manifests")
    version_compare.add_argument("--before", type=Path, required=True)
    version_compare.add_argument("--after", type=Path, required=True)
    version_compare.set_defaults(func=command_version_compare)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
