"""Subagent command: manage sub-agent sessions and generate stage prompts."""

import argparse
import json
from pathlib import Path
from uidetox.subagent import (
    STAGES,
    create_session,
    generate_stage_prompt,
    get_pending_reviews,
    get_session,
    list_sessions,
    record_result,
)


def run(args: argparse.Namespace):
    stage_prompt = getattr(args, "stage_prompt", None)
    list_all = getattr(args, "list", False)
    show_id = getattr(args, "show", None)
    record_id = getattr(args, "record", None)

    if stage_prompt:
        _handle_stage_prompt(stage_prompt, getattr(args, "parallel", 1))
    elif list_all:
        _handle_list()
    elif show_id:
        _handle_show(show_id)
    elif record_id:
        _handle_record(record_id, args)
    else:
        _handle_default()


def _handle_stage_prompt(stage: str, parallel: int):
    if stage not in STAGES:
        print(f"Unknown stage '{stage}'. Valid stages: {', '.join(STAGES)}")
        return

    prompts = generate_stage_prompt(stage, parallel)
    
    print(f"\n[ORCHESTRATOR] Generated {len(prompts)} parallel prompt(s) for the '{stage.upper()}' stage.\n")
    
    session_ids = []
    for i, prompt in enumerate(prompts):
        session_id = create_session(stage, prompt)
        session_ids.append(session_id)
        
        print(f"╔══════════════════════════════════════╗")
        print(f"║  Sub-Agent Session: {session_id:16s}  ║")
        print(f"╚══════════════════════════════════════╝")
        print(f"  Stage: {stage} (Shard {i+1}/{len(prompts)})")
        print(f"  Session stored in .uidetox/sessions/session_{session_id}/")
        print()
        print("━" * 60)
        print(prompt)
        print("━" * 60)
        print()

    print("[AUTONOMOUS LOOP SIGNAL]")
    if len(prompts) == 1:
        print(f"Execute the {stage.upper()} stage prompt above.")
        print(f"When done, run: uidetox subagent --record {session_ids[0]} --result-file result.json --confidence 0.92")
    else:
        print(f"Launch {len(prompts)} parallel subagents with distinct prompts above.")
        print(f"Each agent works only on its assigned shard (no conflicts).")
        print(f"Record sequentially when complete:")
        for sid in session_ids:
            print(f"  uidetox subagent --record {sid} --result-file result.json --confidence 0.92")
    print()
    print("DO NOT STOP. Execute the stage, record results, continue the loop.")


def _handle_list():
    sessions = list_sessions()
    if not sessions:
        print("No sub-agent sessions found.")
        return

    pending_reviews = get_pending_reviews()

    print("╔══════════════════════════════════════╗")
    print("║       Sub-Agent Sessions             ║")
    print("╚══════════════════════════════════════╝")
    for s in sessions:
        status = s.get("status", "pending")
        if status == "completed":
            status_icon = "✅"
        elif status == "completed_with_warnings":
            status_icon = "⚠️"
        elif status == "needs_human_review":
            status_icon = "🛑"
        else:
            status_icon = "⏳"
        confidence = s.get("confidence")
        confidence_text = f" | conf={confidence:.2f}" if isinstance(confidence, (float, int)) else ""
        print(f"  {status_icon} {s.get('session_id', '?'):8s} | {s.get('stage', '?'):12s} | {status}{confidence_text}")
    if pending_reviews:
        print(f"\n  Pending review requests: {len(pending_reviews)}")
    print(f"\n  Total: {len(sessions)} session(s)")


def _handle_show(session_id: str):
    session = get_session(session_id)
    if not session:
        print(f"Session '{session_id}' not found.")
        return

    meta = session.get("meta", {})
    print(f"Session: {meta.get('session_id')}")
    print(f"Stage:   {meta.get('stage')}")
    print(f"Status:  {meta.get('status')}")
    if meta.get("confidence") is not None:
        print(f"Conf.:   {meta.get('confidence')}")
    if meta.get("review_reason"):
        print(f"Review:  {meta.get('review_reason')}")
    print(f"Created: {meta.get('created_at')}")
    if meta.get("completed_at"):
        print(f"Done:    {meta.get('completed_at')}")
    if "result" in session:
        print(f"\nResult:")
        print(json.dumps(session["result"], indent=2)[:2000])


def _load_result_payload(result_file: str | None) -> dict:
    if not result_file:
        return {}
    payload = json.loads(Path(result_file).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Result file must contain a JSON object")
    return payload


def _handle_record(session_id: str, args: argparse.Namespace):
    note = getattr(args, "note", "") or "completed"
    try:
        result = _load_result_payload(getattr(args, "result_file", None))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"❌ Could not load result payload: {exc}")
        return

    result.setdefault("status", "completed")
    result["note"] = note or result.get("note", "completed")

    confidence = getattr(args, "confidence", None)
    if confidence is not None:
        result["confidence"] = max(0.0, min(1.0, confidence))

    verification = getattr(args, "verification", "")
    if verification:
        result["verification"] = verification

    success = record_result(session_id, result)
    if success:
        print(f"✅ Session {session_id} recorded as completed.")
        print()
        print("[AUTONOMOUS LOOP SIGNAL]")
        print("Session recorded. Run `uidetox status` then continue the fix loop.")
        print("DO NOT STOP. Proceed to `uidetox next` or the next stage.")
    else:
        print(f"❌ Session {session_id} not found.")


def _handle_default():
    print("UIdetox Sub-Agent Manager")
    print()
    print("Usage:")
    print("  uidetox subagent --stage-prompt <stage>  Generate a focused prompt for a stage")
    print("  uidetox subagent --list                  List all sessions")
    print("  uidetox subagent --show <session_id>     Show session details")
    print("  uidetox subagent --record <session_id>   Mark a session as completed")
    print("      Optional: --result-file result.json --confidence 0.91 --verification \"checks passed\"")
    print()
    print(f"Available stages: {', '.join(STAGES)}")
