import json
import tempfile
import unittest
from pathlib import Path

from photo_fieldwork.pipeline import (
    build_catalog_plan,
    evaluate,
    make_sample,
    read_config,
    read_csv,
    select,
    validate,
    write_csv,
)
from photo_fieldwork.practice import create_demo_inventory
from photo_fieldwork.publication import scaffold, validate as validate_publication
from photo_fieldwork.release import audit_release_seal, build_release_seal, write_release_seal


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        inventory_path = self.root / "inventory.csv"
        create_demo_inventory(inventory_path)
        config = read_config(ROOT / "config" / "starter.json")
        master, holds, _ = select(read_csv(inventory_path), config)
        sample = make_sample(master, len(master), 20260719)
        for row in sample:
            row.update({
                "judgment": "fit",
                "visible_reason": "synthetic visible fixture",
                "evaluation_safety_state": "clear",
                "error_category": "",
            })
        evaluation, passed = evaluate(sample, config, master=master)
        self.assertTrue(passed)
        errors, validation = validate(master, holds, config)
        self.assertEqual(errors, [])
        source = {
            "schema_version": 1,
            "kind": "synthetic",
            "identifier": "SYNTHETIC-ONLY",
            "title": "Synthetic fixture",
            "snapshot_count": 30,
            "predicate_version": "synthetic-v1",
            "source_fingerprint": "f" * 64,
        }
        plan = build_catalog_plan(
            master,
            config,
            "release-fixture",
            source["title"],
            source["identifier"],
            evaluation,
            source_manifest=source,
        )
        self.paths = {
            "source": self.root / "source.json",
            "config": self.root / "config.json",
            "master": self.root / "master.csv",
            "evaluation": self.root / "evaluation.json",
            "validation": self.root / "validation.json",
            "plan": self.root / "plan.json",
            "output": self.root / "release-seal.json",
        }
        for key, value in {
            "source": source,
            "config": config,
            "evaluation": evaluation,
            "validation": validation,
            "plan": plan,
        }.items():
            self.paths[key].write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        write_csv(self.paths["master"], master)
        self.master = master

    def tearDown(self):
        self.temp.cleanup()

    def build(self) -> dict:
        return build_release_seal(
            source_path=self.paths["source"],
            config_path=self.paths["config"],
            master_path=self.paths["master"],
            evaluation_path=self.paths["evaluation"],
            validation_path=self.paths["validation"],
            plan_path=self.paths["plan"],
            output_path=self.paths["output"],
        )

    def test_release_seal_binds_candidate_and_defaults_publication_closed(self):
        seal = self.build()
        write_release_seal(self.paths["output"], seal)
        report = audit_release_seal(self.paths["output"])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(seal["status"], "SEALED_FOR_WRITE_TEST")
        self.assertTrue(seal["write_authority"]["test_write"])
        self.assertFalse(seal["write_authority"]["production_write"])
        self.assertFalse(seal["publication"]["publication_clearance"])

    def test_post_seal_config_drift_fails_audit(self):
        seal = self.build()
        write_release_seal(self.paths["output"], seal)
        config = json.loads(self.paths["config"].read_text(encoding="utf-8"))
        config["seed"] += 1
        self.paths["config"].write_text(json.dumps(config), encoding="utf-8")
        report = audit_release_seal(self.paths["output"])
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("config" in error and "drift" in error for error in report["errors"]))

    def test_seal_cannot_grant_itself_production_or_publication_authority(self):
        seal = self.build()
        seal["write_authority"]["production_write"] = True
        seal["publication"]["publication_clearance"] = True
        write_release_seal(self.paths["output"], seal)
        report = audit_release_seal(self.paths["output"])
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("write authority" in error for error in report["errors"]))
        self.assertTrue(any("publication" in error for error in report["errors"]))

    def test_source_fingerprint_must_match_plan(self):
        source = json.loads(self.paths["source"].read_text(encoding="utf-8"))
        source["kind"] = "visible-library-stills"
        source["source_fingerprint"] = "a" * 64
        self.paths["source"].write_text(json.dumps(source), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source fingerprint"):
            self.build()

    def test_publication_review_is_separate_and_default_closed(self):
        rows = scaffold(self.master)
        self.assertTrue(all(row["publication_approved"] == "false" for row in rows))
        errors, report = validate_publication(rows)
        self.assertEqual(errors, [])
        self.assertEqual(report["publication_approved"], 0)
        rows[0]["publication_approved"] = "true"
        errors, report = validate_publication(rows)
        self.assertTrue(errors)
        self.assertEqual(report["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
