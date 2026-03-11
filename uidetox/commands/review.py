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

    print("╔══════════════════════════════╗")
    print("║  UIdetox Subjective Review   ║")
    print("╚══════════════════════════════╝")
    print()
    print("Perform a deep, subjective UX quality review of this project.")
    print("Evaluate the OVERALL design — not individual issues, but the holistic feel.")
    print()
    print("━━━ Evaluation Dimensions ━━━")
    print()
    print("  1. CONSISTENCY (0-25)")
    print("     → Is the design language consistent across all pages/components?")
    print("     → Are colors, typography, spacing, and components unified?")
    print("     → Does it feel like one designer made it, or a patchwork?")
    print()
    print("  2. COHESION (0-25)")
    print("     → Does the visual hierarchy guide the eye correctly?")
    print("     → Do elements work together to tell a coherent story?")
    print("     → Is there a clear design system behind the surface?")
    print()
    print("  3. CRAFT (0-25)")
    print("     → Are micro-interactions polished (hover, focus, transitions)?")
    print("     → Are edge cases handled (empty, error, loading states)?")
    print("     → Does it pass the 'squint test' — clear hierarchy at a glance?")
    print()
    print("  4. IDENTITY (0-25)")
    print("     → Does this feel designed, not generated?")
    print("     → Would someone ask 'what tool made this?' (bad) or 'how was this made?' (good)")
    print("     → Are there intentional design choices that surprise or delight?")
    print("     → Does it avoid ALL AI slop fingerprints from SKILL.md?")
    print()
    print("━━━ Scoring Guide ━━━")
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
    print("2. Evaluate each of the 4 dimensions above (Consistency, Cohesion, Craft, Identity).")
    print("3. Sum the 4 dimension scores to get a total (0-100).")
    print("4. Store your score:  uidetox review --score <N>")
    print("5. For any issues found, queue them:")
    print('   uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
    print("6. Then run: uidetox status")


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
