from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from .artifacts import diff_csv, merge_jsonl, replacement_audit, subtract_csv, union_csv, write_jsonl
from .decisions import append_decisions, apply_decisions, merge_compact_feedback, normalize_feedback
from .evaluation_split import audit_evaluation_splits
from .history import compare_versions, register_version, verify_registry
from .pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate, write_csv
from .publication import CLEARANCE_FIELDS, scaffold, validate_clearance
from .public_audit import audit_public_artifact
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .release import build_source_manifest, load_json, validate_plan
from .receipts import compare_idempotent_receipts, verify_write_receipt
from .review import build_review_surface
from .runstate import advance, initialize, load, next_phase, recover, verify


def read_source_inventory(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
        return read_csv(path)
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        rows = [{"uuid": str(row[0])} for row in connection.execute("SELECT uuid FROM asset ORDER BY uuid")]
    finally:
        connection.close()
    if not rows:
        raise ValueError(f"source inventory contains no asset UUIDs: {path}")
    return rows


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
    master = read_csv(args.master) if args.master else None
    source_manifest = load_json(args.source_manifest) if args.source_manifest else None
    report, passed = evaluate(feedback, config, master, source_manifest, args.scope)
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
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        load_json(args.source_manifest),
        read_source_inventory(args.source_inventory),
        read_csv(args.evaluation_sample),
        read_csv(args.tuning_sample) if args.tuning_sample else [],
        load_json(args.evaluation_report),
        load_json(args.validation_report),
        load_json(args.split_audit_report),
        read_csv(args.holds),
    )
    validate_plan(plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_source_freeze(args: argparse.Namespace) -> int:
    manifest = build_source_manifest(
        read_source_inventory(args.inventory),
        source_adapter=args.source_adapter,
        source_identifier=args.source_identifier,
        predicate_version=args.predicate_version,
        library_fingerprint=args.library_fingerprint,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"froze {manifest['observed_count']} source members at {args.output}")
    return 0


def command_audit_evaluation_splits(args: argparse.Namespace) -> int:
    report = audit_evaluation_splits(
        read_csv(args.tuning) if args.tuning else [],
        read_csv(args.final_holdout),
        read_csv(args.canaries) if args.canaries else [],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "leakage_count": len(report["leakage"])}, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_receipt_verify(args: argparse.Namespace) -> int:
    report = verify_write_receipt(load_json(args.plan), load_json(args.receipt))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_receipt_compare(args: argparse.Namespace) -> int:
    report = compare_idempotent_receipts(load_json(args.first), load_json(args.second))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


def command_public_audit(args: argparse.Namespace) -> int:
    report = audit_public_artifact(args.artifact)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


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
    state = advance(
        args.state,
        args.phase,
        args.receipt,
        args.note,
        expected_revision=args.expected_revision,
        attempt_id=args.attempt_id,
    )
    print(json.dumps({"phase": state["phase"], "next_phase": next_phase(state)}, indent=2))
    return 0


def command_run_verify(args: argparse.Namespace) -> int:
    state = load(args.state)
    errors = verify(state, args.state)
    report = {"phase": state["phase"], "status": "PASS" if not errors else "FAIL", "errors": errors}
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


def command_run_recover(args: argparse.Namespace) -> int:
    state = recover(args.state)
    print(json.dumps({"phase": state["phase"], "revision": state["revision"], "status": "RECOVERED"}, indent=2))
    return 0


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
    source_manifest_path = workspace / "manifests" / "source-manifest.json"
    command_source_freeze(
        argparse.Namespace(
            inventory=inventory,
            source_adapter="synthetic-fixture",
            source_identifier="SYNTHETIC-ONLY",
            predicate_version="practice-v1",
            library_fingerprint="",
            output=source_manifest_path,
        )
    )
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
    eval_code = command_evaluate(
        argparse.Namespace(
            config=config,
            feedback=sample_path,
            master=workspace / "manifests" / "proposed-master.csv",
            source_manifest=source_manifest_path,
            scope="final-holdout",
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
    split_audit_path = workspace / "reports" / "evaluation-split-audit.json"
    command_audit_evaluation_splits(
        argparse.Namespace(tuning=None, final_holdout=sample_path, canaries=None, output=split_audit_path)
    )
    command_plan(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            holds=workspace / "manifests" / "hold-sensitive.csv",
            plan_id="synthetic-practice-plan",
            source_manifest=source_manifest_path,
            source_inventory=inventory,
            evaluation_sample=sample_path,
            tuning_sample=None,
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            validation_report=workspace / "reports" / "validation-report.json",
            split_audit_report=split_audit_path,
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
    evaluation.add_argument("--master", type=Path)
    evaluation.add_argument("--source-manifest", type=Path)
    evaluation.add_argument("--scope", choices=["learning-sample", "final-holdout"], default="learning-sample")
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
    plan.add_argument("--holds", type=Path, required=True)
    plan.add_argument("--source-manifest", type=Path, required=True)
    plan.add_argument("--source-inventory", type=Path, required=True)
    plan.add_argument("--evaluation-sample", type=Path, required=True)
    plan.add_argument("--tuning-sample", type=Path)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--validation-report", type=Path, required=True)
    plan.add_argument("--split-audit-report", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    source_freeze = sub.add_parser("source-freeze", help="freeze exact source membership into a manifest")
    source_freeze.add_argument("--inventory", type=Path, required=True)
    source_freeze.add_argument("--source-adapter", required=True)
    source_freeze.add_argument("--source-identifier", required=True)
    source_freeze.add_argument("--predicate-version", required=True)
    source_freeze.add_argument("--library-fingerprint", default="")
    source_freeze.add_argument("--output", type=Path, required=True)
    source_freeze.set_defaults(func=command_source_freeze)

    split_audit = sub.add_parser("audit-evaluation-splits", help="detect UUID and related-image leakage across eval splits")
    split_audit.add_argument("--tuning", type=Path)
    split_audit.add_argument("--final-holdout", type=Path, required=True)
    split_audit.add_argument("--canaries", type=Path)
    split_audit.add_argument("--output", type=Path, required=True)
    split_audit.set_defaults(func=command_audit_evaluation_splits)

    receipt_verify = sub.add_parser("receipt-verify", help="verify a helper receipt against its exact authorized plan")
    receipt_verify.add_argument("--plan", type=Path, required=True)
    receipt_verify.add_argument("--receipt", type=Path, required=True)
    receipt_verify.add_argument("--output", type=Path)
    receipt_verify.set_defaults(func=command_receipt_verify)

    receipt_compare = sub.add_parser("receipt-compare", help="verify two distinct executions are idempotent")
    receipt_compare.add_argument("--first", type=Path, required=True)
    receipt_compare.add_argument("--second", type=Path, required=True)
    receipt_compare.add_argument("--output", type=Path)
    receipt_compare.set_defaults(func=command_receipt_compare)

    public_audit = sub.add_parser("public-audit", help="fail closed on private fields or paths in a public artifact")
    public_audit.add_argument("--artifact", type=Path, required=True)
    public_audit.add_argument("--output", type=Path)
    public_audit.set_defaults(func=command_public_audit)

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
    run_advance.add_argument("--expected-revision", type=int)
    run_advance.add_argument("--attempt-id", default="")
    run_advance.set_defaults(func=command_run_advance)

    run_verify = sub.add_parser("run-verify", help="verify all recorded phase receipts")
    run_verify.add_argument("--state", type=Path, required=True)
    run_verify.set_defaults(func=command_run_verify)

    run_recover = sub.add_parser("run-recover", help="rebuild materialized run state from its event ledger")
    run_recover.add_argument("--state", type=Path, required=True)
    run_recover.set_defaults(func=command_run_recover)

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
