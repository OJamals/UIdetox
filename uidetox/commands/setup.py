"""Setup command."""

import argparse
import sys

from uidetox.design_context import DesignSettings
from uidetox.state import save_config, ensure_uidetox_dir, load_config


DEFAULT_CONFIG = {
    "DESIGN_VARIANCE": 8,
    "MOTION_INTENSITY": 6,
    "VISUAL_DENSITY": 4,
    "auto_commit": False,
}


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

    existing_settings = DesignSettings.from_config(config)
    intent = {
        field_name: getattr(existing_settings.intent, field_name)
        for field_name, source in existing_settings.intent.provenance.items()
        if source == "explicit"
    }
    provenance = {field_name: "explicit" for field_name in intent}
    intent_fields = {
        "audience": "audience",
        "primary_job": "primary_job",
        "tone": "tone",
        "genre": "genre",
        "page_kind": "page_kind",
        "brand": "brand",
    }
    for argument, key in intent_fields.items():
        value = getattr(args, argument, None)
        if isinstance(value, str) and value.strip():
            intent[key] = value.strip()
            provenance[key] = "explicit"
    for argument, key in (("preserve", "preserve"), ("constraint", "constraints")):
        values = getattr(args, argument, None)
        if values is not None:
            cleaned = [str(value).strip() for value in values if str(value).strip()]
            if cleaned:
                intent[key] = cleaned
                provenance[key] = "explicit"
    if intent:
        intent["source"] = "configured"
        intent["provenance"] = provenance
        config["design_intent"] = intent
    else:
        config.pop("design_intent", None)

    settings = DesignSettings.from_config(config)
    config.update(settings.dials.to_config())
    serialized_intent = settings.intent.to_dict()
    explicit_intent = {
        field_name: serialized_intent[field_name]
        for field_name, source in settings.intent.provenance.items()
        if source == "explicit"
    }
    if explicit_intent:
        explicit_intent["source"] = "configured"
        explicit_intent["provenance"] = {
            field_name: "explicit" for field_name in explicit_intent
        }
        config["design_intent"] = explicit_intent
    else:
        config.pop("design_intent", None)

    dev_server = getattr(args, "dev_server", None)
    if isinstance(dev_server, str) and dev_server.strip():
        config["dev_server"] = dev_server.strip()

    auto_commit = getattr(args, "auto_commit", None)
    print(f"\nCurrent auto_commit status: {config.get('auto_commit', False)}")

    if auto_commit is not None:
        config["auto_commit"] = auto_commit
        status = "enabled" if auto_commit else "disabled"
        print(f"⚙️  Auto-commit {status} via flag.")
    else:
        stdin = getattr(sys, "stdin", None)
        is_interactive = bool(stdin and hasattr(stdin, "isatty") and stdin.isatty())
        if is_interactive:
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
    print(f"  AUDIENCE:         {settings.intent.audience}")
    print(f"  PRIMARY_JOB:      {settings.intent.primary_job}")
    print(f"  TONE / GENRE:     {settings.intent.tone} / {settings.intent.genre}")
    print(f"  PAGE_KIND:        {settings.intent.page_kind}")

    print("\n[AGENT INSTRUCTION]")
    print(
        "Use `uidetox setup --design-variance ... --motion-intensity ... --visual-density ...` to persist dials explicitly."
    )
    print(
        "Set `--dev-server http://localhost:5173` when your preview is not on port 3000."
    )
    print("Proceed to run `uidetox scan` to begin detoxifying the frontend.")

    # Ensures config exists if it didn't
    save_config(config)
