from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from .pipeline import (
    build_catalog_plan,
    ensure_private_directory,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    write_csv,
    write_private_text,
)
from .practice import create_demo_inventory, practice_feedback, write_demo_readme
from .publication import PUBLIC_FIELDS, build_public_handoff, scaffold_clearance
from .review import build_review_workbench


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
    ensure_private_directory(reports)
    write_private_text(reports / "selection-summary.json", json.dumps(summary, indent=2) + "\n")
    write_private_text(reports / "selection-summary.md", markdown_report("Selection summary", summary))
    print(f"selected {len(master)}; held {len(holds)}; wrote {output}")
    return 0


def command_sample(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    config = read_config(args.config)
    sample = make_sample(
        master,
        int(config["evaluation_sample_per_view"]),
        int(config["seed"]),
        args.round_id,
    )
    write_csv(args.output, sample)
    print(f"wrote {len(sample)} evaluation rows to {args.output}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    feedback = read_csv(args.feedback)
    master = read_csv(args.master)
    report, passed = evaluate(feedback, config, master)
    ensure_private_directory(args.output)
    write_private_text(args.output / "evaluation-report.json", json.dumps(report, indent=2) + "\n")
    write_private_text(args.output / "evaluation-report.md", markdown_report("Evaluation report", report))
    print(f"evaluation {'PASS' if passed else 'FAIL'}: precision={report['precision']}, coverage={report['coverage']}")
    return 0 if passed else 2


def command_validate(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    errors, metrics = validate(master, holds, config)
    ensure_private_directory(args.output)
    report = dict(metrics)
    report["errors"] = errors
    write_private_text(args.output / "validation-report.json", json.dumps(report, indent=2) + "\n")
    write_private_text(args.output / "validation-report.md", markdown_report("Validation report", report))
    print(f"validation {metrics['status']}")
    return 0 if not errors else 2


def command_plan(args: argparse.Namespace) -> int:
    config = read_config(args.config)
    master = read_csv(args.master)
    holds = read_csv(args.holds)
    feedback = read_csv(args.feedback)
    evaluation_report = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    validation_report = json.loads(args.validation_report.read_text(encoding="utf-8"))
    plan = build_catalog_plan(
        master,
        holds,
        config,
        args.plan_id,
        args.source_title,
        args.source_identifier,
        args.source_count,
        args.source_sha256,
        evaluation_report,
        feedback,
        validation_report,
    )
    write_private_text(args.output, json.dumps(plan, indent=2) + "\n")
    print(f"wrote membership-only catalog plan to {args.output}")
    return 0


def command_review(args: argparse.Namespace) -> int:
    sample = read_csv(args.sample)
    with args.preview_index.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        preview_index = list(reader)
    required = {"uuid", "preview_path", "preview_sha256", "decode_status"}
    missing = required - set(reader.fieldnames or [])
    if not preview_index:
        raise ValueError("verified preview index contains no rows")
    if missing:
        raise ValueError(f"verified preview index missing columns: {', '.join(sorted(missing))}")
    review_id = build_review_workbench(
        sample,
        preview_index,
        args.preview_root,
        args.output,
    )
    print(f"wrote private offline review {review_id} to {args.output}")
    return 0


def command_publication_scaffold(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    rows = scaffold_clearance(master)
    write_csv(args.output, rows)
    print(f"wrote {len(rows)} default-closed clearance rows to {args.output}")
    return 0


def read_private_salt(path: Path) -> str:
    if path.is_symlink():
        raise ValueError("public ID salt file must not be a symlink")
    resolved = path.resolve(strict=True)
    if resolved.stat().st_mode & 0o077:
        raise ValueError("public ID salt file permissions are broader than 0600")
    salt = resolved.read_text(encoding="utf-8").strip()
    if len(salt) < 16:
        raise ValueError("public ID salt must contain at least 16 characters")
    return salt


def command_publication_project(args: argparse.Namespace) -> int:
    master = read_csv(args.master)
    clearance = read_csv(args.clearance)
    rows, errors = build_public_handoff(
        master,
        clearance,
        read_private_salt(args.salt_file),
        args.destination,
    )
    if errors:
        raise ValueError("publication projection blocked:\n" + "\n".join(errors))
    write_csv(args.output, rows, fieldnames=list(PUBLIC_FIELDS))
    print(f"wrote {len(rows)} specifically cleared public rows to {args.output}")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    workspace = args.workspace.resolve()
    inventory = workspace / "inventory" / "practice.csv"
    config = workspace / "config.json"
    create_demo_inventory(inventory)
    ensure_private_directory(config.parent)
    shutil.copy2(root / "config" / "starter.json", config)
    config.chmod(0o600)
    write_demo_readme(workspace / "README.md")
    command_select(argparse.Namespace(config=config, inventory=inventory, output=workspace))
    sample_path = workspace / "manifests" / "eval-sample.csv"
    command_sample(
        argparse.Namespace(
            master=workspace / "manifests" / "proposed-master.csv",
            config=config,
            output=sample_path,
            round_id="practice-round-01",
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
            holds=workspace / "manifests" / "hold-sensitive.csv",
            feedback=sample_path,
            plan_id="synthetic-practice-plan",
            source_title="Synthetic practice corpus",
            source_identifier="SYNTHETIC-ONLY",
            source_count=30,
            source_sha256="50ce7a9ce8269931cee4ed617a22fd1214f27fcde9aada68e23ae8a4b373af74",
            evaluation_report=workspace / "reports" / "evaluation-report.json",
            validation_report=workspace / "reports" / "validation-report.json",
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
    sample.add_argument("--config", type=Path, required=True)
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--round-id", default="round-01")
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
    plan.add_argument("--holds", type=Path, required=True)
    plan.add_argument("--feedback", type=Path, required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--plan-id", required=True)
    plan.add_argument("--source-title", required=True)
    plan.add_argument("--source-identifier", required=True)
    plan.add_argument("--source-count", type=int, required=True)
    plan.add_argument("--source-sha256", required=True)
    plan.add_argument("--evaluation-report", type=Path, required=True)
    plan.add_argument("--validation-report", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(func=command_plan)

    review = sub.add_parser("review", help="build a private offline review field from verified previews")
    review.add_argument("--sample", type=Path, required=True)
    review.add_argument("--preview-index", type=Path, required=True)
    review.add_argument("--preview-root", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    review.set_defaults(func=command_review)

    publication_scaffold = sub.add_parser(
        "publication-scaffold",
        help="make a default-closed private publication-clearance ledger",
    )
    publication_scaffold.add_argument("--master", type=Path, required=True)
    publication_scaffold.add_argument("--output", type=Path, required=True)
    publication_scaffold.set_defaults(func=command_publication_scaffold)

    publication_project = sub.add_parser(
        "publication-project",
        help="project specifically cleared rows through a public allowlist",
    )
    publication_project.add_argument("--master", type=Path, required=True)
    publication_project.add_argument("--clearance", type=Path, required=True)
    publication_project.add_argument("--salt-file", type=Path, required=True)
    publication_project.add_argument("--destination", required=True)
    publication_project.add_argument("--output", type=Path, required=True)
    publication_project.set_defaults(func=command_publication_project)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
