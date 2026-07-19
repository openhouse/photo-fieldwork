#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--operation",
        choices=("ten-item-test", "production", "production-idempotence-rerun", "verify"),
        required=True,
    )
    args = parser.parse_args()
    scenario = read_json(args.scenario)
    args.workspace.mkdir(parents=True, exist_ok=True)
    state_path = args.workspace / "fake-catalog.json"
    trace_path = args.workspace / "invocation-trace.json"
    state = read_json(state_path) if state_path.exists() else {"albums": {}}
    trace = read_json(trace_path) if trace_path.exists() else []
    master = scenario["manifests"]["master"]
    changed = False

    if args.operation == "ten-item-test":
        state["albums"]["write-test"] = master[:10]
        changed = True
    elif args.operation in {"production", "production-idempotence-rerun"}:
        changed = state["albums"].get("production") != master
        state["albums"]["production"] = list(master)
    else:
        source = set(scenario["source"]["observed_members"])
        holds = set(scenario["manifests"]["holds"])
        actual = set(state["albums"].get("production", []))
        planned = set(master)
        report = {
            "status": "PASS",
            "missing": len(planned - actual),
            "unexpected": len(actual - planned),
            "outside_source": len(actual - source),
            "hold_overlap": len(actual & holds),
            "topology_errors": 0 if "production" in state["albums"] else 1,
            "writer": "synthetic-read-write-fake",
            "verifier": "synthetic-independent-reader",
        }
        report["status"] = "PASS" if all(
            report[key] == 0
            for key in ("missing", "unexpected", "outside_source", "hold_overlap", "topology_errors")
        ) else "FAIL"
        write_json(args.workspace / "verification.json", report)

    trace.append({"operation": args.operation, "changed": changed})
    write_json(state_path, state)
    write_json(trace_path, trace)


if __name__ == "__main__":
    main()
