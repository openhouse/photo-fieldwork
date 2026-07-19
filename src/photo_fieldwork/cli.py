from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .evals import audit_paths
from .handoff import PUBLIC_FIELDS, build_public_handoff
from .integrity import (
    RELATION_FIELDS,
    evaluation_sample_sha256,
    membership_sha256,
    relation_leakage_report,
)
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
from .release import begin_execution, complete_execution, idempotence_report, register_plan
from .review import build_review_workbench, serve_review
from .run_state import (
    append_config_decision,
    atomic_json,
    freeze_lock,
    initialize,
    record_invalidation,
    record_transition,
    recover_state,
    read_state,
    sha256_file,
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
        prior_rows: list[dict[str, str]] = []
        for path in args.exclude_feedback:
            rows = read_csv(path)
            missing_relations = set(RELATION_FIELDS) - set(rows[0])
            if missing_relations:
                raise ValueError(
                    f"prior feedback {path} lacks relation columns: "
                    + ", ".join(sorted(missing_relations))
                )
            prior_rows.extend(rows)
            excluded_ids.update(row["uuid"] for row in rows)
        candidate_leakage = relation_leakage_report(master, prior_rows)
        sample = make_final_holdout(
            master,
            args.sample_size,
            args.minimum_per_view,
            args.seed,
            excluded_ids,
            prior_rows,
        )
        final_leakage = relation_leakage_report(sample, prior_rows)
        leakage = {
            **final_leakage,
            "sample_sha256": evaluation_sample_sha256(sample),
            "excluded_candidate_count": len(
                {item["sample_uuid"] for item in candidate_leakage["collisions"]}
            ),
            "excluded_candidate_collisions": candidate_leakage["collisions"],
            "replacement_uuids": sorted(row["uuid"] for row in sample),
            "replacement_relation_audit": final_leakage["status"],
        }
        leakage_path = args.output.with_suffix(".leakage.json")
        atomic_json(leakage_path, leakage)
        if leakage["status"] != "PASS":
            raise ValueError(f"final holdout relation leakage: {leakage_path}")
    else:
        sample = make_sample(master, args.per_view, args.seed)
    write_csv(args.output, sample)
    print(f"wrote {len(sample)} evaluation rows to {args.output}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    leakage = None
    if feedback and all(
        row.get("sample_role", "").startswith("final-holdout")
        or row.get("sample_role", "") == "regression-canary"
        for row in feedback
    ):
        leakage_path = getattr(args, "leakage_report", None) or args.feedback.with_suffix(
            ".leakage.json"
        )
        if not leakage_path.is_file():
            raise ValueError(f"final holdout requires leakage report: {leakage_path}")
        leakage = json.loads(leakage_path.read_text(encoding="utf-8"))
        fresh = [row for row in feedback if row.get("sample_role") != "regression-canary"]
        if leakage.get("sample_sha256") != evaluation_sample_sha256(fresh):
            raise ValueError("final holdout leakage report does not match the evaluated sample")
    report, passed = evaluate(feedback, config, leakage)
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
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    validation_report = json.loads(args.validation_report.read_text(encoding="utf-8"))
    run_lock = None
    run_lock_digest = None
    if args.release_class == "editor-field":
        if args.workspace is None:
            raise ValueError("editor-field plan requires --workspace")
        workspace = args.workspace.resolve()
        errors, _ = verify_lock(workspace)
        if errors:
            raise ValueError("run lock verification failed: " + "; ".join(errors))
        run_lock_path = workspace / "run-lock.json"
        run_lock = json.loads(run_lock_path.read_text(encoding="utf-8"))
        run_lock_digest = sha256_file(run_lock_path)
        state_source = read_state(workspace).get("source", {})
        supplied_source = {
            "identifier": args.source_identifier,
            "expected_count": args.source_count,
            "membership_sha256": args.source_membership_sha256.strip().lower(),
        }
        if supplied_source != state_source:
            raise ValueError("plan source identity does not match the frozen run source")
        locked = run_lock.get("artifacts", {})
        if locked.get("master", {}).get("sha256") != sha256_file(args.master):
            raise ValueError("--master does not match the verified run lock")
        if locked.get("effective_config", {}).get("sha256") != sha256_file(args.config):
            raise ValueError("--config does not match the verified run lock")
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        source_count=args.source_count,
        source_membership_sha256=args.source_membership_sha256,
        evaluation_report=evaluation_report,
        validation_report=validation_report,
        run_lock=run_lock,
        run_lock_sha256=run_lock_digest,
        release_class=args.release_class,
    )
    atomic_json(args.output, plan)
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
        args.source_membership_sha256,
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
        args.expected_revision,
    )
    print(json.dumps(state["phases"][args.phase], indent=2))
    return 0


