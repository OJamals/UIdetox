from pathlib import Path


def test_shipped_guidance_distinguishes_standards_from_house_style(
    project_root: Path,
) -> None:
    skill = (project_root / "SKILL.md").read_text(encoding="utf-8")
    accessibility = (
        project_root / "reference" / "accessibility-and-inclusive-design.md"
    ).read_text(encoding="utf-8")

    assert "Normative baseline" in skill
    assert "accessibility-and-inclusive-design.md" in skill
    assert "APG is informative" in accessibility
    for requirement in (
        "24×24 CSS pixels",
        "spacing exception",
        "Focus Not Obscured",
        "Dragging Movements",
        "Consistent Help",
        "Redundant Entry",
        "Accessible Authentication",
        'role="status"',
    ):
        assert requirement in accessibility


def test_shipped_guidance_covers_full_stack_ui_contract_lifecycle(
    project_root: Path,
) -> None:
    skill = (project_root / "SKILL.md").read_text(encoding="utf-8")
    full_stack = (project_root / "reference" / "full-stack-integration.md").read_text(
        encoding="utf-8"
    )

    assert "full-stack-integration.md" in skill
    for requirement in (
        "server remains authoritative",
        "RFC 9457",
        "authorization",
        "idempotency",
        "optimistic",
        "rollback",
        "rate limit",
        "cache invalidation",
        "partial success",
        "observability",
    ):
        assert requirement in full_stack


def test_guidance_does_not_present_house_preferences_as_universal_requirements(
    project_root: Path,
) -> None:
    paths = (
        project_root / "SKILL.md",
        project_root / "reference" / "interaction-design.md",
        project_root / "reference" / "typography.md",
        project_root / "commands" / "animate.md",
        project_root / "commands" / "polish.md",
        project_root / "uidetox" / "commands" / "autofix.py",
        project_root / "uidetox" / "commands" / "next.py",
        project_root / "uidetox" / "subagent.py",
    )
    guidance = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for overclaim in (
        "Ensure touch targets are 44px minimum.",
        "A single <h1> per page",
        "Label MUST sit above input",
        "Remove all console.log/warn/error statements.",
        "If the same className, handler, or markup appears twice, it should be a component.",
        "Banned fonts: Inter, Roboto, Arial, Open Sans, system-ui as primary",
        "Every interactive element needs these states designed:",
        "Offset from element (not inside it)",
        "Every interactive element needs all states:",
        "Always provide non-animated alternatives for users who need them.",
        "Add hover:, focus:ring, active: states to all interactive elements.",
        "All <label> elements must have an 'htmlFor' attribute",
        "All state changes animated appropriately (150-300ms)",
        "Never use Inter, Roboto, or system-ui as primary.",
    ):
        assert overclaim not in guidance


def test_shipped_command_guidance_avoids_obsolete_universal_ui_thresholds(
    project_root: Path,
) -> None:
    command_guidance = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((project_root / "commands").glob("*.md"))
    )

    for overclaim in (
        "44x44px minimum",
        "< 44x44px",
        "<44x44px",
        "Larger text (16px minimum)",
        "Set minimum readable sizes (14px on mobile)",
        "No text smaller than 14px",
        "Two-column layouts (not single or three-column)",
        "Side navigation always visible",
        "Single column only",
        "All transitions smooth (60fps)",
    ):
        assert overclaim not in command_guidance

    assert "24×24 CSS pixels" in command_guidance
    assert "documented exception" in command_guidance
    assert "INP" in command_guidance


def test_shipped_reference_guidance_uses_current_target_size_levels(
    project_root: Path,
) -> None:
    reference_guidance = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((project_root / "reference").glob("*.md"))
    )

    assert (
        "Buttons can look small but need large touch targets (44px minimum)."
        not in (reference_guidance)
    )
    assert "24×24 CSS pixel minimum" in reference_guidance
    assert "44×44 CSS pixels" in reference_guidance
