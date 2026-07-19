"""Inspect effective product/design intent and its provenance."""

import argparse
import json
import sys

from uidetox.design_context import DesignSettings
from uidetox.frontend_map import (
    FRONTEND_MAP_FILE,
    frontend_map_is_fresh,
    load_frontend_map,
)
from uidetox.intent_journal import latest_intent_artifact_reference
from uidetox.state import get_project_root, get_uidetox_dir, load_config


def _load_inputs():
    root = get_project_root()
    config = load_config()
    map_path = get_uidetox_dir() / FRONTEND_MAP_FILE
    if not map_path.exists():
        return config, None, "missing"
    try:
        frontend_map = load_frontend_map(map_path)
    except (FileNotFoundError, ValueError):
        return config, None, "unreadable"
    if not frontend_map_is_fresh(frontend_map, root, frontend_map.target):
        return config, None, "stale"
    return config, frontend_map, "current"


def run(args: argparse.Namespace) -> None:
    config, frontend_map, map_status = _load_inputs()
    target = frontend_map.target if frontend_map is not None else "."
    intent = DesignSettings.from_config(config, frontend_map, target).intent
    payload = intent.to_dict()
    payload["map_evidence_status"] = map_status
    journal = latest_intent_artifact_reference(
        get_uidetox_dir(),
        project_root=get_project_root(),
    )
    payload["journal"] = journal

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("UIdetox Intent")
        print(f"  Confirmation: {intent.confirmation_status}")
        print(f"  Map evidence: {map_status}")
        print(f"  Intent journal: {journal['status']}")
        if journal.get("latest_event_id"):
            print(f"  Latest event: {journal['latest_event_id']}")
        if journal.get("handoff_path"):
            print(f"  Agent handoff: {journal['handoff_path']}")
        for field_name, source in intent.provenance.items():
            value = getattr(intent, field_name)
            rendered = ", ".join(value) if isinstance(value, tuple) else value
            confidence = intent.confidence.get(field_name, 0.0)
            evidence = ", ".join(intent.evidence.get(field_name, ()))
            print(f"\n  {field_name}: {rendered}")
            print(f"    source={source} confidence={confidence:.2f}")
            print(f"    evidence={evidence}")
        if intent.unconfirmed_fields:
            print(
                "\n  User confirmation needed: " + ", ".join(intent.unconfirmed_fields)
            )
            print("  Run: uidetox setup")

    if (
        getattr(args, "require_confirmed", False)
        and intent.confirmation_status != "confirmed"
    ):
        print(
            "Intent is not user-confirmed. Run `uidetox setup` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)
