"""Setup command."""

import argparse
import sys
from collections.abc import Callable
from datetime import datetime, timezone

from uidetox.design_context import (
    DesignIntent,
    DesignSettings,
    merge_explicit_design_intent,
)
from uidetox.intent_journal import record_intent_artifacts
from uidetox.state import (
    ensure_uidetox_dir,
    get_project_root,
    get_uidetox_dir,
    load_config,
    save_config,
)


DEFAULT_CONFIG = {
    "DESIGN_VARIANCE": 8,
    "MOTION_INTENSITY": 6,
    "VISUAL_DENSITY": 4,
    "auto_commit": False,
}

_INTENT_ARGUMENTS = {
    "product_goal": "product_goal",
    "audience": "audience",
    "primary_job": "primary_job",
    "tone": "tone",
    "genre": "genre",
    "page_kind": "page_kind",
    "brand": "brand",
}

_INTENT_INTERVIEW = (
    ("product_goal", "Website/app purpose (why it exists)"),
    ("audience", "Primary audience"),
    ("primary_job", "Primary user job"),
    ("tone", "Desired tone"),
    ("brand", "Brand signals to preserve"),
)


def _is_interactive() -> bool:
    stdin = getattr(sys, "stdin", None)
    return bool(stdin and hasattr(stdin, "isatty") and stdin.isatty())


def _intent_updates_from_args(args: argparse.Namespace) -> dict[str, object]:
    updates: dict[str, object] = {}
    for argument, field_name in _INTENT_ARGUMENTS.items():
        value = getattr(args, argument, None)
        if isinstance(value, str) and value.strip():
            updates[field_name] = value.strip()
    for argument, field_name in (
        ("preserve", "preserve"),
        ("constraint", "constraints"),
    ):
        values = getattr(args, argument, None)
        if values is not None:
            cleaned = tuple(
                str(value).strip() for value in values if str(value).strip()
            )
            if cleaned:
                updates[field_name] = cleaned
    return updates


