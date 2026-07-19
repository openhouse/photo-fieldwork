from __future__ import annotations

import json
from pathlib import Path

from photo_fieldwork.evalbank import validate_eval_bank


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    bank = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
    report = validate_eval_bank(bank)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
