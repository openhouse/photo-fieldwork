import json
import unittest
from pathlib import Path


class SchemaTests(unittest.TestCase):
    def test_every_schema_is_valid_json_with_an_object_root(self):
        root = Path(__file__).resolve().parents[1] / "schemas"
        schemas = sorted(root.glob("*.json"))
        self.assertGreaterEqual(len(schemas), 4)
        for path in schemas:
            with self.subTest(path=path.name):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(value.get("type"), "object")
                self.assertIn("$schema", value)
