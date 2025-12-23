#!/usr/bin/env python3
"""
UE LevelSequence Creation Job Runner (Python)
Simple test: create an empty LevelSequence asset
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

def print_header(title: str):
    print("=" * 40)
    print(title)
    print("=" * 40)
    print()


def print_error(message: str):
    print(f"ERROR: {message}", file=sys.stderr)


def print_warning(message: str):
    print(f"WARNING: {message}")


def print_info(key: str, value: str):
    print(f"{key:14s} {value}")


def load_manifest(manifest_path: str) -> dict:
    if not os.path.exists(manifest_path):
        print_error(f"Manifest file not found: {manifest_path}")
        sys.exit(1)
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        return manifest
    except Exception as e:
        print_error(f"Cannot parse manifest: {e}")
        sys.exit(1)


def validate_manifest(manifest: dict) -> tuple[str, str]:
    job_id = manifest.get('job_id', 'unknown')
    job_type = manifest.get('job_type', 'unknown')
    
    if job_type != 'create_sequence':
        print_error(f"Invalid job type '{job_type}', expected 'create_sequence'")
        sys.exit(1)
    
    return job_id, job_type


def load_default_ue_config() -> dict:
    """Load default UE configuration from config file"""
    script_dir = Path(__file__).parent
    config_path = script_dir / 'config' / 'ue_config.json'
    
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"Cannot load default ue_config: {e}")
        return {}


def get_ue_config(manifest: dict) -> tuple[str, str]:
    """Extract UE configuration from manifest or default config file"""
    # Load default config first
    default_config = load_default_ue_config()
    
    # Merge with manifest config (manifest overrides default)
    manifest_config = manifest.get('ue_config', {})
    ue_config = {**default_config, **manifest_config}
    
    if not ue_config:
        print_error("No ue_config found in manifest or default config file")
        sys.exit(1)
    
    editor_path = ue_config.get('editor_path')
    if not editor_path:
        print_error("Missing 'editor_path' in ue_config")
        sys.exit(1)
    
    # Replace UnrealEditor.exe with UnrealEditor-Cmd.exe
    ue_editor = editor_path.replace('UnrealEditor.exe', 'UnrealEditor-Cmd.exe')
    
    project = ue_config.get('project_path')
    if not project:
        print_error("Missing 'project_path' in ue_config")
        sys.exit(1)
    
    return ue_editor, project


def validate_paths(ue_editor: str, project: str, worker: str):
    if not os.path.exists(ue_editor):
        print_error(f"UE Editor not found at: {ue_editor}")
        sys.exit(1)
    
    if not os.path.exists(project):
        print_error(f"Project not found at: {project}")
        sys.exit(1)
    
    if not os.path.exists(worker):
        print_error(f"Worker script not found at: {worker}")
        sys.exit(1)


def run_ue_job(ue_editor: str, project: str, manifest_path: str, worker: str) -> int:
    abs_manifest_path = os.path.abspath(manifest_path)
    abs_worker = os.path.abspath(worker)
    
    # UE-CMD mode: Use -ExecutePythonScript with manifest passed as environment variable
    os.environ['UE_MANIFEST_PATH'] = abs_manifest_path
    
    ue_args = [
        ue_editor,
        project,
        f'-ExecutePythonScript={abs_worker}',
        '-unattended',
        '-nopause',
        '-nosplash',
        '-NullRHI',
        '-buildmachine',
        '-NoSound',
        '-AllowStdOutLogVerbosity',
        '-stdout',
        '-FullStdOutLogOutput',
        '-log',
    ]
    
    print(f"Command: {' '.join(ue_args)}")
    print()
    print("-" * 40)
    
    try:
        result = subprocess.run(ue_args, check=False)
        
        print()
        print("-" * 40)
        
        if result.returncode == 0:
            print("Job completed successfully")
            return 0
        else:
            print_error(f"Job failed with exit code: {result.returncode}")
            return result.returncode
            
    except Exception as e:
        print_error(f"Failed to launch UE: {e}")
        return 1

# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='UE LevelSequence Creation Job Runner'
    )
    parser.add_argument(
        'manifest_path',
        help='Path to the job manifest JSON file'
    )
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    worker = str(script_dir / 'python' / 'worker_create_sequence.py')

    print_header("UE Create LevelSequence Test")
    
    manifest = load_manifest(args.manifest_path)
    job_id, job_type = validate_manifest(manifest)
    
    ue_editor, project = get_ue_config(manifest)
    
    print_info("Job ID:", job_id)
    print_info("Job Type:", job_type)
    print_info("Manifest:", args.manifest_path)
    print_info("UE Editor:", ue_editor)
    print_info("Project:", project)
    print()
    
    validate_paths(ue_editor, project, worker)
    
    print("Creating LevelSequence...")
    print()
    
    exit_code = run_ue_job(ue_editor, project, args.manifest_path, worker)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
