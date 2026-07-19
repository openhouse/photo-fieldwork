import unittest

from photo_fieldwork.safety import may_enter_general_master, normalize_safety_state, validate_safety_transition


class SafetyTests(unittest.TestCase):
    def test_legacy_states_normalize_without_weakening_restrictions(self):
        self.assertEqual(normalize_safety_state("clear"), "clear_automated")
        self.assertEqual(normalize_safety_state("hold"), "hold_automated")
        self.assertEqual(normalize_safety_state("needs-review"), "review_sensitive")
        self.assertFalse(may_enter_general_master("review_sensitive"))

    def test_automation_cannot_grant_clearance(self):
        with self.assertRaisesRegex(ValueError, "requires actor=human-editor"):
            validate_safety_transition("review_sensitive", "cleared_public_candidate", "automation")
        self.assertEqual(
            validate_safety_transition("review_sensitive", "cleared_public_candidate", "human-editor"),
            ("review_sensitive", "cleared_public_candidate"),
        )


if __name__ == "__main__":
    unittest.main()
