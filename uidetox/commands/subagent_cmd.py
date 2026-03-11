"""Subagent command: manage sub-agent sessions and generate stage prompts."""

import argparse
import json
from uidetox.subagent import (
    STAGES,
    create_session,
    generate_stage_prompt,
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

    print("[AGENT INSTRUCTION]")
    if len(prompts) == 1:
        print(f"Execute the {stage.upper()} stage prompt above.")
        print(f"When done, run: uidetox subagent --record {session_ids[0]}")
    else:
        print(f"Launch {len(prompts)} parallel subagents and feed each one a distinct prompt from above.")
        print(f"Each agent MUST only work on its assigned shard to prevent merge conflicts.")
        print(f"When all agents are done, record them sequentially:")
        for sid in session_ids:
            print(f"  uidetox subagent --record {sid}")


def _handle_list():
    sessions = list_sessions()
    if not sessions:
        print("No sub-agent sessions found.")
        return

    print("╔══════════════════════════════════════╗")
    print("║       Sub-Agent Sessions             ║")
    print("╚══════════════════════════════════════╝")
    for s in sessions:
        status_icon = "✅" if s.get("status") == "completed" else "⏳"
        print(f"  {status_icon} {s.get('session_id', '?'):8s} | {s.get('stage', '?'):12s} | {s.get('status', '?')}")
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
    print(f"Created: {meta.get('created_at')}")
    if meta.get("completed_at"):
        print(f"Done:    {meta.get('completed_at')}")
    if "result" in session:
        print(f"\nResult:")
        print(json.dumps(session["result"], indent=2)[:2000])


def _handle_record(session_id: str, args: argparse.Namespace):
    note = getattr(args, "note", "") or "completed"
    result = {
        "status": "completed",
        "note": note,
    }
    success = record_result(session_id, result)
    if success:
        print(f"✅ Session {session_id} recorded as completed.")
        print("\n[AGENT LOOP SIGNAL]")
        print("Run `uidetox status` to check progress, or proceed to the next stage.")
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
    print()
    print(f"Available stages: {', '.join(STAGES)}")