def _prompt(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _interactive_intent_updates(
    current: DesignIntent,
    supplied_fields: set[str],
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    ask = input_fn or _prompt
    output = output_fn or print
    output("\nIntent preflight (Enter = keep existing or defer to map inference):")
    updates: dict[str, object] = {}
    for field_name, label in _INTENT_INTERVIEW:
        if field_name in supplied_fields:
            continue
        current_value = (
            getattr(current, field_name)
            if current.provenance.get(field_name) == "explicit"
            else ""
        )
        suffix = f" [{current_value}]" if current_value else ""
        try:
            answer = str(ask(f"  {label}{suffix}: ")).strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer:
            updates[field_name] = answer

    for field_name, label in (
        ("preserve", "Must preserve (comma-separated)"),
        ("constraints", "Constraints (comma-separated)"),
    ):
        if field_name in supplied_fields:
            continue
        current_values = (
            getattr(current, field_name)
            if current.provenance.get(field_name) == "explicit"
            else ()
        )
        suffix = f" [{', '.join(current_values)}]" if current_values else ""
        try:
            answer = str(ask(f"  {label}{suffix}: ")).strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer:
            updates[field_name] = tuple(
                item.strip() for item in answer.split(",") if item.strip()
            )
    return updates


def capture_interactive_intent(
    config: dict[str, object],
    *,
    supplied_fields: set[str] | None = None,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
    confirmed_at: str | None = None,
) -> tuple[DesignSettings, bool]:
    """Run the shared intent interview and update the current config projection."""

    settings = DesignSettings.from_config(config)
    updates = _interactive_intent_updates(
        settings.intent,
        supplied_fields or set(),
        input_fn=input_fn,
        output_fn=output_fn,
    )
    if not updates:
        return settings, False
    config["design_intent"] = merge_explicit_design_intent(
        config.get("design_intent"),
        updates,
        evidence_source="user:interactive-setup",
        confirmed_at=confirmed_at or _confirmed_now(),
    )
    return DesignSettings.from_config(config), True


def _confirmed_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(args: argparse.Namespace):
    print("==============================")
    print(" UIdetox Setup")
    print("==============================")

    ensure_uidetox_dir()
    config = load_config()

    for key, default_value in DEFAULT_CONFIG.items():
        config.setdefault(key, default_value)

    if getattr(args, "design_variance", None) is not None:
        config["DESIGN_VARIANCE"] = args.design_variance
    if getattr(args, "motion_intensity", None) is not None:
        config["MOTION_INTENSITY"] = args.motion_intensity
    if getattr(args, "visual_density", None) is not None:
        config["VISUAL_DENSITY"] = args.visual_density

    intent_updates = _intent_updates_from_args(args)
    intent_update_sources: list[str] = []
    configured_intent = merge_explicit_design_intent(
        config.get("design_intent"),
        intent_updates,
        evidence_source="user:cli-setup",
        confirmed_at=_confirmed_now(),
    )
    if configured_intent:
        config["design_intent"] = configured_intent
    else:
        config.pop("design_intent", None)
    if intent_updates:
        intent_update_sources.append("cli")

    settings = DesignSettings.from_config(config)
    if _is_interactive() and not getattr(args, "no_intent_prompt", False):
        settings, interactive_changed = capture_interactive_intent(
            config,
            supplied_fields=set(intent_updates),
            input_fn=_prompt,
            output_fn=print,
            confirmed_at=_confirmed_now(),
        )
        if interactive_changed:
            intent_update_sources.append("interactive")

    config.update(settings.dials.to_config())

    dev_server = getattr(args, "dev_server", None)
    if isinstance(dev_server, str) and dev_server.strip():
        config["dev_server"] = dev_server.strip()

    visual_config = config.get("visual_evidence", {})
    if not isinstance(visual_config, dict):
        visual_config = {}
    visual_threshold = getattr(args, "visual_threshold", None)
    if visual_threshold is not None:
        visual_config["threshold"] = visual_threshold
    visual_max_pixels = getattr(args, "visual_max_pixels", None)
    if visual_max_pixels is not None:
        if visual_max_pixels <= 0:
            raise SystemExit("--visual-max-pixels must be greater than zero")
        visual_config["max_pixels"] = visual_max_pixels
    visual_evidence_file = getattr(args, "visual_evidence_file", None)
    if isinstance(visual_evidence_file, str) and visual_evidence_file.strip():
        visual_config["manifest_path"] = visual_evidence_file.strip()
    require_visual_evidence = getattr(args, "require_visual_evidence", None)
    if require_visual_evidence is not None:
        visual_config["required"] = require_visual_evidence
    if visual_config:
        config["visual_evidence"] = visual_config

    auto_commit = getattr(args, "auto_commit", None)
    print(f"\nCurrent auto_commit status: {config.get('auto_commit', False)}")

    if auto_commit is not None:
        config["auto_commit"] = auto_commit
        status = "enabled" if auto_commit else "disabled"
        print(f"⚙️  Auto-commit {status} via flag.")
    else:
        if _is_interactive():
            try:
                ans = (
                    input(
                        "Enable automated git commits for each resolved issue? (y/n): "
                    )
                    .strip()
                    .lower()
                )
            except EOFError:
                ans = ""
            if ans == "y":
                config["auto_commit"] = True
            elif ans == "n":
                config["auto_commit"] = False
        else:
            print(
                "Non-interactive mode detected — keeping existing auto_commit setting."
            )

    print("\nCurrent configuration:")
    print(f"  DESIGN_VARIANCE:  {config.get('DESIGN_VARIANCE', 8)}")
    print(f"  MOTION_INTENSITY: {config.get('MOTION_INTENSITY', 6)}")
    print(f"  VISUAL_DENSITY:   {config.get('VISUAL_DENSITY', 4)}")
    print(f"  AUTO_COMMIT:      {config.get('auto_commit', False)}")
    if config.get("dev_server"):
        print(f"  DEV_SERVER:       {config['dev_server']}")
    if visual_config:
        print(
            "  VISUAL_EVIDENCE:  "
            f"{'required' if visual_config.get('required') else 'optional'}"
        )
    print(f"  PRODUCT_GOAL:     {settings.intent.product_goal}")
    print(f"  AUDIENCE:         {settings.intent.audience}")
    print(f"  PRIMARY_JOB:      {settings.intent.primary_job}")
    print(f"  TONE / GENRE:     {settings.intent.tone} / {settings.intent.genre}")
    print(f"  PAGE_KIND:        {settings.intent.page_kind}")
    print(f"  INTENT_STATUS:    {settings.intent.confirmation_status}")

    print("\n[AGENT INSTRUCTION]")
    print(
        "Use `uidetox setup --design-variance ... --motion-intensity ... --visual-density ...` to persist dials explicitly."
    )
    print(
        "Set `--dev-server http://localhost:5173` when your preview is not on port 3000."
    )
    print("Run `uidetox intent` to inspect field-level provenance and confidence.")
    print("Proceed to run `uidetox scan` to begin detoxifying the frontend.")

    # Ensures config exists if it didn't
    save_config(config)
    if intent_update_sources and settings.intent.confirmation_status == "confirmed":
        artifacts = record_intent_artifacts(
            settings.intent,
            source=f"setup:{'+'.join(intent_update_sources)}",
            project_root=get_project_root(),
            uidetox_dir=get_uidetox_dir(),
        )
        print(f"\nIntent event saved: {artifacts.event['event_id']}")
        print(f"Agent handoff saved: {artifacts.handoff_path}")
        print("\nCopy-ready agent prompt:\n")
        print(artifacts.prompt)
