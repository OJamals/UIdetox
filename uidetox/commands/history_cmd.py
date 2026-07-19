"""History command: view run history and score progression."""

import argparse
import json
from uidetox.history import load_run_history, compare_runs


def _safe_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _safe_int(value: object, default: int = 0) -> int:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return default


def _safe_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def run(args: argparse.Namespace):
    show_full = getattr(args, "full", False)
    use_json = getattr(args, "json", False)

    summary_runs = compare_runs()
    full_runs = load_run_history() if show_full else []
    runs = full_runs if show_full and use_json else summary_runs

    if not summary_runs:
        if use_json:
            print(json.dumps({"runs": [], "total": 0}))
        else:
            print(
                "No run history found. Run 'uidetox scan' to create your first snapshot."
            )
        return

    if use_json:
        payload = {
            "runs": runs,
            "total": len(runs),
            "first_score": summary_runs[0].get("score", 0) if summary_runs else 0,
            "latest_score": summary_runs[-1].get("score", 0) if summary_runs else 0,
            "delta": (
                summary_runs[-1].get("score", 0) - summary_runs[0].get("score", 0)
            )
            if len(summary_runs) >= 2
            else 0,
        }
        print(json.dumps(payload, indent=2))
        return

    print("╔══════════════════════════════════════╗")
    print("║       UIdetox Run History            ║")
    print("╚══════════════════════════════════════╝")
    print()
    print(
        f"  {'#':>3s}  {'Trigger':>8s}  {'Score':>6s}  {'Pending':>8s}  {'Resolved':>9s}  Timestamp"
    )
    print(f"  {'─' * 3}  {'─' * 8}  {'─' * 6}  {'─' * 8}  {'─' * 9}  {'─' * 20}")

    for i, r in enumerate(summary_runs, 1):
        ts = r.get("timestamp", "")[:19]
        trigger = r.get("trigger", "?")
        score = r.get("score", 0)

        # Score trend indicator
        if i > 1:
            prev_score = summary_runs[i - 2].get("score", 0)
            if score > prev_score:
                trend = "↑"
            elif score < prev_score:
                trend = "↓"
            else:
                trend = "─"
        else:
            trend = " "

        print(
            f"  {i:3d}  {trigger:>8s}  {score:4d}{trend:2s}  {r.get('pending', 0):8d}  {r.get('resolved', 0):9d}  {ts}"
        )

    print(f"\n  Total runs: {len(summary_runs)}")

    # Score progression bar
    if len(summary_runs) >= 2:
        first = summary_runs[0].get("score", 0)
        last = summary_runs[-1].get("score", 0)
        delta = last - first
        direction = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
        print(
            f"  Progression: {first} → {last} ({'+' if delta >= 0 else ''}{delta}) {direction}"
        )

    if show_full:
        print("\n  ─── Full Run Details ───")
        for i, run in enumerate(full_runs, 1):
            print(f"  [{i}] {_safe_text(run.get('_file'), '?')}")
            print(f"      Trigger        : {_safe_text(run.get('trigger'), '?')}")
            print(f"      Timestamp      : {_safe_text(run.get('timestamp'), '')[:19]}")
            print(f"      Design score   : {_safe_int(run.get('design_score'))}")
            print(f"      Objective      : {_safe_int(run.get('objective_score'))}")

            subjective_score = run.get("subjective_score")
            subjective_text = (
                str(_safe_int(subjective_score))
                if isinstance(subjective_score, (int, float))
                and not isinstance(subjective_score, bool)
                else "n/a"
            )
            print(f"      Subjective     : {subjective_text}")
            print(f"      Pending issues : {_safe_int(run.get('pending_issues'))}")
            print(f"      Resolved       : {_safe_int(run.get('resolved_issues'))}")
            print(f"      Total found    : {_safe_int(run.get('total_found'))}")
            print(f"      Scans run      : {_safe_int(run.get('scans_run'))}")
            print(f"      Issue entries  : {_safe_count(run.get('issues'))}")
            print(f"      Resolved entries: {_safe_count(run.get('resolved'))}")
            visual = run.get("visual_evidence")
            visual_state = (
                _safe_text(visual.get("state"), "unknown")
                if isinstance(visual, dict)
                else "unknown"
            )
            print(f"      Visual evidence: {visual_state}")
            print()
