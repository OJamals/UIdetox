"""Review command: captures LLM subjective UX quality assessment."""

import argparse
import json
from uidetox.state import load_state, save_state, ensure_uidetox_dir


def run(args: argparse.Namespace):
    score = getattr(args, "score", None)

    if score is not None:
        _store_subjective_score(score)
        return

    parallel = getattr(args, "parallel", 1) or 1

    # Parallel domain-sharded review via subagent infrastructure
    if parallel > 1:
        _run_parallel_review(parallel)
        return

    from uidetox.state import get_uidetox_dir
    snapshot = get_uidetox_dir() / "snapshots" / "latest.png"
    has_snapshot = snapshot.exists()

    print("+" + "=" * 58 + "+")
    print("| UIdetox Subjective Review                                |")
    print("+" + "=" * 58 + "+")
    print()
    print("  ──── PRE-REVIEW ANALYSIS (MANDATORY — do ALL before scoring) ────")
    print()
    print("  1. npx gitnexus analyze             — refresh codebase index")
    print('  2. npx gitnexus query "frontend components"  — map component graph')
    print('  3. npx gitnexus query "design patterns"      — find design system patterns')
    print('  4. npx gitnexus query "styling color theme"  — discover color/theme usage')
    print('  5. npx gitnexus query "animation transition" — find motion patterns')
    print('  6. npx gitnexus query "error loading state"  — find state handling')
    print("  7. uidetox check --fix               — ensure code is clean")
    print("  8. uidetox status                    — see current score and queue")
    print()
    print("  ────────────────────────────────────────────────────────────")
    print()
    print("  Perform a deep, subjective quality review of this project.")
    print("  Evaluate the OVERALL design — not individual issues, but the holistic feel.")
    print()
    print("  NOTE: Subjective score carries 70% weight in the blended Design Score.")
    print()
    print("  ──── SCORING PROTOCOL (follow this exact process) ────")
    print("  1. Start each domain at max score")
    print("  2. Walk through every checklist item — mark pass or fail")
    print("  3. Measure every hard threshold — cite actual values found")
    print("  4. Apply every matching automatic deduction")
    print("  5. Domain score = max - sum(deductions), clamped to [0, max]")
    print("  6. Show deduction math in justification")
    print()

    # ── Print the full reference-driven rubric from REVIEW_DOMAINS ──
    from uidetox.subagent import REVIEW_DOMAINS, SCORED_REVIEW_DOMAINS, PERFECTION_GATE

    total_max = sum(d.get("max_score", 0) for d in SCORED_REVIEW_DOMAINS)

    # Group scored domains by rubric section letter for display
    section_a = [d for d in SCORED_REVIEW_DOMAINS if d["rubric"].startswith("A.")]
    section_b = [d for d in SCORED_REVIEW_DOMAINS if d["rubric"].startswith("B.")]
    section_c = [d for d in SCORED_REVIEW_DOMAINS if d["rubric"].startswith("C.")]
    section_d = [d for d in SCORED_REVIEW_DOMAINS if d["rubric"].startswith("D.")]

    section_groups = [
        ("A. VISUAL DESIGN & AESTHETICS", section_a),
        ("B. DESIGN SYSTEM & COHERENCE", section_b),
        ("C. INTERACTION & CRAFT", section_c),
        ("D. ARCHITECTURE & CODE QUALITY", section_d),
    ]

    for section_label, domains_in_section in section_groups:
        section_total = sum(d.get("max_score", 0) for d in domains_in_section)
        print(f"  {section_label} (0-{section_total})")
        print("  " + "-" * 50)
        print()
        for domain in domains_in_section:
            max_s = domain.get("max_score", 0)
            print(f"    {domain['label']} (0-{max_s})")
            print(f"      Focus: {domain['focus']}")
            # Print checklist
            checklist = domain.get("checklist", [])
            if checklist:
                print("      Checklist:")
                for item in checklist[:6]:  # Show top 6 for space
                    print(f"        - {item}")
                if len(checklist) > 6:
                    print(f"        ... +{len(checklist) - 6} more (see reference files)")
            # Print key thresholds
            thresholds = domain.get("thresholds", {})
            if thresholds:
                print("      Thresholds:")
                for k, v in list(thresholds.items())[:4]:
                    print(f"        - {k}: {v}")
            # Print deductions
            deductions = domain.get("deductions", [])
            if deductions:
                print("      Deductions:")
                for ded in deductions[:4]:  # Show top 4
                    print(f"        - {ded}")
                if len(deductions) > 4:
                    print(f"        ... +{len(deductions) - 4} more")
            print()
    # ---- Scoring Guide ----
    print("  " + "=" * 50)
    print(f"  SCORING GUIDE (sum all domains = 0-{total_max}, normalize to 0-100)")
    print("  " + "=" * 50)
    print()
    print("     0-20  : Critical failures — AI slop everywhere, no design intention")
    print("    21-40  : Heavy AI fingerprints, generic template, multiple anti-patterns")
    print("    41-55  : Some design effort but obvious AI tells remain")
    print("    56-70  : Competent design with residual slop — checklist failures remain")
    print("    71-80  : Good design, mostly clean — some deductions still apply")
    print("    81-88  : Very good, intentional design — minor checklist gaps")
    print("    89-93  : Excellent — nearly all checklists pass, ≤2 minor deductions")
    print("    94-97  : Near-perfect — ALL checklists pass, ZERO pending issues")
    print("    98-100 : Flawless — zero deductions, perfection gate fully satisfied")
    print()
    print("  ⚠️  SCORING INTEGRITY RULES:")
    print("    • A diminishing-returns curve compresses your raw score above 60.")
    print("      Raw 80 → effective ~68. Raw 90 → effective ~81. Only 100 → 100.")
    print("    • Pending issues in the queue AUTO-DEDUCT from your effective score.")
    print("    • If ANY issues remain in the queue, effective subjective is CAPPED at 80.")
    print("    • If objective score < 95, effective subjective is CAPPED at 75.")
    print("    • You CANNOT reach 90+ blended without: empty queue, 100% objective,")
    print("      AND a raw subjective score of ~98+.")
    print("    • 14 scored domains across 138 total points — more areas to fail in.")
    print("    • Do NOT inflate your score — the curve will expose it.")
    print()

    # ── Perfection Gate display ──
    if PERFECTION_GATE:
        print("  " + "=" * 50)
        print("  PERFECTION GATE (must pass ALL to exceed 85)")
        print("  " + "=" * 50)
        print()
        for item in PERFECTION_GATE.get("checklist", []):
            print(f"    □ {item}")
        print()
        for ded in PERFECTION_GATE.get("deductions", []):
            print(f"    ⚠️  {ded}")
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
    print()
    print("  PRE-REVIEW (MANDATORY):")
    print("  1. Run `npx gitnexus query \"frontend components\"` — map the component graph")
    print("  2. Run `npx gitnexus query \"design patterns\"` — find design system patterns")
    print("  3. Run `uidetox check --fix` — ensure code is clean (tsc → lint → format)")
    print()
    print("  REVIEW:")
    step = 4
    print(f"  {step}. Read every reference file (reference/*.md) for scoring criteria.")
    step += 1
    print(f"  {step}. Read every frontend file in the project.")
    step += 1
    if has_visual_diff or has_responsive:
        print(f"  {step}. Review the visual snapshots above (before/after + responsive).")
        step += 1
        print(f"  {step}. Factor visual quality into your scoring.")
        step += 1
    else:
        print(f"  {step}. Optional: Run `uidetox capture --stage before` (if dev server is up).")
        step += 1
    print(f"  {step}. For each domain: walk checklist, measure thresholds, apply deductions.")
    step += 1
    print(f"  {step}. Domain score = max - deductions (clamped to 0). Show math.")
    step += 1
    print(f"  {step}. Sum all domain scores, normalize to 0-100.")
    step += 1
    print()
    print("  POST-REVIEW:")
    print(f"  {step}. Run `uidetox check --fix` — verify code is still clean after any changes")
    step += 1
    print(f"  {step}. Store your score:  uidetox review --score <N>")
    step += 1
    print(f"  {step}. For any issues found, queue them:")
    print('     uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
    step += 1
    print(f"  {step}. Then run: uidetox loop")
    print()
    print("  NOTE: Subjective score = 70% of final blended score. Be thorough.")
    print("        Use checklist/threshold/deduction protocol for consistency.")
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("After scoring with `uidetox review --score <N>`, run `uidetox loop` immediately.")
    print("DO NOT STOP. DO NOT run individual commands — the loop handles everything.")


def _store_subjective_score(score: int):
    """Store the LLM's subjective design score.

    Accepts raw 0-100 score (already normalized from domain rubric).
    Records score, tracks history, and provides domain-aware feedback.
    """
    from uidetox.utils import now_iso, compute_design_score

    ensure_uidetox_dir()
    state = load_state()

    # Clamp to 0-100
    score = max(0, min(100, score))
    reviewed_at = now_iso()

    state.setdefault("subjective", {})
    state["subjective"]["score"] = score
    state["subjective"]["reviewed_at"] = reviewed_at

    # Keep history of subjective scores for progression tracking (capped at 50)
    history = state["subjective"].setdefault("history", [])
    history.append({"score": score, "timestamp": reviewed_at})

    # Compute score snapshot with centralized scoring logic
    scores_snapshot = compute_design_score(state)
    pending = state.get("issues", [])
    effective = scores_snapshot.get("effective_subjective")
    if effective is None:
        effective = 0
    blended = scores_snapshot["blended_score"]
    obj = scores_snapshot.get("objective_score")
    details = scores_snapshot.get("effective_subjective_details") or {}

    history[-1]["effective_score"] = effective
    history[-1]["blended_score"] = blended
    if obj is not None:
        history[-1]["objective_score"] = obj

    # Prevent unbounded growth — keep only the most recent 50 entries
    state["subjective"]["history"] = history[-50:]
    state["subjective"]["effective_score"] = effective
    state["subjective"]["effective_details"] = details

    save_state(state)

    print(f"✅ Subjective design score recorded: {score}/100 (raw)")
    print(f"   Effective (after curve + penalties): {effective}/100")
    if effective < score:
        print(f"   Δ compression: -{score - effective} pts (diminishing-returns curve")
        pending_penalty = details.get("pending_penalty")
        if pending and pending_penalty:
            print(f"     + pending-issue penalty ({pending_penalty} pts)")
        for cap in details.get("caps_applied", []):
            if cap == "pending_issue_cap":
                print("     + pending-issue cap [effective <= 80]")
            elif cap == "critical_issue_cap":
                print("     + critical-issue cap [T1 present -> effective <= 70]")
            elif cap == "objective_cross_gate" and obj is not None:
                print(f"     + objective cross-gate cap [obj={obj} < 95 -> effective <= 75]")
        print("   )")
    print(f"   Blended Design Score: {blended}/100")
    print()

    # Domain-aware feedback with checklist/threshold context
    if effective >= 95:
        print("   Outstanding — near-perfect across all domains. Verify with uidetox status.")
    elif effective >= 86:
        print("   Excellent — nearly all domain checklists pass, minimal deductions.")
    elif effective >= 71:
        print("   Good — some checklist failures remain. Review deductions applied.")
        print("   Focus areas: check which domains scored lowest and target those.")
    elif effective >= 51:
        print("   Moderate — multiple threshold violations and AI fingerprints detected.")
        print("   Priority: fix identity/consistency deductions first (highest impact).")
    elif effective >= 31:
        print("   Below average — significant deductions across multiple domains.")
        print("   Action: run `uidetox review --parallel 10` for detailed domain breakdown.")
    else:
        print("   Heavy slop — critical failures in most domains.")
        print("   Action: address typography + color + identity deductions first.")

    # Warn when raw vs effective gap is large
    if score >= 90 and effective < 85:
        print()
        print("   ⚠️  Your raw score is high but the effective score is low.")
        print("   This means pending issues or the objective cross-gate are dragging it down.")
        print("   Clear the queue and re-scan before expecting 95+ blended.")

    # Show progression trend if history exists
    if len(history) >= 2:
        prev = history[-2]["score"]
        delta = score - prev
        if delta > 0:
            print(f"\n   📈 Trend: +{delta} pts raw ({prev} → {score})")
        elif delta < 0:
            print(f"\n   📉 Trend: {delta} pts raw ({prev} → {score})")
        else:
            print(f"\n   ➡️  No change from previous raw score ({prev})")

    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("Run `uidetox loop` NOW to continue the autonomous cycle.")
    print("DO NOT STOP. DO NOT run individual commands — the loop handles everything.")


def _run_parallel_review(parallel: int):
    """Generate parallel domain-sharded review subagent prompts."""
    from uidetox.subagent import generate_stage_prompt, SCORED_REVIEW_DOMAINS, PERFECTION_GATE

    total_max = sum(d.get("max_score", 0) for d in SCORED_REVIEW_DOMAINS)

    print("+" + "=" * 58 + "+")
    print("| UIdetox Parallel Subjective Review                       |")
    print("+" + "=" * 58 + "+")
    print()
    print(f"  Spawning {min(parallel, len(SCORED_REVIEW_DOMAINS))} parallel review subagents")
    print(f"  across {len(SCORED_REVIEW_DOMAINS)} scored domains ({total_max} total pts).")
    if PERFECTION_GATE:
        gate_checks = len(PERFECTION_GATE.get("checklist", []))
        print(f"  + Perfection Gate ({gate_checks} cross-cutting conditions) injected into every shard.")
    print("  Subjective score = 70% of final blended Design Score.")
    print()
    print("  Scoring Protocol: checklist → thresholds → deductions → score")
    print()

    prompts = generate_stage_prompt("review", parallel=parallel)

    print(f"  Generated {len(prompts)} domain review prompt(s):")
    print()
    for idx, domain in enumerate(SCORED_REVIEW_DOMAINS[:len(prompts)]):
        label = domain.get("label", f"Domain {idx + 1}")
        rubric = domain.get("rubric", "")
        max_s = domain.get("max_score", 0)
        n_checks = len(domain.get("checklist", []))
        n_deds = len(domain.get("deductions", []))
        print(f"    Shard {idx + 1}: {label} ({max_s} pts)")
        print(f"             {rubric}")
        print(f"             {n_checks} checklist items, {n_deds} deduction rules")
    print()

    for idx, prompt in enumerate(prompts):
        print("=" * 60)
        print(f"  REVIEW SUBAGENT PROMPT {idx + 1}/{len(prompts)}")
        print("=" * 60)
        print(prompt)
        print()

    print("─" * 60)
    print("[AGENT INSTRUCTION]")
    print()
    print("  0. Run `npx gitnexus analyze` — refresh codebase index")
    print("  1. Spawn the subagent prompts above in PARALLEL")
    print("     (one subagent per domain shard)")
    print("  2. Each subagent follows the scoring protocol:")
    print("     checklist items → threshold measurements → automatic deductions")
    print(f"  3. After ALL subagents complete, SUM partial scores (0-{total_max} raw)")
    print(f"  4. Normalize: final_score = round(sum / {total_max} × 100)")
    print("  5. Run `uidetox check --fix` — verify code is clean (tsc → lint → format)")
    print("  6. Record the normalized score: `uidetox review --score <NORMALIZED>`")
    print("  7. Run `uidetox loop` to continue the autonomous cycle")
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("After scoring, run `uidetox loop` immediately. DO NOT STOP.")
    print("DO NOT run individual commands — the loop handles everything.")
