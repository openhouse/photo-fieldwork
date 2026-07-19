from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .artifacts import build_source_snapshot, verify_source_snapshot
from .integrity import create_release_seal, row_artifact_fingerprint, verify_release_seal
from .pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate, write_csv
from .publication import CLEARANCE_FIELDS, scaffold, validate_clearance
from .receipts import audit_idempotence_evidence
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .run_ledger import PHASES, derive_state, initialize_run, next_phase, record_phase
from .splits import audit_split


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


def read_csv_allow_empty(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def command_select(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    inventory = read_csv(args.inventory)
    master, holds, summary = select(inventory, config)
    output = args.output
    write_csv(output / "manifests" / "proposed-master.csv", master)
    write_csv(
        output / "manifests" / "hold-sensitive.csv",
        holds,
        list(inventory[0]) if not holds else None,
    )
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
    master = read_csv(args.master)
    master_ids = {row["uuid"].strip() for row in master}
    feedback_ids = {row["uuid"].strip() for row in feedback}
    unexpected = sorted(feedback_ids - master_ids)
    if unexpected:
        raise ValueError(f"evaluation contains UUIDs outside the master: {', '.join(unexpected)}")
    report, passed = evaluate(feedback, config)
    report["master_count"] = len(master)
    report["master_fingerprint"] = row_artifact_fingerprint(master)
    report["evaluated_sample_fingerprint"] = row_artifact_fingerprint(feedback)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    print(f"evaluation {'PASS' if passed else 'FAIL'}: precision={report['precision']}, coverage={report['coverage']}")
    return 0 if passed else 2


def command_validate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv_allow_empty(args.holds)
    errors, metrics = validate(master, holds, config)
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(metrics)
    report["errors"] = errors
    report["master_fingerprint"] = row_artifact_fingerprint(master)
    report["holds_fingerprint"] = row_artifact_fingerprint(holds, allow_empty=True)
    (args.output / "validation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "validation-report.md").write_text(markdown_report("Validation report", report), encoding="utf-8")
    print(f"validation {metrics['status']}")
    return 0 if not errors else 2


def command_plan(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv_allow_empty(args.holds)
    source_snapshot = json.loads(args.source_snapshot.read_text(encoding="utf-8"))
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    validation_report = json.loads(args.validation_report.read_text(encoding="utf-8"))
    release_seal = json.loads(args.release_seal.read_text(encoding="utf-8"))
    seal_errors = verify_release_seal(
        release_seal,
        master,
        holds,
        config,
        source_snapshot,
        evaluation_report,
        validation_report,
    )
    if seal_errors:
        raise ValueError("release seal verification failed: " + "; ".join(seal_errors))
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        source_snapshot,
        release_seal["seal_fingerprint"],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_release_seal(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    holds = read_csv_allow_empty(args.holds)
    config = read_config(args.config)
    source_snapshot = json.loads(args.source_snapshot.read_text(encoding="utf-8"))
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    validation_report = json.loads(args.validation_report.read_text(encoding="utf-8"))
    seal = create_release_seal(
        master,
        holds,
        config,
        source_snapshot,
        evaluation_report,
        validation_report,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    print(f"release_seal={seal['seal_fingerprint']}")
    return 0


def command_publication_scaffold(args: argparse.Namespace) -> int:
    rows = scaffold(read_csv(args.master))
    write_csv(args.output, rows, CLEARANCE_FIELDS)
    print(f"publication_rows={len(rows)}")
    print("publication_cleared=0")
    return 0


def command_publication_validate(args: argparse.Namespace) -> int:
    master_ids = {row["uuid"].strip() for row in read_csv(args.master)}
    rows = read_csv(args.ledger)
    errors, report = validate_clearance(rows, master_ids=master_ids)
    report["errors"] = errors
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"publication_validation={report['status']}")
    return 0 if not errors else 2


def command_split_audit(args: argparse.Namespace) -> int:
    tuning = [row for path in args.tuning for row in read_csv(path)]
    holdout = read_csv(args.holdout)
    canaries = [row for path in args.canary for row in read_csv(path)]
    report = audit_split(tuning, holdout, canaries, include_identifiers=args.include_identifiers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"split_audit={report['status']}")
    return 0 if report["status"] == "PASS" else 2


def command_idempotence_audit(args: argparse.Namespace) -> int:
    attempts = [json.loads(path.read_text(encoding="utf-8")) for path in args.attempt]
    verifications = [json.loads(path.read_text(encoding="utf-8")) for path in args.verification]
    report = audit_idempotence_evidence(attempts, verifications, args.plan_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"idempotence_audit={report['status']}")
    return 0 if report["status"] == "PASS" else 2


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
    master_path = workspace / "manifests" / "proposed-master.csv"
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
        argparse.Namespace(config=config, feedback=sample_path, master=master_path, output=workspace / "reports")
    )
    validation_code = command_validate(
        argparse.Namespace(
            config=config,
            master=workspace / "manifests" / "proposed-master.csv",
            holds=workspace / "manifests" / "hold-sensitive.csv",
            output=workspace / "reports",
        )
    )
    holds_path = workspace / "manifests" / "hold-sensitive.csv"
    source_snapshot_path = workspace / "source-snapshot.json"
    source_snapshot = build_source_snapshot(
        [row["uuid"] for row in read_csv(inventory)],
        "synthetic-practice://v1",
    )
    source_snapshot_path.write_text(json.dumps(source_snapshot, indent=2) + "\n", encoding="utf-8")
    seal_path = workspace / "reports" / "release-seal.json"
    command_release_seal(
        argparse.Namespace(
            master=master_path,
            holds=holds_path,
            config=config,
            source_snapshot=source_snapshot_path,
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            validation_report=workspace / "reports" / "validation-report.json",
            output=seal_path,
        )
    )
    command_plan(
        argparse.Namespace(
            config=config,
            master=master_path,
            holds=holds_path,
            plan_id="synthetic-practice-plan",
            source_title="Synthetic practice corpus",
            source_identifier="SYNTHETIC-ONLY",
            source_snapshot=source_snapshot_path,
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            validation_report=workspace / "reports" / "validation-report.json",
            release_seal=seal_path,
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
    evaluation.add_argument("--master", type=Path, required=True)
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
    plan.add_argument("--source-snapshot", type=Path, required=True)
    plan.add_argument("--holds", type=Path, required=True)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--validation-report", type=Path, required=True)
    plan.add_argument("--release-seal", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    seal = sub.add_parser("release-seal", help="bind the exact candidate and passing release evidence")
    seal.add_argument("--master", type=Path, required=True)
    seal.add_argument("--holds", type=Path, required=True)
    seal.add_argument("--config", type=Path, required=True)
    seal.add_argument("--source-snapshot", type=Path, required=True)
    seal.add_argument("--evaluation-report", type=Path, required=True)
    seal.add_argument("--validation-report", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    seal.set_defaults(func=command_release_seal)

    publication_scaffold = sub.add_parser("publication-scaffold", help="create a default-closed publication ledger")
    publication_scaffold.add_argument("--master", type=Path, required=True)
    publication_scaffold.add_argument("--output", type=Path, required=True)
    publication_scaffold.set_defaults(func=command_publication_scaffold)

    publication_validate = sub.add_parser("publication-validate", help="validate explicit per-asset publication clearance")
    publication_validate.add_argument("--master", type=Path, required=True)
    publication_validate.add_argument("--ledger", type=Path, required=True)
    publication_validate.add_argument("--output", type=Path, required=True)
    publication_validate.set_defaults(func=command_publication_validate)

    split_audit = sub.add_parser("split-audit", help="audit tuning, holdout, and canary independence")
    split_audit.add_argument("--tuning", type=Path, action="append", required=True)
    split_audit.add_argument("--holdout", type=Path, required=True)
    split_audit.add_argument("--canary", type=Path, action="append", default=[])
    split_audit.add_argument("--include-identifiers", action="store_true")
    split_audit.add_argument("--output", type=Path, required=True)
    split_audit.set_defaults(func=command_split_audit)

    idempotence = sub.add_parser("idempotence-audit", help="verify two distinct executions and their independent checks")
    idempotence.add_argument("--attempt", type=Path, action="append", required=True)
    idempotence.add_argument("--verification", type=Path, action="append", required=True)
    idempotence.add_argument("--plan-sha256", required=True)
    idempotence.add_argument("--output", type=Path, required=True)
    idempotence.set_defaults(func=command_idempotence_audit)

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
