"""Add issue command."""

import argparse
import fnmatch
import hashlib
import sys
import uuid

from uidetox.findings import Finding
from uidetox.state import add_issue, load_config

_MAX_FILE_LEN = 300
_MAX_ISSUE_LEN = 500


def _is_suppressed(file_path: str, description: str, patterns: list[str]) -> bool:
    """Check if this issue matches any active suppress pattern."""
    for pattern in patterns:
        if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(
            file_path, f"*{pattern}*"
        ):
            return True
        if fnmatch.fnmatch(description, pattern) or fnmatch.fnmatch(
            description, f"*{pattern}*"
        ):
            return True
        if (
            pattern.lower() in file_path.lower()
            or pattern.lower() in description.lower()
        ):
            return True
    return False


def _manual_detector_id(file_path: str, issue: str, fix_command: str) -> str:
    identity = "\0".join(
        (
            file_path.strip().replace("\\", "/"),
            " ".join(issue.split()),
            " ".join(fix_command.split()),
        )
    )
    return f"manual-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"


def run(args: argparse.Namespace):
    # Validate required fields are non-empty
    if not args.file or not args.file.strip():
        print("Error: --file cannot be empty.", file=sys.stderr)
        sys.exit(1)
    if not args.issue or not args.issue.strip():
        print("Error: --issue cannot be empty.", file=sys.stderr)
        sys.exit(1)

    # Enforce length limits to keep state.json sane
    if len(args.file) > _MAX_FILE_LEN:
        print(
            f"Error: --file exceeds maximum length of {_MAX_FILE_LEN} characters.",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(args.issue) > _MAX_ISSUE_LEN:
        print(
            f"Error: --issue exceeds maximum length of {_MAX_ISSUE_LEN} characters.",
            file=sys.stderr,
        )
        sys.exit(1)

    config = load_config()
    ignore_patterns = config.get("ignore_patterns", [])

    if ignore_patterns and _is_suppressed(args.file, args.issue, ignore_patterns):
        print(
            f"Suppressed: [{args.tier}] {args.issue} in {args.file} (matches active ignore pattern)"
        )
        return

    issue_id = f"SCAN-{str(uuid.uuid4())[:6].upper()}"
    file_path = args.file.strip().replace("\\", "/")
    issue = " ".join(args.issue.split())
    fix_command = " ".join(str(args.fix_command or "").split())
    new_issue = Finding.create(
        detector_id=_manual_detector_id(file_path, issue, fix_command),
        category="quality",
        severity={"T1": "info", "T2": "warning", "T3": "error", "T4": "critical"}.get(
            args.tier, "warning"
        ),
        confidence=0.8,
        message=issue,
        provenance="manual",
        source_anchor={"path": file_path},
        suppression_key=issue_id,
        verifier={"kind": "manual"},
        legacy={"id": issue_id, "command": fix_command},
    )
    if not add_issue(new_issue):
        print(f"Issue already queued: [{args.tier}] {issue} in {file_path}")
        return
    print(f"Added issue {issue_id}: [{args.tier}] {issue} in {file_path}")
