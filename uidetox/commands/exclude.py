"""Exclude command: add paths to the exclusion list."""

import argparse
from uidetox.state import load_config, save_config

def run(args: argparse.Namespace):
    config = load_config()
    excludes = config.setdefault("exclude", [])
    
    path = args.path
    if path in excludes:
        print(f"'{path}' is already excluded.")
        return
    
    excludes.append(path)
    save_config(config)
    print(f"Excluded '{path}'. Current exclusions: {', '.join(excludes)}")
