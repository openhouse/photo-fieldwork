import unittest

from photo_fieldwork.pipeline import master_sha256
from photo_fieldwork.publication import PUBLIC_FIELDS, build_public_handoff, scaffold_clearance


def bound_master(*identifiers: str):
    rows = [
        {
            "uuid": identifier,
            "filename": f"{identifier}.jpg",
            "primary_view": "work",
            "assigned_view": "work",
            "config_sha256": "a" * 64,
        }
        for identifier in identifiers
    ]
    digest = master_sha256(rows)
    proposal_id = f"pfp-{digest[:16]}"
    for row in rows:
        row["master_sha256"] = digest
        row["proposal_id"] = proposal_id
    return rows


def clear(row: dict[str, str], destination: str = "portfolio-home") -> None:
    row.update(
        {
            "publication_status": "cleared-for-specific-use",
            "rights_status": "owner-verified",
            "consent_status": "cleared-for-use",
            "claim_status": "visible-only",
            "safety_status": "clear",
            "caption": "A public-safe visible description.",
            "alt_text": "A person works at a table.",
            "credit": "Jamie Burkart",
            "public_destination": destination,
            "reviewer_actor": "Jamie Burkart",
            "reviewer_lens": "human-review",
            "review_date": "2026-07-19",
        }
    )


class PublicationTests(unittest.TestCase):
    def test_scaffold_is_default_closed_and_projection_is_empty(self):
        master = bound_master("ARCHIVE-001")
        clearance = scaffold_clearance(master)
        self.assertEqual(clearance[0]["publication_status"], "not-reviewed")
        self.assertEqual(clearance[0]["safety_status"], "human-needs-review")
        projected, errors = build_public_handoff(
            master, clearance, "private-salt-value", "portfolio-home"
        )
        self.assertEqual(projected, [])
        self.assertEqual(errors, [])

    def test_projection_requires_all_clearances_and_uses_an_allowlist(self):
        master = bound_master("ARCHIVE-001")
        clearance = scaffold_clearance(master)
        clear(clearance[0])
        clearance[0].update(
            {
                "primary_view": "poisoned-view",
                "local_path": "/private/archive/image.jpg",
                "persons": "Private Person",
                "raw_ocr": "private correspondence",
                "safety_reason": "private home",
            }
        )
        projected, errors = build_public_handoff(
            master, clearance, "private-salt-value", "portfolio-home"
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(projected), 1)
        self.assertEqual(tuple(projected[0]), PUBLIC_FIELDS)
        self.assertEqual(projected[0]["primary_view"], "work")
        rendered = repr(projected)
        for forbidden in ("ARCHIVE-001", "/private/", "Private Person", "raw_ocr"):
            self.assertNotIn(forbidden, rendered)

    def test_one_invalid_claimed_clearance_blocks_the_entire_projection(self):
        master = bound_master("ARCHIVE-001", "ARCHIVE-002")
        clearance = scaffold_clearance(master)
        for row in clearance:
            clear(row)
        clearance[1]["reviewer_lens"] = "delegated-editorial-inference"
        projected, errors = build_public_handoff(
            master, clearance, "private-salt-value", "portfolio-home"
        )
        self.assertEqual(projected, [])
        self.assertTrue(any("human publication authority" in error for error in errors))

    def test_projection_rejects_stale_master_or_unknown_clearance_rows(self):
        master = bound_master("ARCHIVE-001")
        stale = [dict(master[0], assigned_view="changed")]
        with self.assertRaisesRegex(ValueError, "exact bound master"):
            scaffold_clearance(stale)
        clearance = scaffold_clearance(master)
        clearance.append(dict(clearance[0], uuid="OUTSIDE-MASTER"))
        with self.assertRaisesRegex(ValueError, "outside the exact master"):
            build_public_handoff(master, clearance, "private-salt-value", "portfolio-home")

    def test_public_ids_are_destination_bound_and_formula_rows_fail_closed(self):
        master = bound_master("ARCHIVE-001")
        clearance = scaffold_clearance(master)
        clear(clearance[0], "portfolio-home")
        home, errors = build_public_handoff(
            master, clearance, "private-salt-value", "portfolio-home"
        )
        self.assertEqual(errors, [])
        clearance[0]["public_destination"] = "project-case-study"
        project, errors = build_public_handoff(
            master, clearance, "private-salt-value", "project-case-study"
        )
        self.assertEqual(errors, [])
        self.assertNotEqual(home[0]["public_id"], project[0]["public_id"])
        clearance[0]["caption"] = "=HYPERLINK(\"private\")"
        projected, errors = build_public_handoff(
            master, clearance, "private-salt-value", "project-case-study"
        )
        self.assertEqual(projected, [])
        self.assertTrue(any("formula marker" in error for error in errors))
        clearance[0]["caption"] = "Safe caption"
        clearance[0]["public_destination"] = "=public-feed"
        with self.assertRaisesRegex(ValueError, "formula marker"):
            build_public_handoff(master, clearance, "private-salt-value", "=public-feed")


if __name__ == "__main__":
    unittest.main()
