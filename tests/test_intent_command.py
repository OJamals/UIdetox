"""Intent inspection command and confirmation gate."""

import json

import pytest

from uidetox.cli import parse_args
from uidetox.commands import intent as intent_command


def test_intent_command_is_registered():
    args = parse_args(["intent", "--json", "--require-confirmed"])

    assert args.command == "intent"
    assert args.json is True
    assert args.require_confirmed is True


def test_intent_command_json_exposes_provenance(monkeypatch, capsys):
    monkeypatch.setattr(
        intent_command,
        "_load_inputs",
        lambda: (
            {
                "design_intent": {
                    "product_goal": "reduce scheduling errors",
                    "audience": "clinic coordinators",
                    "primary_job": "resolve appointment conflicts",
                    "provenance": {
                        "product_goal": "explicit",
                        "audience": "explicit",
                        "primary_job": "explicit",
                    },
                    "evidence": {
                        "product_goal": ["user:cli-setup"],
                        "audience": ["user:cli-setup"],
                        "primary_job": ["user:cli-setup"],
                    },
                    "confidence": {
                        "product_goal": 1.0,
                        "audience": 1.0,
                        "primary_job": 1.0,
                    },
                    "confirmed_at": "2026-07-17T12:00:00+00:00",
                }
            },
            None,
            "missing",
        ),
    )

    intent_command.run(parse_args(["intent", "--json", "--require-confirmed"]))

    payload = json.loads(capsys.readouterr().out)
    assert payload["confirmation_status"] == "confirmed"
    assert payload["provenance"]["product_goal"] == "explicit"
    assert payload["evidence"]["product_goal"] == ["user:cli-setup"]
    assert payload["map_evidence_status"] == "missing"


def test_intent_command_confirmation_gate_rejects_inference(monkeypatch):
    monkeypatch.setattr(intent_command, "_load_inputs", lambda: ({}, None, "missing"))

    with pytest.raises(SystemExit) as exc:
        intent_command.run(parse_args(["intent", "--require-confirmed"]))

    assert exc.value.code == 2
