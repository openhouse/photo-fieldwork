import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.integrity import content_sha256, master_sha256, membership_sha256
from photo_fieldwork.release import (
    begin_execution,
    complete_execution,
    idempotence_report,
    register_plan,
)
from photo_fieldwork.run_state import initialize
from photo_fieldwork.run_state import (
    freeze_lock,
    read_state,
    record_invalidation,
    record_transition,
    sha256_file,
)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "run"
        self.source_digest = membership_sha256(["A", "B"])
        state = initialize(
            self.workspace,
            "v-test",
            1,
            "source://test",
            2,
            self.source_digest,
        )
        evidence = self.workspace / "manifests" / "phase-evidence.txt"
        evidence.write_text("verified", encoding="utf-8")
        for phase in (
            "brief",
            "source",
            "retrieval",
            "inspection",
        ):
            state = record_transition(
                self.workspace,
                phase,
                "complete",
                outputs={"evidence": evidence},
                expected_revision=state["revision"],
            )
        effective_config = self.workspace / "final" / "effective-final-config.json"
        master = self.workspace / "manifests" / "proposed-master.csv"
        holds = self.workspace / "manifests" / "hold-sensitive.csv"
        replay = self.workspace / "reports" / "final-replay-validation.json"
        self.effective_config_path = effective_config
        self.master_path = master
        self.holds_path = holds
        self.replay_path = replay
        config = {
            "seed": 1,
            "target_count": 1,
            "unclassified_view": "01",
            "views": [{"id": "01", "label": "One", "quota": 1}],
        }
        effective_config.write_text(json.dumps(config), encoding="utf-8")
        master.write_text(
            "uuid,filename,primary_view,safety_status,evidence_confidence,persons\n"
            "A,a.jpg,01,clear,high,\n",
            encoding="utf-8",
        )
        holds.write_text("uuid\n", encoding="utf-8")
        replay.write_text("{}", encoding="utf-8")
        state = record_transition(
            self.workspace,
            "final_freeze",
            "complete",
            outputs={
                "effective_config": effective_config,
                "master": master,
                "holds": holds,
                "replay_validation": replay,
            },
            expected_revision=state["revision"],
        )
        freeze_lock(
            self.workspace,
            effective_config,
            master,
            holds,
            {"replay_validation": replay},
        )
        self.plan_path = self.workspace / "manifests" / "catalog-plan.json"
        master_digest = master_sha256(
            [{"uuid": "A", "primary_view": "01", "safety_status": "clear"}]
        )
        proposal_id = f"pfp-{master_digest[:16]}"
        config_digest = content_sha256(config)
        self.leakage = {
            "status": "PASS",
            "collisions": [],
        }
        self.evaluation = {
            "passed": True,
            "final_holdout": True,
            "relation_clean_holdout": True,
            "master_sha256": master_digest,
            "proposal_id": proposal_id,
            "config_sha256": config_digest,
            "leakage_report_sha256": content_sha256(self.leakage),
        }
        self.validation = {
            "status": "PASS",
            "master_sha256": master_digest,
            "proposal_id": proposal_id,
            "config_sha256": config_digest,
        }
        self.evaluation_path = self.workspace / "reports" / "evaluation.json"
        self.leakage_path = self.workspace / "reports" / "leakage.json"
        self.validation_path = self.workspace / "reports" / "validation.json"
        self.evaluation_path.write_text(json.dumps(self.evaluation), encoding="utf-8")
        self.leakage_path.write_text(json.dumps(self.leakage), encoding="utf-8")
        self.validation_path.write_text(json.dumps(self.validation), encoding="utf-8")
        state = record_transition(
            self.workspace,
            "evaluation",
            "complete",
            outputs={"report": self.evaluation_path, "leakage": self.leakage_path},
            expected_revision=state["revision"],
        )
        state = record_transition(
            self.workspace,
            "validation",
            "complete",
            outputs={"report": self.validation_path},
            expected_revision=state["revision"],
        )
        self.plan = {
            "schema_version": 2,
            "plan_id": "plan-test",
            "proposal_id": proposal_id,
            "master_sha256": master_digest,
            "config_sha256": config_digest,
            "run_lock_sha256": sha256_file(self.workspace / "run-lock.json"),
            "release_class": "editor-field",
            "safety_mode": "create-folders-albums-and-add-membership-only",
            "source": {
                "identifier": "source://test",
                "count": 2,
                "membership_sha256": self.source_digest,
            },
            "evaluation": {
                "passed": True,
                "final_holdout": True,
                "relation_clean_holdout": True,
                "report_sha256": content_sha256(self.evaluation),
                "leakage_report_sha256": content_sha256(self.leakage),
            },
            "validation": {
                "status": "PASS",
                "report_sha256": content_sha256(self.validation),
            },
            "expected_master_count": 1,
            "write_test_count": 1,
            "albums": [
                {"key": "master", "asset_ids": ["A"]},
                {"key": "view-01", "asset_ids": ["A"]},
            ],
        }
        self.plan["plan_sha256"] = content_sha256(self.plan, "plan_sha256")
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.write_test_plan_path = self.adapter_plan("write-test")
        self.production_plan_path = self.adapter_plan("production")

    def tearDown(self):
        self.temp.cleanup()

    def adapter_plan(self, kind: str) -> Path:
        path = self.workspace / "manifests" / f"{kind}-adapter.json"
        titles = (
            ["WRITE TEST"]
            if kind == "write-test"
            else ["MASTER", "VIEW 01", "WRITE TEST"]
        )
        roles = (
            ["aux:write-test"]
            if kind == "write-test"
            else ["catalog:master", "catalog:view-01", "aux:write-test"]
        )
        albums = [
            {"title": title, "role": role, "asset_identifiers": ["A"]}
            for title, role in zip(titles, roles)
        ]
        path.write_text(
            json.dumps(
                {
                    "operation": "snapshot-membership",
                    "plan_id": f"adapter-{kind}",
                    "execution_kind": kind,
                    "catalog_plan_sha256": self.plan["plan_sha256"],
                    "safety_mode": "create-folders-albums-and-add-membership-only",
                    "source_album_identifier": self.plan["source"]["identifier"],
                    "expected_source_count": self.plan["source"]["count"],
                    "source_membership_sha256": self.plan["source"]["membership_sha256"],
                    "folders": [],
                    "albums": albums,
                }
            ),
            encoding="utf-8",
        )
        return path

    def receipt(self, name: str, execution: dict) -> Path:
        path = self.workspace / "logs" / name
        adapter_path = (
            self.write_test_plan_path
            if execution["kind"] == "write-test"
            else self.production_plan_path
        )
        adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
        path.write_text(
            json.dumps(
                {
                    "status": "completed",
                    "plan_id": adapter["plan_id"],
                    "execution_kind": execution["kind"],
                    "execution_nonce": execution["execution_nonce"],
                    "plan_sha256": self.plan["plan_sha256"],
                    "adapter_plan_sha256": execution["adapter_plan_sha256"],
                    "runtime_plan_sha256": "e" * 64,
                    "source_album_identifier": self.plan["source"]["identifier"],
                    "source_count": self.plan["source"]["count"],
                    "source_membership_sha256": self.plan["source"]["membership_sha256"],
                    "safety_mode": "create-folders-albums-and-add-membership-only",
                    "independent_verification_required": True,
                    "folders": [],
                    "albums": [
                        {
                            "title": album["title"],
                            "identifier": f"album-{name}-{index}",
                            "count": len(album["asset_identifiers"]),
                        }
                        for index, album in enumerate(adapter["albums"])
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def complete_write_test_gate(self) -> None:
        execution = begin_execution(
            self.workspace,
            "write-test",
            self.write_test_plan_path,
        )
        receipt = self.receipt("write-test-receipt.json", execution)
        complete_execution(self.workspace, execution["execution_nonce"], receipt)
        verification = self.workspace / "reports" / "write-test-verification.json"
        verification.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "execution_kind": "write-test",
                    "execution_nonce": execution["execution_nonce"],
                    "plan_sha256": self.plan["plan_sha256"],
                    "adapter_plan_sha256": execution["adapter_plan_sha256"],
                    "runtime_plan_sha256": "e" * 64,
                    "source_membership_sha256": self.plan["source"][
                        "membership_sha256"
                    ],
                    "receipt_sha256": sha256_file(receipt),
                    "verified_album_count": 1,
                    "missing_membership_count": 0,
                    "unexpected_membership_count": 0,
                    "outside_source_count": 0,
                    "independent_read_only": True,
                }
            ),
            encoding="utf-8",
        )
        state = read_state(self.workspace)
        record_transition(
            self.workspace,
            "write_test",
            "complete",
            outputs={"receipt": receipt, "verification": verification},
            expected_revision=state["revision"],
        )

    def test_registered_plan_rejects_post_registration_mutation(self):
        register_plan(self.workspace, self.plan_path)
        self.plan["albums"][0]["asset_ids"].append("B")
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after registration"):
            begin_execution(self.workspace, "production", self.production_plan_path)

    def test_registration_rejects_non_editor_plan(self):
        self.plan["release_class"] = "synthetic-practice"
        self.plan["plan_sha256"] = content_sha256(self.plan, "plan_sha256")
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "only editor-field"):
            register_plan(self.workspace, self.plan_path)

    def test_registration_rejects_another_run_lock(self):
        self.plan["run_lock_sha256"] = "0" * 64
        self.plan["plan_sha256"] = content_sha256(self.plan, "plan_sha256")
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "this workspace run lock"):
            register_plan(self.workspace, self.plan_path)

    def test_registration_rejects_rehashed_plan_with_forged_master(self):
        forged_digest = master_sha256(
            [{"uuid": "B", "primary_view": "01", "safety_status": "clear"}]
        )
        self.plan["master_sha256"] = forged_digest
        self.plan["proposal_id"] = f"pfp-{forged_digest[:16]}"
        for album in self.plan["albums"]:
            album["asset_ids"] = ["B"]
        self.plan["plan_sha256"] = content_sha256(self.plan, "plan_sha256")
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "locked candidate"):
            register_plan(self.workspace, self.plan_path)

    def test_registration_rejects_duplicate_catalog_album_keys(self):
        self.plan["albums"].insert(
            0,
            {"key": "master", "asset_ids": ["B"]},
        )
        self.plan["plan_sha256"] = content_sha256(self.plan, "plan_sha256")
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "album keys"):
            register_plan(self.workspace, self.plan_path)

    def test_invalidated_candidate_can_supersede_registered_plan(self):
        register_plan(self.workspace, self.plan_path)
        same_candidate = dict(self.plan, plan_id="renamed-plan")
        same_candidate["plan_sha256"] = content_sha256(
            same_candidate, "plan_sha256"
        )
        self.plan_path.write_text(json.dumps(same_candidate), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalidation and refreeze"):
            register_plan(self.workspace, self.plan_path)

        new_config = {
            "seed": 1,
            "target_count": 1,
            "unclassified_view": "02",
            "views": [{"id": "02", "label": "Two", "quota": 1}],
        }
        self.master_path.write_text(
            "uuid,filename,primary_view,safety_status,evidence_confidence,persons\n"
            "A,a.jpg,02,clear,high,\n",
            encoding="utf-8",
        )
        self.effective_config_path.write_text(
            json.dumps(new_config), encoding="utf-8"
        )
        state = read_state(self.workspace)
        state = record_invalidation(
            self.workspace,
            "final_freeze",
            "editor changed the frozen assignment",
            expected_revision=state["revision"],
        )
        state = record_transition(
            self.workspace,
            "final_freeze",
            "complete",
            outputs={
                "effective_config": self.effective_config_path,
                "master": self.master_path,
                "holds": self.holds_path,
                "replay_validation": self.replay_path,
            },
            expected_revision=state["revision"],
        )
        freeze_lock(
            self.workspace,
            self.effective_config_path,
            self.master_path,
            self.holds_path,
            {"replay_validation": self.replay_path},
        )
        new_digest = master_sha256(
            [{"uuid": "A", "primary_view": "02", "safety_status": "clear"}]
        )
        new_proposal = f"pfp-{new_digest[:16]}"
        new_config_digest = content_sha256(new_config)
        self.evaluation.update(
            master_sha256=new_digest,
            proposal_id=new_proposal,
            config_sha256=new_config_digest,
        )
        self.validation.update(
            master_sha256=new_digest,
            proposal_id=new_proposal,
            config_sha256=new_config_digest,
        )
        self.evaluation_path.write_text(json.dumps(self.evaluation), encoding="utf-8")
        self.validation_path.write_text(json.dumps(self.validation), encoding="utf-8")
        state = record_transition(
            self.workspace,
            "evaluation",
            "complete",
            outputs={"report": self.evaluation_path, "leakage": self.leakage_path},
            expected_revision=state["revision"],
        )
        record_transition(
            self.workspace,
            "validation",
            "complete",
            outputs={"report": self.validation_path},
            expected_revision=state["revision"],
        )
        self.plan.update(
            plan_id="replacement-plan",
            proposal_id=new_proposal,
            master_sha256=new_digest,
            config_sha256=new_config_digest,
            run_lock_sha256=sha256_file(self.workspace / "run-lock.json"),
            evaluation={
                **self.plan["evaluation"],
                "report_sha256": content_sha256(self.evaluation),
            },
            validation={
                "status": "PASS",
                "report_sha256": content_sha256(self.validation),
            },
            albums=[
                {"key": "master", "asset_ids": ["A"]},
                {"key": "view-02", "asset_ids": ["A"]},
            ],
        )
        self.plan["plan_sha256"] = content_sha256(self.plan, "plan_sha256")
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        replacement = register_plan(self.workspace, self.plan_path)
        self.assertEqual(replacement["plan_id"], "replacement-plan")
        events = [
            json.loads(line)
            for line in (self.workspace / "execution-events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertTrue(any(event["event_type"] == "plan_superseded" for event in events))

    def test_execution_nonce_authorizes_one_adapter_kind(self):
        register_plan(self.workspace, self.plan_path)
        with self.assertRaisesRegex(ValueError, "execution kind"):
            begin_execution(self.workspace, "write-test", self.production_plan_path)

    def test_launch_rechecks_recorded_release_artifacts(self):
        register_plan(self.workspace, self.plan_path)
        self.validation_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact drift"):
            begin_execution(self.workspace, "production", self.production_plan_path)

    def test_production_rejects_unbound_auxiliary_membership(self):
        register_plan(self.workspace, self.plan_path)
        self.complete_write_test_gate()
        adapter = json.loads(self.production_plan_path.read_text(encoding="utf-8"))
        adapter["albums"].append(
            {"title": "UNBOUND", "role": "aux:unbound", "asset_identifiers": ["B"]}
        )
        self.production_plan_path.write_text(json.dumps(adapter), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "adapter roles"):
            begin_execution(self.workspace, "production", self.production_plan_path)

    def test_production_requires_exact_duplicate_membership_roles(self):
        register_plan(self.workspace, self.plan_path)
        self.complete_write_test_gate()
        adapter = json.loads(self.production_plan_path.read_text(encoding="utf-8"))
        adapter["albums"] = adapter["albums"][:1]
        self.production_plan_path.write_text(json.dumps(adapter), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "adapter roles"):
            begin_execution(self.workspace, "production", self.production_plan_path)

    def test_production_rejects_status_only_write_test_phase(self):
        register_plan(self.workspace, self.plan_path)
        evidence = self.workspace / "reports" / "status-only.txt"
        evidence.write_text("claimed complete", encoding="utf-8")
        state = read_state(self.workspace)
        record_transition(
            self.workspace,
            "write_test",
            "complete",
            outputs={"evidence": evidence},
            expected_revision=state["revision"],
        )
        with self.assertRaisesRegex(ValueError, "receipt and independent verification"):
            begin_execution(self.workspace, "production", self.production_plan_path)

    def test_idempotence_requires_distinct_completed_executions(self):
        register_plan(self.workspace, self.plan_path)
        self.complete_write_test_gate()
        first = begin_execution(self.workspace, "production", self.production_plan_path)
        complete_execution(
            self.workspace,
            first["execution_nonce"],
            self.receipt("receipt-1.json", first),
        )
        self.assertEqual(idempotence_report(self.workspace)["status"], "FAIL")
        second = begin_execution(self.workspace, "production", self.production_plan_path)
        self.assertNotEqual(first["execution_nonce"], second["execution_nonce"])
        second_receipt = self.receipt("receipt-2.json", second)
        complete_execution(
            self.workspace,
            second["execution_nonce"],
            second_receipt,
        )
        report = idempotence_report(self.workspace)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["independent_verification_required"])
        with self.assertRaisesRegex(ValueError, "already completed"):
            complete_execution(
                self.workspace,
                first["execution_nonce"],
                self.receipt("copied.json", first),
            )
        second_receipt.write_text("{}", encoding="utf-8")
        self.assertEqual(idempotence_report(self.workspace)["status"], "FAIL")

    def test_idempotence_requires_identical_adapter_plan_bytes(self):
        register_plan(self.workspace, self.plan_path)
        self.complete_write_test_gate()
        first = begin_execution(self.workspace, "production", self.production_plan_path)
        complete_execution(
            self.workspace,
            first["execution_nonce"],
            self.receipt("same-plan-1.json", first),
        )
        adapter = json.loads(self.production_plan_path.read_text(encoding="utf-8"))
        adapter["plan_id"] = "adapter-production-second-layout"
        adapter["albums"][0]["title"] = "MASTER SECOND LAYOUT"
        self.production_plan_path.write_text(json.dumps(adapter), encoding="utf-8")
        second = begin_execution(self.workspace, "production", self.production_plan_path)
        second_receipt = self.receipt("different-plan-2.json", second)
        payload = json.loads(second_receipt.read_text(encoding="utf-8"))
        payload["plan_id"] = adapter["plan_id"]
        payload["albums"][0]["title"] = adapter["albums"][0]["title"]
        second_receipt.write_text(json.dumps(payload), encoding="utf-8")
        complete_execution(self.workspace, second["execution_nonce"], second_receipt)
        report = idempotence_report(self.workspace)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["distinct_adapter_plans"], 2)

    def test_completion_rejects_source_identity_mismatch(self):
        register_plan(self.workspace, self.plan_path)
        self.complete_write_test_gate()
        execution = begin_execution(
            self.workspace, "production", self.production_plan_path
        )
        receipt = self.receipt("wrong-source.json", execution)
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["source_membership_sha256"] = "0" * 64
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source membership"):
            complete_execution(self.workspace, execution["execution_nonce"], receipt)

    def test_completion_requires_concrete_album_outcomes(self):
        register_plan(self.workspace, self.plan_path)
        self.complete_write_test_gate()
        execution = begin_execution(
            self.workspace, "production", self.production_plan_path
        )
        receipt = self.receipt("empty-outcomes.json", execution)
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["albums"] = []
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "album outcomes"):
            complete_execution(self.workspace, execution["execution_nonce"], receipt)


if __name__ == "__main__":
    unittest.main()
