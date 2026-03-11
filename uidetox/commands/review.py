"""Review command."""

import argparse

def run(args: argparse.Namespace):
    print("==============================")
    print(" UIdetox Subjective Review")
    print("==============================")
    print("Please evaluate the subjective design quality of the project.")
    print("Check against the 13 sections in SKILL.md, particularly:")
    print("  - The AI Slop Test (Does it look AI-generated?)")
    print("  - Typography & Color Usage")
    print("  - Materiality & Surfaces")
    print("  - Motion & Interaction")
    
    print("\n[AGENT INSTRUCTION]")
    print("Assign a Design Score from 1 to 100.")
    print("Give specific reasons for deductions and suggest areas for improvement.")
    print("If there are slop violations, add them to the queue using:")
    print("  uidetox add-issue --file <path> --tier <T1-T4> --issue <reason> --fix-command <fix>")
