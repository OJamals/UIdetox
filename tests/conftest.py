from __future__ import annotations

import sys
from pathlib import Path


# Ensure tests always import the in-repo package, even when fixtures chdir().
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)
