import unittest

from photo_fieldwork.source import build_source_profile, fingerprint_identifiers, verify_source_profile


class SourceProfileTests(unittest.TestCase):
    def test_fingerprint_is_order_independent_and_canonicalizes_local_identifiers(self):
        first = fingerprint_identifiers(["A/L0/001", "B"])
        second = fingerprint_identifiers(["B/L0/040", "A"])
        self.assertEqual(first, second)

    def test_same_count_different_membership_fails(self):
        profile = build_source_profile(
            [{"uuid": "A"}, {"uuid": "B"}],
            profile_id="test://source",
            kind="synthetic",
            scope="test source",
            inventory="fixture.csv",
        )
        errors = verify_source_profile(profile, ["A", "C"])
        self.assertFalse(any("count changed" in error for error in errors))
        self.assertTrue(any("fingerprint changed" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
