"""Review command: captures LLM subjective UX quality assessment."""

import argparse
import json
from uidetox.state import load_config, load_state, save_state, ensure_uidetox_dir


def run(args: argparse.Namespace):
    score = getattr(args, "score", None)

    if score is not None:
        # Store the subjective score
        _store_subjective_score(score)
        return

    config = load_config()
    tooling = config.get("tooling", {})
    has_fullstack = bool(
        tooling.get("backend") or tooling.get("database") or tooling.get("api")
    )

    # Check for visual snapshot
    from uidetox.state import get_uidetox_dir
    snapshot = get_uidetox_dir() / "snapshots" / "latest.png"
    has_snapshot = snapshot.exists()

    print("+" + "=" * 58 + "+")
    print("| UIdetox Subjective Review                                |")
    print("+" + "=" * 58 + "+")
    print()
    print("  Perform a deep, subjective quality review of this project.")
    print("  Evaluate the OVERALL design — not individual issues, but the holistic feel.")
    print()

    # ---- A. VISUAL DESIGN & AESTHETICS (40 pts) ----
    print("  A. VISUAL DESIGN & AESTHETICS (0-40)")
    print("  " + "-" * 50)
    print()
    print("    STYLING & ELEGANCE (0-15)")
    print("      -> Surface textures, color relationships, shadow/border craft")
    print("      -> Does it feel polished or rough? Premium or cheap?")
    print("      -> Visual rhythm — intentional contrast between dense and airy")
    print()
    print("    TYPOGRAPHY (0-10)")
    print("      -> Font choice, weight spectrum, scale, kerning, line-height")
    print("      -> Is there a clear type hierarchy (display, body, caption)?")
    print("      -> Are weights intentional (500/600, not just 400/700)?")
    print()
    print("    LAYOUT & SPATIAL DESIGN (0-15)")
    print("      -> Grid structure, whitespace, alignment, responsive behavior")
    print("      -> Is the layout compositional or just stacked divs?")
    print("      -> Does spacing create grouping and hierarchy, not just padding?")
    print()

    # ---- B. DESIGN SYSTEM & COHERENCE (30 pts) ----
    print("  B. DESIGN SYSTEM & COHERENCE (0-30)")
    print("  " + "-" * 50)
    print()
    print("    CONSISTENCY (0-15)")
    print("      -> Unified tokens, spacing scale, color palette, component patterns")
    print("      -> Does the same element look the same everywhere?")
    print("      -> Would a new developer know the design system from reading the code?")
    print()
    print("    IDENTITY (0-15)")
    print("      -> Does this feel designed, not generated?")
    print("      -> Is there an intentional aesthetic point-of-view?")
    print("      -> Would someone ask 'what tool made this?' (bad) or")
    print("         'who designed this?' (good)")
    print()

    # ---- C. INTERACTION & CRAFT (20 pts) ----
    print("  C. INTERACTION & CRAFT (0-20)")
    print("  " + "-" * 50)
    print()
    print("    STATES & MICRO-INTERACTIONS (0-10)")
    print("      -> Hover, focus, active, disabled, loading, empty, error states")
    print("      -> Transitions, animations, feedback on user actions")
    print("      -> Does the interface feel alive and responsive to input?")
    print()
    print("    EDGE CASES & POLISH (0-10)")
    print("      -> Error boundaries, empty states, skeleton screens, truncation")
    print("      -> Graceful degradation, mobile edge cases, keyboard navigation")
    print("      -> Does the squint test pass — clear hierarchy at a glance?")
    print()

    # ---- D. ARCHITECTURE & CODE QUALITY (10 pts) ----
    print("  D. ARCHITECTURE & CODE QUALITY (0-10)")
    print("  " + "-" * 50)
    print()
    print("    -> Component structure, file organization, naming conventions")
    print("    -> Separation of concerns (logic/presentation/data)")
    print("    -> Reusability, composability, prop/API surface area")
    if has_fullstack:
        print("    -> DTO alignment: do frontend types match backend schemas?")
        print("    -> Error surfacing: do API errors appear as meaningful UI feedback?")
        print("    -> Data flow: is fetching/caching/mutation coherent across the stack?")
    print()

    # ---- Scoring Guide ----
    print("  " + "=" * 50)
    print("  SCORING GUIDE (sum A+B+C+D = 0-100)")
    print("  " + "=" * 50)
    print()
    print("     0-30  : Heavy AI slop, generic, inconsistent")
    print("    31-50  : Some personality but obvious AI tells remain")
    print("    51-70  : Competent design with minor slop traces")
    print("    71-85  : Good design, mostly clean of AI fingerprints")
    print("    86-95  : Excellent, intentional, polished")
    print("    96-100 : Exceptional — indistinguishable from expert human design")
    print()

    if has_snapshot:
        print("-" * 60)
        print(f"📸 VISION CONTEXT: Snapshot detected at {snapshot}")
        print("   Use this image to assess layout symmetry, typography hierarchy,")
        print("   and overall visual rhythm objectively.")
        print("-" * 60)
        print()

    # ── Visual diff context (if before/after capture was run) ──
    diff_meta_path = get_uidetox_dir() / "snapshots" / "diff_meta.json"
    before_path = get_uidetox_dir() / "snapshots" / "before.png"
    after_path = get_uidetox_dir() / "snapshots" / "after.png"
    has_visual_diff = diff_meta_path.exists()

    if has_visual_diff:
        try:
            diff_meta = json.loads(diff_meta_path.read_text())
            print("=" * 60)
            print("🔍 VISUAL REGRESSION DIFF AVAILABLE")
            print("=" * 60)
            print(f"   Before: {before_path}")
            print(f"   After:  {after_path}")
            change_pct = diff_meta.get("change_percentage", "?")
            severity = diff_meta.get("severity", "unknown")
            print(f"   Pixel change: {change_pct}% ({severity})")
            if diff_meta.get("diff_image"):
                print(f"   Diff image: {diff_meta['diff_image']}")
            print()
            print("   INSTRUCTIONS FOR VISUAL DIFF REVIEW:")
            print("   1. Open the BEFORE and AFTER screenshots side by side")
            print("   2. Assess: Did the fixes IMPROVE visual quality?")
            print("   3. Check for regressions: layout shifts, missing elements, broken alignment")
            print("   4. Factor visual diff into your subjective score")
            print()
            if severity in ("major", "complete_redesign"):
                print("   ⚠️  LARGE visual change detected — verify this is intentional!")
            elif severity == "none":
                print("   ℹ️  Minimal visual change — fixes may be code-only or subtle.")
            print()
        except (json.JSONDecodeError, OSError):
            pass

    # ── Responsive snapshots context ──
    snapshots_dir = get_uidetox_dir() / "snapshots"
    responsive_viewports = ["mobile", "tablet", "desktop", "wide"]
    has_responsive = any(
        (snapshots_dir / f"after_{vp}.png").exists()
        for vp in responsive_viewports
    )

    if has_responsive:
        print("=" * 60)
        print("📱 RESPONSIVE SNAPSHOTS AVAILABLE")
        print("=" * 60)
        for vp in responsive_viewports:
            before_vp = snapshots_dir / f"before_{vp}.png"
            after_vp = snapshots_dir / f"after_{vp}.png"
            if after_vp.exists():
                status = "✅ before + after" if before_vp.exists() else "📸 after only"
                print(f"   {vp:>8}: {status}")
        print()
        print("   Review each viewport for responsive design quality.")
        print("   Check: breakpoint transitions, touch targets, readability, overflow.")
        print()

    print("[AGENT INSTRUCTION]")
    print("1. Read every frontend file in the project.")
    if has_visual_diff or has_responsive:
        print("2. Review the visual snapshots above (before/after + responsive).")
        print("3. Factor visual quality into your scoring.")
    else:
        print("2. Optional: Run `uidetox capture --stage before` (if dev server is up) for visual regression.")
    print(f"{'3' if not (has_visual_diff or has_responsive) else '4'}. Score each of the 4 sections above (A, B, C, D) mentally.")
    print(f"{'4' if not (has_visual_diff or has_responsive) else '5'}. Sum them for a total (0-100).")
    print(f"{'5' if not (has_visual_diff or has_responsive) else '6'}. Store your score:  uidetox review --score <N>")
    print(f"{'6' if not (has_visual_diff or has_responsive) else '7'}. For any issues found, queue them:")
    print('   uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
    print(f"{'7' if not (has_visual_diff or has_responsive) else '8'}. Then run: uidetox status")
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("After scoring, run `uidetox review --score <N>` then `uidetox status`.")
    print("DO NOT STOP. Continue the autonomous loop.")


def _store_subjective_score(score: int):
    """Store the LLM's subjective design score."""
    ensure_uidetox_dir()
    state = load_state()

    # Clamp to 0-100
    score = max(0, min(100, score))

    state.setdefault("subjective", {})
    state["subjective"]["score"] = score

    # Keep history of subjective scores for progression tracking (capped at 50)
    history = state["subjective"].setdefault("history", [])
    from uidetox.utils import now_iso
    history.append({"score": score, "timestamp": now_iso()})
    # Prevent unbounded growth — keep only the most recent 50 entries
    state["subjective"]["history"] = history[-50:]

    save_state(state)

    print(f"✅ Subjective design score recorded: {score}/100")
    print()

    # Show breakdown hint
    if score >= 86:
        print("   Excellent — minimal slop detected by LLM review.")
    elif score >= 71:
        print("   Good — some areas need polish. Check issues queue.")
    elif score >= 51:
        print("   Moderate — AI fingerprints still visible. Focus on identity and consistency.")
    elif score >= 31:
        print("   Below average — significant slop remains. Deep work needed.")
    else:
        print("   Heavy slop — major redesign likely needed.")

    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("Run `uidetox status` NOW to see the blended Design Score.")
    print("DO NOT STOP. The loop continues automatically.")
