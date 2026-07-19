from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from .handoff import render_handoff
from .integrity import base_identifier, membership_sha256
from .pipeline import (
    build_catalog_plan,
    evaluate,
    evaluation_identity_errors,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    write_csv,
)
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .review import render_review_workspace
from .runstate import checkpoint, initialize_run, next_phase, load_state


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


def read_id_column(path: Path, column: str) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if column not in (reader.fieldnames or []):
            raise ValueError(f"missing identifier column {column}: {path}")
        values = [row[column] for row in reader if row.get(column)]
    if not values:
        raise ValueError(f"no identifiers found in {path}")
    return values


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
    source_members = read_id_column(args.source_members, args.source_id_column)
    plan = build_catalog_plan(
        master,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        source_members,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_apply_feedback(args: argparse.Namespace) -> int:
    inventory = read_csv(args.inventory)
    feedback_rows = read_csv(args.feedback)
    integrity_errors, _ = evaluation_identity_errors(
        feedback_rows,
        {"require_evaluation_binding": True},
    )
    inventory_ids = [base_identifier(row["uuid"]) for row in inventory]
    if len(inventory_ids) != len(set(inventory_ids)):
        integrity_errors.append("inventory contains duplicate canonical UUIDs")
    feedback_ids = [base_identifier(row["uuid"]) for row in feedback_rows]
    unknown = sorted(set(feedback_ids) - set(inventory_ids))
    if unknown:
        integrity_errors.append(f"feedback contains {len(unknown)} UUIDs outside the inventory")
    if integrity_errors:
        raise ValueError("; ".join(integrity_errors))
    feedback = dict(zip(feedback_ids, feedback_rows, strict=True))
    excluded = 0
    held = 0
    for row in inventory:
        item = feedback.get(base_identifier(row["uuid"]))
        if not item:
            row.setdefault("evaluation_exclusion", "false")
            continue
        row["evaluation_round"] = item.get("round_id", "")
        row["evaluation_reason"] = item.get("visible_reason", "")
        rejected = item.get("judgment", "").strip().lower() == "reject"
        row["evaluation_exclusion"] = str(rejected).lower()
        if rejected:
            excluded += 1
        safety_status = item.get("safety_status", "").strip().lower()
        if safety_status in {"hold", "human-confirmed-hold"}:
            row["safety_status"] = "human-confirmed-hold"
            row["safety_reason"] = "human-sensitive visual review; private review required"
            held += 1
        elif safety_status in {"machine-suspected", "needs-review"}:
            row["safety_status"] = "machine-suspected"
            row["safety_reason"] = "local automated review; human confirmation required"
            held += 1
    write_csv(args.output, inventory)
    print(f"evaluation_exclusions={excluded}")
    print(f"safety_holds={held}")
    return 0


def command_compare(args: argparse.Namespace) -> int:
    before = read_csv(args.before)
    after = read_csv(args.after)
    before_by_id = {base_identifier(row["uuid"]): row for row in before}
    after_by_id = {base_identifier(row["uuid"]): row for row in after}
    retained = set(before_by_id) & set(after_by_id)
    report = {
        "before_count": len(before_by_id),
        "after_count": len(after_by_id),
        "added_count": len(set(after_by_id) - set(before_by_id)),
        "removed_count": len(set(before_by_id) - set(after_by_id)),
        "retained_count": len(retained),
        "retained_fraction": round(len(retained) / len(after_by_id), 4) if after_by_id else 0,
        "reclassified_count": sum(
            before_by_id[identifier].get("primary_view") != after_by_id[identifier].get("primary_view")
            for identifier in retained
        ),
        "before_membership_sha256": membership_sha256(before_by_id),
        "after_membership_sha256": membership_sha256(after_by_id),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def command_digest(args: argparse.Namespace) -> int:
    identifiers = read_id_column(args.input, args.id_column)
    print(json.dumps({"count": len(set(identifiers)), "membership_sha256": membership_sha256(identifiers)}, indent=2))
    return 0


def command_run(args: argparse.Namespace) -> int:
    state, created = initialize_run(args.workspace, args.brief, args.profile, args.version, args.target)
    print(json.dumps({
        "workspace": str(args.workspace.resolve()),
        "created": created,
        "status": state["status"],
        "next_phase": next_phase(state),
    }, indent=2))
    return 0


def command_checkpoint(args: argparse.Namespace) -> int:
    state, changed = checkpoint(args.workspace, args.phase, args.artifact)
    print(json.dumps({"changed": changed, "status": state["status"], "next_phase": next_phase(state)}, indent=2))
    return 0


def command_status(args: argparse.Namespace) -> int:
    state = load_state(args.workspace)
    summary = {
        "run_id": state["run_id"],
        "status": state["status"],
        "next_phase": next_phase(state),
        "phase_counts": dict(sorted(Counter(item["status"] for item in state["phases"].values()).items())),
    }
    print(json.dumps(summary, indent=2))
    return 0


def command_evidence_handoff(args: argparse.Namespace) -> int:
    data = json.loads(args.input.read_text(encoding="utf-8"))
    output = render_handoff(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"wrote public-safe evidence handoff to {args.output}")
    return 0


def command_review_pack(args: argparse.Namespace) -> int:
    rows = read_csv(args.sample)
    html = render_review_workspace(rows, args.previews, args.round_id, args.reviewer_lens)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"wrote offline review workspace to {args.output}")
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
            source_members=inventory,
            source_id_column="uuid",
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
    plan.add_argument("--source-members", type=Path, required=True)
    plan.add_argument("--source-id-column", default="uuid")
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    feedback = sub.add_parser("apply-feedback", help="apply visual rejects and safety holds to an inventory")
    feedback.add_argument("--inventory", type=Path, required=True)
    feedback.add_argument("--feedback", type=Path, required=True)
    feedback.add_argument("--output", type=Path, required=True)
    feedback.set_defaults(func=command_apply_feedback)

    compare = sub.add_parser("compare", help="compare two versioned master manifests")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.set_defaults(func=command_compare)

    digest = sub.add_parser("digest", help="compute a stable membership digest for a CSV")
    digest.add_argument("--input", type=Path, required=True)
    digest.add_argument("--id-column", default="uuid")
    digest.set_defaults(func=command_digest)

    run = sub.add_parser("run", help="initialize or resume a private versioned run")
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--brief", type=Path, required=True)
    run.add_argument("--profile", type=Path, required=True)
    run.add_argument("--version", required=True)
    run.add_argument("--target", type=int, required=True)
    run.set_defaults(func=command_run)

    checkpoint_parser = sub.add_parser("checkpoint", help="complete one run phase with artifact digests")
    checkpoint_parser.add_argument("--workspace", type=Path, required=True)
    checkpoint_parser.add_argument("--phase", required=True)
    checkpoint_parser.add_argument("--artifact", type=Path, action="append", default=[])
    checkpoint_parser.set_defaults(func=command_checkpoint)

    status = sub.add_parser("status", help="show resumable run status")
    status.add_argument("--workspace", type=Path, required=True)
    status.set_defaults(func=command_status)

    handoff = sub.add_parser("evidence-handoff", help="render a public-safe visual corroboration handoff")
    handoff.add_argument("--input", type=Path, required=True)
    handoff.add_argument("--output", type=Path, required=True)
    handoff.set_defaults(func=command_evidence_handoff)

    review = sub.add_parser("review-pack", help="build a static, offline visual review workspace")
    review.add_argument("--sample", type=Path, required=True)
    review.add_argument("--previews", type=Path, required=True)
    review.add_argument("--round-id", required=True)
    review.add_argument("--reviewer-lens", required=True)
    review.add_argument("--output", type=Path, required=True)
    review.set_defaults(func=command_review_pack)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
