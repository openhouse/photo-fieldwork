from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .eval_split import audit_eval_split
from .feedback import apply_feedback
from .handoff import PUBLIC_FIELDS, build_public_handoff
from .integrity import create_evaluation_seal, evaluate_freshness
from .pipeline import build_catalog_plan, evaluate, make_sample, read_config, read_csv, select, validate, write_csv
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .release import compare_execution_receipts, verify_execution_receipt
from .source import build_source_profile, read_source_profile
from .state import initialize_run, recover_state, sha256_file, transition_phase


DEFAULT_PHASES = [
    "brief",
    "retrieval",
    "local_inspection",
    "recursive_evaluation",
    "validation",
    "write_test",
    "production_commit",
    "independent_verification",
]


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
    print(f"wrote {len(sample)} evaluation rows to {args.output}; sample_hash={sample[0]['sample_hash']}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    master = read_csv(args.master)
    args.output.mkdir(parents=True, exist_ok=True)
    seal_path = args.output / "evaluation-seal.json"
    seal_path.unlink(missing_ok=True)
    report, passed = evaluate(feedback, config)
    (args.output / "evaluation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "evaluation-report.md").write_text(markdown_report("Evaluation report", report), encoding="utf-8")
    if passed:
        seal = create_evaluation_seal(master, config, report)
        seal_path.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    print(
        f"evaluation {'PASS' if passed else 'FAIL'}: "
        f"decisive_precision={report['decisive_precision']}, "
        f"uncertainty_rate={report['uncertainty_rate']}, coverage={report['coverage']}"
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
    holds_path = getattr(args, "holds", None)
    source_profile_path = getattr(args, "source_profile", None)
    source_title = getattr(args, "source_title", None)
    source_identifier = getattr(args, "source_identifier", None)
    holds = read_csv(holds_path) if holds_path else []
    source_profile = read_source_profile(source_profile_path) if source_profile_path else None
    evaluation_seal = json.loads(args.evaluation_seal.read_text(encoding="utf-8"))
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    helper_profile = json.loads(args.helper_profile.read_text(encoding="utf-8"))
    if source_profile is None and (not source_title or not source_identifier):
        raise ValueError("provide --source-profile or both --source-title and --source-identifier")
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        source_title or (source_profile or {}).get("scope", ""),
        source_identifier or (source_profile or {}).get("id", ""),
        source_profile=source_profile,
        holds=holds,
        evaluation_seal=evaluation_seal,
        evaluation_report=evaluation_report,
        helper_profile=helper_profile,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_source_profile(args: argparse.Namespace) -> int:
    if args.inventory.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        connection = sqlite3.connect(f"file:{args.inventory}?mode=ro&immutable=1", uri=True, timeout=60)
        try:
            profile = build_source_profile(
                ({"uuid": row[0]} for row in connection.execute("SELECT uuid FROM asset")),
                profile_id=args.id,
                kind=args.kind,
                scope=args.scope,
                inventory=str(args.inventory.resolve()),
            )
        finally:
            connection.close()
    else:
        inventory = read_csv(args.inventory)
        profile = build_source_profile(
            inventory,
            profile_id=args.id,
            kind=args.kind,
            scope=args.scope,
            inventory=str(args.inventory.resolve()),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(f"source_count={profile['actual_count']}")
    print(f"source_fingerprint={profile['fingerprint']}")
    print(f"profile={args.output}")
    return 0


def command_init_run(args: argparse.Namespace) -> int:
    phases = args.phase or DEFAULT_PHASES
    state = initialize_run(
        args.run.resolve(),
        run_id=args.run_id or args.run.name,
        phases=phases,
        metadata={"version": args.version, "target_count": args.target},
    )
    for directory in ("inventory", "manifests", "reports", "logs", "previews", "contact-sheets"):
        (args.run / directory).mkdir(parents=True, exist_ok=True)
    print(json.dumps(state, indent=2))
    return 0


def command_transition(args: argparse.Namespace) -> int:
    state = transition_phase(
        args.run.resolve(),
        args.phase,
        args.status,
        expected_revision=args.expected_revision,
        artifact=args.artifact.resolve() if args.artifact else None,
        note=args.note,
        attempt_id=args.attempt_id,
    )
    print(json.dumps(state, indent=2))
    return 0


def command_status(args: argparse.Namespace) -> int:
    state = recover_state(args.run.resolve())
    print(json.dumps(state, indent=2))
    return 0


def command_apply_feedback(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    sample = read_csv(args.sample)
    feedback = read_csv(args.feedback)
    reviewed, removed, report = apply_feedback(master, sample, feedback)
    manifests = args.output / "manifests"
    reports = args.output / "reports"
    master_fields = list(master[0])
    feedback_fields = [
        "last_judgment",
        "last_visible_reason",
        "last_error_category",
        "last_round_id",
        "last_reviewer_lens",
        "last_reviewer_actor",
    ]
    fields = master_fields + [field for field in feedback_fields if field not in master_fields]
    write_csv(manifests / "reviewed-master.csv", reviewed, fieldnames=fields)
    write_csv(manifests / "feedback-removed.csv", removed, fieldnames=fields)
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "feedback-policy.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (reports / "feedback-policy.md").write_text(markdown_report("Feedback policy", report), encoding="utf-8")
    print(f"decisions_applied={report['decisions_applied']}")
    print(f"removed={report['removed_count']}")
    print(f"requires_reselection={str(report['requires_reselection']).lower()}")
    return 0


def command_freshness(args: argparse.Namespace) -> int:
    sample = read_csv(args.sample)
    prior = []
    for path in args.prior_feedback:
        prior.extend(read_csv(path))
    report = evaluate_freshness(
        [row["uuid"] for row in sample],
        [row["uuid"] for row in prior],
        minimum_fresh_fraction=args.minimum_fresh_fraction,
        require_disjoint=args.require_disjoint,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "freshness-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "freshness-report.md").write_text(markdown_report("Freshness report", report), encoding="utf-8")
    print(
        f"freshness {'PASS' if report['passed'] else 'FAIL'}: "
        f"fresh_fraction={report['fresh_fraction']}, reused={report['reused_count']}"
    )
    return 0 if report["passed"] else 2


def command_split_audit(args: argparse.Namespace) -> int:
    tuning = []
    canaries = []
    for path in args.tuning:
        tuning.extend(read_csv(path))
    for path in args.canary:
        canaries.extend(read_csv(path))
    report = audit_eval_split(
        tuning,
        read_csv(args.holdout),
        canaries,
        include_private_details=args.include_private_details,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"split_audit={'PASS' if report['passed'] else 'FAIL'}")
    print(f"report={args.output}")
    return 0 if report["passed"] else 2


def command_verify_receipt(args: argparse.Namespace) -> int:
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    helper = json.loads(args.helper_profile.read_text(encoding="utf-8"))
    errors = verify_execution_receipt(receipt, plan, helper, sha256_file(args.plan))
    report = {
        "schema_version": 1,
        "passed": not errors,
        "errors": errors,
        "plan_id": plan.get("plan_id"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"receipt_verification={'PASS' if report['passed'] else 'FAIL'}")
    return 0 if report["passed"] else 2


def command_compare_receipts(args: argparse.Namespace) -> int:
    first = json.loads(args.first.read_text(encoding="utf-8"))
    second = json.loads(args.second.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    helper = json.loads(args.helper_profile.read_text(encoding="utf-8"))
    report = compare_execution_receipts(first, second, plan, helper)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"idempotence={'PASS' if report['passed'] else 'FAIL'}")
    return 0 if report["passed"] else 2


def command_handoff(args: argparse.Namespace) -> int:
    rows = read_csv(args.master)
    salt = args.salt_file.read_text(encoding="utf-8").strip()
    output, errors = build_public_handoff(rows, salt)
    report = {
        "schema_version": 1,
        "passed": not errors,
        "source_count": len(rows),
        "public_count": len(output) if not errors else 0,
        "blocked_error_count": len(errors),
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if errors:
        args.output.unlink(missing_ok=True)
    else:
        write_csv(args.output, output, fieldnames=list(PUBLIC_FIELDS))
    print(f"public_handoff={'PASS' if report['passed'] else 'FAIL'}")
    print(f"public_count={report['public_count']}")
    return 0 if report["passed"] else 2


def command_demo(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    workspace = args.workspace.resolve()
    inventory = workspace / "inventory" / "practice.csv"
    config = workspace / "config.json"
    create_demo_inventory(inventory)
    source_profile_path = workspace / "inventory" / "source-profile.json"
    source_profile = build_source_profile(
        read_csv(inventory),
        profile_id="synthetic-practice://v1",
        kind="synthetic-csv",
        scope="synthetic practice corpus",
        inventory=str(inventory),
    )
    source_profile_path.write_text(json.dumps(source_profile, indent=2) + "\n", encoding="utf-8")
    helper_profile_path = workspace / "inventory" / "helper-profile.json"
    helper_profile_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bundle_identifier": "org.openhouse.synthetic-photo-helper",
                "binary_sha256": "sha256:" + "1" * 64,
                "capabilities": [
                    "membership-only-write",
                    "receipt-plan-digest",
                    "launch-nonce",
                    "exact-folder-topology",
                ],
                "supported_plan_schema_versions": [2],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
    eval_code = command_evaluate(
        argparse.Namespace(
            config=config,
            feedback=sample_path,
            master=workspace / "manifests" / "proposed-master.csv",
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
            plan_id="synthetic-practice-plan",
            source_title="Synthetic practice corpus",
            source_identifier="SYNTHETIC-ONLY",
            source_profile=source_profile_path,
            holds=workspace / "manifests" / "hold-sensitive.csv",
            evaluation_seal=workspace / "reports" / "evaluation-seal.json",
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            helper_profile=helper_profile_path,
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
    evaluation.add_argument("--master", type=Path, required=True, help="exact candidate being authorized")
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
    plan.add_argument("--source-title")
    plan.add_argument("--source-identifier")
    plan.add_argument("--source-profile", type=Path)
    plan.add_argument("--holds", type=Path)
    plan.add_argument("--evaluation-seal", type=Path, required=True)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--helper-profile", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    source = sub.add_parser("source-profile", help="fingerprint a frozen source inventory")
    source.add_argument("--inventory", type=Path, required=True)
    source.add_argument("--id", required=True)
    source.add_argument("--kind", required=True)
    source.add_argument("--scope", required=True)
    source.add_argument("--output", type=Path, required=True)
    source.set_defaults(func=command_source_profile)

    init_run = sub.add_parser("init-run", help="initialize an atomic, resumable run ledger")
    init_run.add_argument("--run", type=Path, required=True)
    init_run.add_argument("--run-id")
    init_run.add_argument("--version", required=True)
    init_run.add_argument("--target", type=int, required=True)
    init_run.add_argument("--phase", action="append", help="repeat to override the default phase sequence")
    init_run.set_defaults(func=command_init_run)

    transition = sub.add_parser("transition", help="record an atomic phase transition")
    transition.add_argument("--run", type=Path, required=True)
    transition.add_argument("--phase", required=True)
    transition.add_argument(
        "--status", required=True, choices=["started", "completed", "failed", "blocked", "superseded"]
    )
    transition.add_argument("--expected-revision", type=int)
    transition.add_argument("--artifact", type=Path)
    transition.add_argument("--note", default="")
    transition.add_argument("--attempt-id", required=True)
    transition.set_defaults(func=command_transition)

    status = sub.add_parser("status", help="recover and show run state from the event ledger")
    status.add_argument("run", type=Path)
    status.set_defaults(func=command_status)

    feedback = sub.add_parser("apply-feedback", help="apply UUID-keyed review decisions without positional joins")
    feedback.add_argument("--master", type=Path, required=True)
    feedback.add_argument("--sample", type=Path, required=True)
    feedback.add_argument("--feedback", type=Path, required=True)
    feedback.add_argument("--output", type=Path, required=True)
    feedback.set_defaults(func=command_apply_feedback)

    freshness = sub.add_parser("freshness", help="measure holdout reuse against prior tuning rounds")
    freshness.add_argument("--sample", type=Path, required=True)
    freshness.add_argument("--prior-feedback", type=Path, action="append", required=True)
    freshness.add_argument("--minimum-fresh-fraction", type=float, default=1.0)
    freshness.add_argument("--require-disjoint", action="store_true")
    freshness.add_argument("--output", type=Path, required=True)
    freshness.set_defaults(func=command_freshness)

    split = sub.add_parser("split-audit", help="audit final holdout UUID and relationship-cluster isolation")
    split.add_argument("--tuning", type=Path, action="append", required=True)
    split.add_argument("--holdout", type=Path, required=True)
    split.add_argument("--canary", type=Path, action="append", default=[])
    split.add_argument("--include-private-details", action="store_true")
    split.add_argument("--output", type=Path, required=True)
    split.set_defaults(func=command_split_audit)

    receipt = sub.add_parser("verify-receipt", help="bind a helper receipt to an authorized release plan")
    receipt.add_argument("--receipt", type=Path, required=True)
    receipt.add_argument("--plan", type=Path, required=True)
    receipt.add_argument("--helper-profile", type=Path, required=True)
    receipt.add_argument("--output", type=Path, required=True)
    receipt.set_defaults(func=command_verify_receipt)

    idempotence = sub.add_parser("compare-receipts", help="verify two distinct equivalent executions")
    idempotence.add_argument("--first", type=Path, required=True)
    idempotence.add_argument("--second", type=Path, required=True)
    idempotence.add_argument("--plan", type=Path, required=True)
    idempotence.add_argument("--helper-profile", type=Path, required=True)
    idempotence.add_argument("--output", type=Path, required=True)
    idempotence.set_defaults(func=command_compare_receipts)

    handoff = sub.add_parser("handoff", help="build an allowlisted, opaque-ID public projection")
    handoff.add_argument("--master", type=Path, required=True)
    handoff.add_argument("--salt-file", type=Path, required=True)
    handoff.add_argument("--output", type=Path, required=True)
    handoff.add_argument("--report", type=Path, required=True)
    handoff.set_defaults(func=command_handoff)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
