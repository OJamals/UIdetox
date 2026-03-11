"""Setup command."""

import argparse
from uidetox.state import save_config, ensure_uidetox_dir, load_config

def run(args: argparse.Namespace):
    print("==============================")
    print(" UIdetox Setup")
    print("==============================")
    
    ensure_uidetox_dir()
    config = load_config()
    
    # Check if --auto-commit was passed via CLI
    if hasattr(args, 'auto_commit') and args.auto_commit:
        config['auto_commit'] = True
        print("\n⚙️  Auto-commit enabled via flag.")
    else:
        # Interactive prompt if not set
        current_ac = config.get('auto_commit', False)
        print(f"\nCurrent auto_commit status: {current_ac}")
        ans = input("Enable automated git commits for each resolved issue? (y/n): ").strip().lower()
        if ans == 'y':
            config['auto_commit'] = True
        elif ans == 'n':
            config['auto_commit'] = False

    print("\nCurrent configuration:")
    print(f"  DESIGN_VARIANCE:  {config.get('DESIGN_VARIANCE', 8)}")
    print(f"  MOTION_INTENSITY: {config.get('MOTION_INTENSITY', 6)}")
    print(f"  VISUAL_DENSITY:   {config.get('VISUAL_DENSITY', 4)}")
    print(f"  AUTO_COMMIT:      {config.get('auto_commit', False)}")
    
    print("\n[AGENT INSTRUCTION]")
    print("If the user provided specific requirements for Variance/Motion/Density, update `.uidetox/config.json`.")
    print("Otherwise, keep optimal defaults (8, 6, 4).")
    print("Proceed to run `uidetox scan` to begin detoxifying the frontend.")
    
    # Ensures config exists if it didn't
    save_config(config)
