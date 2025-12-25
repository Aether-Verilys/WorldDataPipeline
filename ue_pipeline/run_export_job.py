#!/usr/bin/env python3
"""
UE Camera Export Job Executor (Python version)
Execute a camera export job using UnrealEditor.exe (GUI mode)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# ============================================================
# Helper Functions
# ============================================================

def load_ue_config():
    """Load UE configuration from config file"""
    script_dir = Path(__file__).parent
    config_path = script_dir / 'config' / 'ue_config.json'
    
    if not config_path.exists():
        print_colored(f"ERROR: UE config file not found: {config_path}", 'red')
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print_colored(f"ERROR: Failed to load UE config: {e}", 'red')
        sys.exit(1)


# ============================================================
# Helper Functions
# ============================================================

def print_colored(text, color):
    """Print colored text (simple version for cross-platform compatibility)"""
    colors = {
        'cyan': '\033[96m',
        'yellow': '\033[93m',
        'green': '\033[92m',
        'red': '\033[91m',
        'gray': '\033[90m',
        'reset': '\033[0m'
    }
    print(f"{colors.get(color, '')}{text}{colors.get('reset', '')}")


def print_header():
    """Print script header"""
    print_colored("=" * 40, 'cyan')
    print_colored("UE Camera Export Job Executor", 'cyan')
    print_colored("=" * 40, 'cyan')
    print()


def print_separator():
    """Print separator line"""
    print_colored("-" * 40, 'cyan')


# ============================================================
# Main Function
# ============================================================

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='Execute UE camera export job')
    parser.add_argument('manifest', help='Path to manifest JSON file')
    args = parser.parse_args()

    manifest_path = args.manifest

    print_header()

    # Load UE configuration from config file
    ue_config_global = load_ue_config()

    # Check manifest file
    if not os.path.isfile(manifest_path):
        print_colored(f"ERROR: Manifest file not found: {manifest_path}", 'red')
        return 1

    # Parse manifest to get job_id, job_type, and ue_config
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        job_id = manifest.get('job_id')
        job_type = manifest.get('job_type')

        if job_type != 'export':
            print_colored(f"ERROR: Invalid job type '{job_type}', expected 'export'", 'red')
            return 1

        # Read UE paths from manifest or use config file defaults
        ue_config = manifest.get('ue_config', {})
        ue_editor = ue_config.get('editor_path', ue_config_global.get('editor_path'))
        project = ue_config.get('project_path', ue_config_global.get('project_path'))

        if not manifest.get('ue_config'):
            print_colored("WARNING: No ue_config in manifest, using config file defaults", 'yellow')

        print_colored(f"Job ID:       {job_id}", 'yellow')
        print_colored(f"Job Type:     {job_type}", 'yellow')

    except json.JSONDecodeError as e:
        print_colored(f"ERROR: Cannot parse manifest: {e}", 'red')
        return 1
    except Exception as e:
        print_colored(f"ERROR: Failed to read manifest: {e}", 'red')
        return 1

    # Worker Export script path
    script_dir = Path(__file__).parent
    worker_export = script_dir / 'python' / 'worker_export.py'

    print_colored(f"Manifest:     {manifest_path}", 'yellow')
    print_colored(f"UE Editor:    {ue_editor}", 'yellow')
    print_colored(f"Project:      {project}", 'yellow')
    print()

    # Check required files
    if not os.path.isfile(ue_editor):
        print_colored(f"ERROR: UE Editor not found at: {ue_editor}", 'red')
        return 1

    if not os.path.isfile(project):
        print_colored(f"ERROR: Project not found at: {project}", 'red')
        return 1

    if not os.path.isfile(worker_export):
        print_colored(f"ERROR: Worker export script not found at: {worker_export}", 'red')
        return 1

    print_colored("Starting export job...", 'green')
    print()

    # Resolve absolute path for manifest
    abs_manifest_path = os.path.abspath(manifest_path)

    # Build python command for worker
    py_command = f'py "{worker_export}" --manifest="{abs_manifest_path}"'

    # Build UE launch arguments (GUI mode)
    ue_args = [
        str(project),
        f'-ExecCmds="{py_command}"',
        '-NoLoadingScreen',
        '-log'
    ]

    # Print command
    command_str = f'{ue_editor} {" ".join(ue_args)}'
    print_colored(f"Command: {command_str}", 'gray')
    print()
    print_separator()

    # Launch UE
    try:
        process = subprocess.run(
            [ue_editor] + ue_args,
            check=False
        )

        print()
        print_separator()

        if process.returncode == 0:
            print_colored("Export job completed successfully", 'green')
            return 0
        else:
            print_colored(f"Export job failed with exit code: {process.returncode}", 'red')
            return process.returncode

    except Exception as e:
        print_colored(f"ERROR: Failed to launch UE: {e}", 'red')
        return 1


if __name__ == '__main__':
    sys.exit(main())
