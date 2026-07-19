#!/usr/bin/env python3
"""Run public-safe executable contracts against a Photo Fieldwork checkout."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path


def load_script(path: Path, name: str):
    if not path.exists():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config(quotas: dict[str, int]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "seed": 7,
        "target_count": sum(quotas.values()),
        "unclassified_view": next(iter(quotas)),
        "minimum_named_people_fraction": 0,
        "minimum_person_free_fraction": 0,
        "views": [
            {"id": view, "label": view, "quota": quota, "evaluation_mode": "material"}
            for view, quota in quotas.items()
        ],
    }


def row(identifier: str, view: str, **extra: str) -> dict[str, str]:
    return {
        "uuid": identifier,
        "filename": f"{identifier}.jpg",
        "assigned_view": view,
        "assignment_status": "assigned",
        "assignment_reason": "synthetic visible evidence",
        "assignment_version": "eval-v1",
        "evidence_confidence": "high",
        "safety_status": "clear",
        **extra,
    }


def run(repository: Path) -> dict[str, object]:
    sys.path.insert(0, str(repository / "src"))
    from photo_fieldwork import contracts, pipeline

    bridge = load_script(
        repository / "skills/curate-apple-photos/scripts/photo_archive_bridge.py",
        "composite_eval_bridge",
    )
    results: list[dict[str, object]] = []

    def evaluate_case(name: str, check) -> None:
        try:
            check()
            results.append({"name": name, "passed": True, "failure": None})
        except Exception as error:  # Every failed oracle becomes report evidence.
            results.append(
                {"name": name, "passed": False, "failure": f"{type(error).__name__}: {error}"}
            )

    def exact_quota_scarcity() -> None:
        expected = getattr(pipeline, "SelectionInfeasible", None)
        if expected is None:
            raise AssertionError("structured selection scarcity is unavailable")
        try:
            pipeline.select(
                [row("A", "one"), row("B", "one"), row("C", "one")],
                config({"one": 1, "two": 1}),
            )
        except expected as error:
            if error.deficits.get("two", {}).get("deficit") == 1:
                return
        raise AssertionError("exact view scarcity did not expose the expected deficit")

    def relational_hold() -> None:
        if not hasattr(pipeline, "relational_hold_origins"):
            raise AssertionError("relational HOLD closure is unavailable")
        master, holds, _ = pipeline.select(
            [
                row("HOLD", "one", safety_status="hold-human", duplicate_group="dup"),
                row("BRIDGE", "one", duplicate_group="dup", burst_group="burst"),
                row("RELATED", "one", burst_group="burst"),
                row("SAFE", "one"),
            ],
            config({"one": 1}),
        )
        if [item["uuid"] for item in master] != ["SAFE"]:
            raise AssertionError("a related HOLD member remained master-eligible")
        if {item["uuid"] for item in holds} != {"HOLD", "BRIDGE", "RELATED"}:
            raise AssertionError("HOLD did not propagate through the connected component")

    def quota_drift_validation() -> None:
        cfg = config({"one": 2, "two": 2})
        master = [row("A", "one"), row("B", "one"), row("C", "one"), row("D", "two")]
        digest = pipeline.master_sha256(master)
        for item in master:
            item["primary_view"] = item["assigned_view"]
            item["selection_reason"] = "synthetic"
            item["master_sha256"] = digest
            item["proposal_id"] = f"pfp-{digest[:16]}"
        errors, _ = pipeline.validate(master, [], cfg)
        if not any("exact quotas" in error for error in errors):
            raise AssertionError("count-preserving quota drift passed validation")

    def split_case(kind: str) -> None:
        audit = load_script(
            repository / "skills/curate-apple-photos/scripts/audit_eval_split.py",
            f"composite_split_{kind}",
        )
        if kind == "uuid":
            report = audit.audit_split([{"uuid": "A"}], [{"uuid": "A/L0/001"}], [])
            field = "tuning_uuid_overlap_count"
        else:
            report = audit.audit_split(
                [{"uuid": "A", "perceptual_cluster_id": "scene"}],
                [{"uuid": "B", "perceptual_cluster_id": "scene"}],
                [],
            )
            field = "tuning_cluster_overlap_count"
        if report["status"] != "FAIL" or report["leakage"][field] != 1:
            raise AssertionError(f"holdout {kind} leakage passed")
        if "private_details" in report:
            raise AssertionError("default split report exposed private identifiers")

    def stale_run_revision() -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            state = {
                "schema_version": 2,
                "run_id": "synthetic-run",
                "status": "active",
                "phases": {phase: "pending" for phase in bridge.RUN_PHASES},
                "phase_records": {},
                "revision": 1,
                "last_event_sha256": None,
            }
            (workspace / "run-state.json").write_text(json.dumps(state), encoding="utf-8")
            try:
                bridge.update_run_state(
                    workspace, "brief", "completed", expected_revision=0, actor="eval"
                )
            except ValueError as error:
                if "stale run-state revision" in str(error):
                    return
            raise AssertionError("a stale operator overwrote current run state")

    def artifact_substitution(field: str, digest_field: str) -> None:
        source = contracts.build_source_manifest(
            source_adapter="synthetic",
            source_identifier="synthetic://source",
            source_title="Synthetic",
            predicate_version="all-v1",
            observed_count=1,
            membership_sha256="a" * 64,
            artifact_sensitivity="public-safe",
        )
        evaluation = {
            "passed": True,
            "proposal_id": "pfp-" + "b" * 16,
            "master_sha256": "b" * 64,
            "config_sha256": "c" * 64,
        }
        validation = {
            "status": "PASS",
            "proposal_id": evaluation["proposal_id"],
            "master_sha256": evaluation["master_sha256"],
            "config_sha256": evaluation["config_sha256"],
        }
        plan = contracts.finalize_plan(
            {
                "schema_version": 2,
                "operation": "snapshot-membership",
                "source": source,
                "source_fingerprint": source["source_fingerprint"],
                "proposal_id": evaluation["proposal_id"],
                "master_sha256": evaluation["master_sha256"],
                "config_sha256": evaluation["config_sha256"],
                "evaluation": evaluation,
                "evaluation_report_sha256": contracts.canonical_sha256(evaluation),
                "validation": validation,
                "validation_report_sha256": contracts.canonical_sha256(validation),
            }
        )
        altered = deepcopy(plan)
        altered[field]["synthetic_substitution"] = True
        altered["plan_sha256"] = contracts.plan_sha256(altered)
        try:
            contracts.validate_plan(altered)
        except ValueError as error:
            if digest_field in str(error):
                return
        raise AssertionError(f"rehashed {field} substitution passed plan validation")

    def relational_hold_causes_quota_scarcity() -> None:
        expected = getattr(pipeline, "SelectionInfeasible", None)
        closure = getattr(pipeline, "relational_hold_origins", None)
        if expected is None or closure is None:
            raise AssertionError("composed safety and scarcity contracts are unavailable")
        inventory = [
            row("HOLD", "one", safety_status="hold-human", duplicate_group="dup"),
            row("BRIDGE", "one", duplicate_group="dup", burst_group="burst"),
            row("RELATED", "one", burst_group="burst"),
            row("SAFE", "one"),
        ]
        if set(closure(inventory, config({"one": 2}))) != {"HOLD", "BRIDGE", "RELATED"}:
            raise AssertionError("compound relation closure is incomplete")
        try:
            pipeline.select(inventory, config({"one": 2}))
        except expected as error:
            if error.deficits.get("one", {}).get("deficit") == 1:
                return
        raise AssertionError("relational safety did not expose downstream quota scarcity")

    def mixed_split_leakage() -> None:
        audit = load_script(
            repository / "skills/curate-apple-photos/scripts/audit_eval_split.py",
            "composite_split_mixed",
        )
        report = audit.audit_split(
            [{"uuid": "A", "perceptual_cluster_id": "scene"}],
            [
                {"uuid": "A/L0/001", "perceptual_cluster_id": "other"},
                {"uuid": "B", "perceptual_cluster_id": "scene"},
            ],
            [],
        )
        leakage = report["leakage"]
        if leakage["tuning_uuid_overlap_count"] != 1 or leakage["tuning_cluster_overlap_count"] != 1:
            raise AssertionError("compound holdout leakage was partially accepted")
        if report["status"] != "FAIL" or "private_details" in report:
            raise AssertionError("compound split report violated its public-safe failure contract")

    def double_artifact_substitution() -> None:
        source = contracts.build_source_manifest(
            source_adapter="synthetic",
            source_identifier="synthetic://source",
            source_title="Synthetic",
            predicate_version="all-v1",
            observed_count=1,
            membership_sha256="a" * 64,
            artifact_sensitivity="public-safe",
        )
        evaluation = {
            "passed": True,
            "proposal_id": "pfp-" + "b" * 16,
            "master_sha256": "b" * 64,
            "config_sha256": "c" * 64,
        }
        validation = {
            "status": "PASS",
            "proposal_id": evaluation["proposal_id"],
            "master_sha256": evaluation["master_sha256"],
            "config_sha256": evaluation["config_sha256"],
        }
        plan = contracts.finalize_plan(
            {
                "schema_version": 2,
                "operation": "snapshot-membership",
                "source": source,
                "source_fingerprint": source["source_fingerprint"],
                "proposal_id": evaluation["proposal_id"],
                "master_sha256": evaluation["master_sha256"],
                "config_sha256": evaluation["config_sha256"],
                "evaluation": evaluation,
                "evaluation_report_sha256": contracts.canonical_sha256(evaluation),
                "validation": validation,
                "validation_report_sha256": contracts.canonical_sha256(validation),
            }
        )
        altered = deepcopy(plan)
        altered["evaluation"]["replacement"] = "passing-evaluation"
        altered["validation"]["replacement"] = "passing-validation"
        altered["plan_sha256"] = contracts.plan_sha256(altered)
        try:
            contracts.validate_plan(altered)
        except ValueError as error:
            if "report_sha256" in str(error):
                return
        raise AssertionError("double upstream substitution passed after outer rehash")

    def recover_event_ahead_of_state() -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            initial = {
                "schema_version": 2,
                "run_id": "synthetic-run",
                "status": "active",
                "phases": {phase: "pending" for phase in bridge.RUN_PHASES},
                "phase_records": {},
                "revision": 0,
                "last_event_sha256": None,
            }
            state_path = workspace / "run-state.json"
            state_path.write_text(json.dumps(initial), encoding="utf-8")
            bridge.update_run_state(workspace, "brief", "completed", expected_revision=0)
            revision_one = state_path.read_text(encoding="utf-8")
            bridge.update_run_state(workspace, "retrieval", "completed", expected_revision=1)
            if not (workspace / "run-events.jsonl").exists():
                raise AssertionError("append-only event ledger is unavailable")
            state_path.write_text(revision_one, encoding="utf-8")
            bridge.update_run_state(
                workspace, "local_inspection", "completed", expected_revision=2
            )
            recovered = json.loads(state_path.read_text(encoding="utf-8"))
            if recovered["revision"] != 3 or recovered["phases"]["retrieval"] != "completed":
                raise AssertionError("event-ahead recovery lost the interrupted transition")
            events = [
                json.loads(line)
                for line in (workspace / "run-events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            if events[2]["previous_event_sha256"] != events[1]["event_sha256"]:
                raise AssertionError("recovered transition broke the append-only hash chain")

    evaluate_case("exact-view-quota-scarcity", exact_quota_scarcity)
    evaluate_case("transitive-relational-hold", relational_hold)
    evaluate_case("count-preserving-quota-drift", quota_drift_validation)
    evaluate_case("holdout-canonical-uuid-leakage", lambda: split_case("uuid"))
    evaluate_case("holdout-relation-leakage", lambda: split_case("cluster"))
    evaluate_case("stale-run-state-revision", stale_run_revision)
    evaluate_case(
        "rehashed-evaluation-substitution",
        lambda: artifact_substitution("evaluation", "evaluation_report_sha256"),
    )
    evaluate_case(
        "rehashed-validation-substitution",
        lambda: artifact_substitution("validation", "validation_report_sha256"),
    )
    evaluate_case("compound-relational-hold-and-quota-scarcity", relational_hold_causes_quota_scarcity)
    evaluate_case("compound-holdout-leakage", mixed_split_leakage)
    evaluate_case("compound-artifact-substitution", double_artifact_substitution)
    evaluate_case("event-ahead-state-recovery", recover_event_ahead_of_state)
    passed = sum(bool(item["passed"]) for item in results)
    return {
        "schema_version": 1,
        "repository_revision": repository.name,
        "summary": {
            "passed": passed,
            "failed": len(results) - passed,
            "total": len(results),
            "pass_rate": passed / len(results),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.repository.resolve())
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