def command_run_recover(args: argparse.Namespace) -> int:
    state = recover_state(args.workspace.resolve())
    print(json.dumps(state, indent=2))
    return 0 if state["recovery_report"]["status"] == "PASS" else 2


def command_run_invalidate(args: argparse.Namespace) -> int:
    state = record_invalidation(
        args.workspace.resolve(),
        args.phase,
        args.reason,
        args.expected_revision,
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


def command_release_register(args: argparse.Namespace) -> int:
    result = register_plan(args.workspace.resolve(), args.plan.resolve())
    print(json.dumps(result, indent=2))
    return 0


def command_release_begin(args: argparse.Namespace) -> int:
    result = begin_execution(
        args.workspace.resolve(),
        args.kind,
        args.adapter_plan.resolve(),
    )
    print(json.dumps(result, indent=2))
    return 0


def command_release_complete(args: argparse.Namespace) -> int:
    result = complete_execution(
        args.workspace.resolve(),
        args.execution_nonce,
        args.receipt.resolve(),
    )
    print(json.dumps(result, indent=2))
    return 0


def command_release_idempotence(args: argparse.Namespace) -> int:
    result = idempotence_report(args.workspace.resolve())
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


def command_evals_check(args: argparse.Namespace) -> int:
    errors, report = audit_paths(args.evals, args.contract)
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
            source_count=len(read_csv(inventory)),
            source_membership_sha256=membership_sha256(
                row["uuid"] for row in read_csv(inventory)
            ),
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            validation_report=workspace / "reports" / "validation-report.json",
            release_class="synthetic-practice",
            workspace=None,
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
    evaluation.add_argument("--leakage-report", type=Path)
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
    plan.add_argument("--source-count", type=int, required=True)
    plan.add_argument("--source-membership-sha256", required=True)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--validation-report", type=Path, required=True)
    plan.add_argument(
        "--release-class",
        choices=("synthetic-practice", "editor-field"),
        default="editor-field",
    )
    plan.add_argument("--workspace", type=Path)
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
    run_init.add_argument("--source-membership-sha256")
    run_init.set_defaults(func=command_run_init)
    transition = run_sub.add_parser("transition", help="atomically record a phase attempt")
    transition.add_argument("--workspace", type=Path, required=True)
    transition.add_argument("--phase", required=True)
    transition.add_argument("--status", required=True)
    transition.add_argument("--input", action="append", default=[])
    transition.add_argument("--output", action="append", default=[])
    transition.add_argument("--facts")
    transition.add_argument("--expected-revision", type=int)
    transition.set_defaults(func=command_run_transition)
    recover = run_sub.add_parser("recover", help="rebuild materialized state from the event ledger")
    recover.add_argument("--workspace", type=Path, required=True)
    recover.set_defaults(func=command_run_recover)
    invalidate = run_sub.add_parser(
        "invalidate", help="append a CAS-guarded artifact-drift invalidation"
    )
    invalidate.add_argument("--workspace", type=Path, required=True)
    invalidate.add_argument("--phase", required=True)
    invalidate.add_argument("--reason", required=True)
    invalidate.add_argument("--expected-revision", type=int, required=True)
    invalidate.set_defaults(func=command_run_invalidate)
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

    release = sub.add_parser("release", help="register and execute one immutable catalog plan")
    release_sub = release.add_subparsers(dest="release_command", required=True)
    release_register = release_sub.add_parser("register", help="seal the reviewed plan for execution")
    release_register.add_argument("--workspace", type=Path, required=True)
    release_register.add_argument("--plan", type=Path, required=True)
    release_register.set_defaults(func=command_release_register)
    release_begin = release_sub.add_parser("begin", help="create a distinct execution nonce")
    release_begin.add_argument("--workspace", type=Path, required=True)
    release_begin.add_argument("--kind", choices=("write-test", "production"), required=True)
    release_begin.add_argument("--adapter-plan", type=Path, required=True)
    release_begin.set_defaults(func=command_release_begin)
    release_complete = release_sub.add_parser("complete", help="bind a receipt to its execution")
    release_complete.add_argument("--workspace", type=Path, required=True)
    release_complete.add_argument("--execution-nonce", required=True)
    release_complete.add_argument("--receipt", type=Path, required=True)
    release_complete.set_defaults(func=command_release_complete)
    release_idempotence = release_sub.add_parser(
        "idempotence", help="require two distinct completed production attempts"
    )
    release_idempotence.add_argument("--workspace", type=Path, required=True)
    release_idempotence.set_defaults(func=command_release_idempotence)

    evals_check = sub.add_parser("evals-check", help="audit eval coverage and decision contracts")
    evals_check.add_argument("--evals", type=Path, required=True)
    evals_check.add_argument("--contract", type=Path, required=True)
    evals_check.set_defaults(func=command_evals_check)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
