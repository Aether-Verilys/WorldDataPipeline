#!/usr/bin/env python
"""
Copy Scene Assets Wrapper Script
A Python wrapper for copy_scene_assets.py that handles argument parsing and logging.
"""

import argparse
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path


def main():
    # Get script directory (wrapper is in ue_pipeline/python/pre_copy/)
    script_dir = Path(__file__).parent.resolve()
    # Python script is in parent directory (ue_pipeline/python/)
    python_script = script_dir.parent / "copy_scene_assets.py"
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Copy scene assets with configuration file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python copy_scene_assets_wrapper.py -c config/world_01_scene_config.json
  python copy_scene_assets_wrapper.py --config config/world_01_scene_config.json --dry-run
  python copy_scene_assets_wrapper.py -c config.json --list --batch-size 20
        """
    )
    
    parser.add_argument(
        '-c', '--config',
        type=str,
        required=True,
        help='Configuration JSON file path'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making actual changes'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List assets to be processed'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of assets to process per batch (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Check if Python script exists
    if not python_script.exists():
        print(f"Error: Python script not found: {python_script}", file=sys.stderr)
        return 1
    
    # Process config path
    config_path = Path(args.config.strip('"').strip("'"))
    
    # If not absolute path, resolve relative to script directory
    if not config_path.is_absolute():
        config_path = script_dir / config_path
    
    # Normalize path
    config_path = config_path.resolve()
    
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print("\nPlease provide a valid configuration JSON file.")
        print("Usage:")
        print(f"  python {Path(__file__).name} --config path/to/config.json")
        return 1
    
    # Build command arguments
    cmd_args = [
        sys.executable,
        str(python_script),
        "--config", str(config_path),
        "--batch-size", str(args.batch_size)
    ]
    
    if args.dry_run:
        cmd_args.append("--dry-run")
    
    if args.list:
        cmd_args.append("--list")
    
    # Create log directory (ue_pipeline/logs)
    log_dir = script_dir.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"world_01_scene_assets_{timestamp}.log"
    
    # Display information
    print(f"Config file: {config_path}")
    print(f"Batch size: {args.batch_size} assets per batch")
    print(f"Log file: {log_file}")
    
    # Execute the Python script and capture output
    try:
        with open(log_file, 'w', encoding='utf-8') as log:
            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Stream output to both console and log file
            for line in process.stdout:
                print(line, end='')
                log.write(line)
            
            process.wait()
            exit_code = process.returncode
            
    except Exception as e:
        print(f"\nError executing script: {e}", file=sys.stderr)
        print(f"Log saved to: {log_file}")
        return 1
    
    # Check exit code and display result
    if exit_code != 0:
        print("\nScript execution failed", file=sys.stderr)
        print(f"Log saved to: {log_file}")
        return exit_code
    
    print("\nScript execution completed")
    print(f"Log saved to: {log_file}")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nScript interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        sys.exit(1)
