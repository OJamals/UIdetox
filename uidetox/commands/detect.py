"""Detect command: discover project tooling and print results."""

import argparse
import json
from uidetox.tooling import detect_all
from uidetox.state import load_config, save_config

def run(args: argparse.Namespace):
    path = getattr(args, "path", ".")
    profile = detect_all(path)
    
    # Store detected tooling in config
    config = load_config()
    config["tooling"] = profile.to_dict()
    save_config(config)
    
    print("==============================")
    print(" UIdetox Tooling Detection")
    print("==============================")
    
    pm = profile.package_manager
    print(f"\n  Package Manager : {pm or 'not detected'}")
    
    if profile.typescript:
        print(f"  TypeScript      : {profile.typescript.config_file}")
        print(f"    check cmd     : {profile.typescript.run_cmd}")
    else:
        print("  TypeScript      : not detected")
    
    if profile.linter:
        print(f"  Linter          : {profile.linter.name} ({profile.linter.config_file})")
        print(f"    lint cmd      : {profile.linter.run_cmd}")
        if profile.linter.fix_cmd:
            print(f"    fix cmd       : {profile.linter.fix_cmd}")
    else:
        print("  Linter          : not detected")
    
    if profile.formatter:
        print(f"  Formatter       : {profile.formatter.name} ({profile.formatter.config_file})")
        print(f"    check cmd     : {profile.formatter.run_cmd}")
        if profile.formatter.fix_cmd:
            print(f"    fix cmd       : {profile.formatter.fix_cmd}")
    else:
        print("  Formatter       : not detected")
    
    if getattr(profile, "frontend", []):
        for f in profile.frontend:
            print(f"  Frontend        : {f.name} ({f.config_file})")
    
    if profile.backend:
        for b in profile.backend:
            print(f"  Backend         : {b.name} ({b.config_file})")
    
    if profile.database:
        for db in profile.database:
            print(f"  Database/ORM    : {db.name} ({db.config_file})")
    
    if profile.api:
        for api in profile.api:
            print(f"  API Layer       : {api.name} ({api.config_file})")
    
    print("\nTooling config saved to .uidetox/config.json")
