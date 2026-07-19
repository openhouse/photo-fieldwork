import unittest
from copy import deepcopy

from photo_fieldwork.integrity import canonical_json_fingerprint
from photo_fieldwork.release import compare_execution_receipts, validate_helper_profile, verify_execution_receipt


def helper_profile() -> dict:
    return {
        "schema_version": 1,
        "bundle_identifier": "org.openhouse.synthetic-helper",
        "binary_sha256": "sha256:" + "1" * 64,
        "capabilities": [
            "membership-only-write",
            "receipt-plan-digest",
            "launch-nonce",
            "exact-folder-topology",
        ],
        "supported_plan_schema_versions": [2],
    }


def plan() -> dict:
    helper = helper_profile()
    return {
        "schema_version": 2,
        "plan_id": "PLAN-1",
        "source": {"id": "SOURCE-1", "actual_count": 2, "fingerprint": "sha256:" + "2" * 64},
        "helper_requirement": {
            "bundle_identifier": helper["bundle_identifier"],
            "binary_sha256": helper["binary_sha256"],
            "required_capabilities": helper["capabilities"],
            "plan_schema_version": 2,
        },
        "folders": [{"key": "version", "title": "Version", "parent_key": None}],
        "albums": [
            {
                "key": "master",
                "title": "Master",
                "parent_folder_key": "version",
                "asset_identifiers": ["A", "B"],
            }
        ],
    }


def receipt(release_plan: dict, nonce: str = "a" * 32, completed_at: str = "2026-07-19T10:00:00+00:00") -> dict:
    helper = helper_profile()
    return {
        "schema_version": 1,
        "completed_at": completed_at,
        "execution_nonce": nonce,
        "plan_file_sha256": "sha256:" + "3" * 64,
        "plan_id": release_plan["plan_id"],
        "plan_fingerprint": canonical_json_fingerprint(release_plan),
        "source_id": release_plan["source"]["id"],
        "source_count": release_plan["source"]["actual_count"],
        "source_fingerprint": release_plan["source"]["fingerprint"],
        "helper": {
            "bundle_identifier": helper["bundle_identifier"],
            "binary_sha256": helper["binary_sha256"],
        },
        "folders": [
            {"key": "version", "title": "Version", "identifier": "FOLDER-1", "parent_identifier": None}
        ],
        "albums": [
            {
                "key": "master",
                "title": "Master",
                "identifier": "ALBUM-1",
                "parent_identifier": "FOLDER-1",
                "count": 2,
            }
        ],
    }


class ReleaseContractTests(unittest.TestCase):
    def test_helper_capabilities_are_negotiated_before_write(self):
        profile = helper_profile()
        self.assertEqual(validate_helper_profile(profile), [])
        profile["capabilities"].remove("launch-nonce")
        self.assertTrue(any("launch-nonce" in error for error in validate_helper_profile(profile)))

    def test_receipt_binds_plan_bytes_helper_source_and_topology(self):
        release_plan = plan()
        result = receipt(release_plan)
        self.assertEqual(
            verify_execution_receipt(result, release_plan, helper_profile(), result["plan_file_sha256"]),
            [],
        )
        substituted = helper_profile()
        substituted["binary_sha256"] = "sha256:" + "4" * 64
        result["helper"]["binary_sha256"] = substituted["binary_sha256"]
        errors = verify_execution_receipt(result, release_plan, substituted, "sha256:" + "5" * 64)
        self.assertTrue(any("authorized helper" in error for error in errors))
        self.assertTrue(any("executed plan bytes" in error for error in errors))

    def test_idempotence_requires_distinct_equivalent_executions(self):
        release_plan = plan()
        first = receipt(release_plan)
        second = receipt(release_plan, "b" * 32, "2026-07-19T10:05:00+00:00")
        self.assertTrue(compare_execution_receipts(first, second, release_plan, helper_profile())["passed"])

        copied = deepcopy(first)
        copied["completed_at"] = second["completed_at"]
        self.assertFalse(compare_execution_receipts(first, copied, release_plan, helper_profile())["passed"])

        second["albums"][0]["identifier"] = "ALBUM-2"
        report = compare_execution_receipts(first, second, release_plan, helper_profile())
        self.assertFalse(report["passed"])
        self.assertTrue(any("topology" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
