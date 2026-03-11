"""History command: view run history and score progression."""

import argparse
from uidetox.history import load_run_history, compare_runs


def run(args: argparse.Namespace):
    show_full = getattr(args, "full", False)

    runs = compare_runs()
    if not runs:
        print("No run history found. Run 'uidetox scan' to create your first snapshot.")
        return

    print("╔══════════════════════════════════════╗")
    print("║       UIdetox Run History            ║")
    print("╚══════════════════════════════════════╝")
    print()
    print(f"  {'#':>3s}  {'Trigger':>8s}  {'Score':>6s}  {'Pending':>8s}  {'Resolved':>9s}  Timestamp")
    print(f"  {'─'*3}  {'─'*8}  {'─'*6}  {'─'*8}  {'─'*9}  {'─'*20}")

    for i, r in enumerate(runs, 1):
        ts = r.get("timestamp", "")[:19]
        trigger = r.get("trigger", "?")
        score = r.get("score", 0)

        # Score trend indicator
        if i > 1:
            prev_score = runs[i - 2].get("score", 0)
            if score > prev_score:
                trend = "↑"
            elif score < prev_score:
                trend = "↓"
            else:
                trend = "─"
        else:
            trend = " "

        print(f"  {i:3d}  {trigger:>8s}  {score:4d}{trend:2s}  {r.get('pending', 0):8d}  {r.get('resolved', 0):9d}  {ts}")

    print(f"\n  Total runs: {len(runs)}")

    # Score progression bar
    if len(runs) >= 2:
        first = runs[0].get("score", 0)
        last = runs[-1].get("score", 0)
        delta = last - first
        direction = "📈" if delta > 0 else "📉" if delta < 0 else "➡️"
        print(f"  Progression: {first} → {last} ({'+' if delta >= 0 else ''}{delta}) {direction}")
