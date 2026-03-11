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
    print("[AGENT INSTRUCTION]")
    print("1. Read every frontend file in the project.")
    print("2. Optional: Run `uidetox capture` (if dev server is up) for visual regression.")
    print("3. Score each of the 4 sections above (A, B, C, D) mentally.")
    print("4. Sum them for a total (0-100).")
    print("5. Store your score:  uidetox review --score <N>")
    print("6. For any issues found, queue them:")
    print('   uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
    print("7. Then run: uidetox status")


def _store_subjective_score(score: int):
    """Store the LLM's subjective design score."""
    ensure_uidetox_dir()
    state = load_state()

    # Clamp to 0-100
    score = max(0, min(100, score))

    state.setdefault("subjective", {})
    state["subjective"]["score"] = score

    # Keep history of subjective scores for progression tracking
    history = state["subjective"].setdefault("history", [])
    from uidetox.utils import now_iso
    history.append({"score": score, "timestamp": now_iso()})

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
    print("[AGENT LOOP SIGNAL]")
    print("Run `uidetox status` to see the blended Design Score.")
