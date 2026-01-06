#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


script_dir = Path(__file__).parent
repo_root = script_dir.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ue_pipeline.python.logger import logger


def load_manifest(manifest_path: str) -> dict:
    if not os.path.exists(manifest_path):
        logger.error(f"Manifest file not found: {manifest_path}")
        sys.exit(1)
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        return manifest
    except Exception as e:
        logger.error(f"Cannot parse manifest: {e}")
        sys.exit(1)


def validate_manifest(manifest: dict) -> tuple[str, str]:
    job_id = manifest.get('job_id', 'unknown')
    job_type = manifest.get('job_type', 'unknown')
    
    if job_type != 'create_sequence':
        logger.error(f"Invalid job type '{job_type}', expected 'create_sequence'")
        sys.exit(1)
    
    return job_id, job_type


def load_default_ue_config() -> dict:
    """Load default UE configuration from config file"""
    script_dir = Path(__file__).parent
    env_config_path = os.environ.get('UE_CONFIG_PATH')
    config_path = Path(env_config_path) if env_config_path else (script_dir / 'config' / 'ue_config.json')
    
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Cannot load default ue_config: {e}")
        return {}


def get_ue_config(manifest: dict) -> tuple[str, str, dict]:
    """Extract and merge UE configuration, return editor, project, and full config"""
    # Load default config first
    default_config = load_default_ue_config()
    
    # Merge with manifest config (manifest overrides default)
    manifest_config = manifest.get('ue_config', {})
    ue_config = {**default_config, **manifest_config}
    
    if not ue_config:
        logger.error("No ue_config found in manifest or default config file")
        sys.exit(1)
    
    editor_path = ue_config.get('editor_path')
    if not editor_path:
        logger.error("Missing 'editor_path' in ue_config")
        sys.exit(1)
    
    # Replace UnrealEditor.exe with UnrealEditor-Cmd.exe
    ue_editor = editor_path.replace('UnrealEditor.exe', 'UnrealEditor-Cmd.exe')
    
    project = ue_config.get('project_path')
    if not project:
        logger.error("Missing 'project_path' in ue_config")
        sys.exit(1)
    
    # Handle "default" value - use ue_template project
    if project == "default":
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project = os.path.join(script_dir, "ue_template", "project", "WorldData.uproject")
        logger.info(f"Using default project: {project}")
    
    return ue_editor, project, ue_config


def validate_paths(ue_editor: str, project: str, worker: str):
    if not os.path.exists(ue_editor):
        logger.error(f"UE Editor not found at: {ue_editor}")
        sys.exit(1)
    
    if not os.path.exists(project):
        logger.error(f"Project not found at: {project}")
        sys.exit(1)
    
    if not os.path.exists(worker):
        logger.error(f"Worker script not found at: {worker}")
        sys.exit(1)


def run_ue_job(ue_editor: str, project: str, manifest_path: str, worker: str) -> int:
    abs_manifest_path = os.path.abspath(manifest_path)
    abs_worker = os.path.abspath(worker)
    abs_project = os.path.abspath(project)
    
    # UE-CMD mode: Use -ExecutePythonScript with manifest passed as environment variable
    os.environ['UE_MANIFEST_PATH'] = abs_manifest_path
    
    ue_args = [
        ue_editor,
        abs_project,
        f'-ExecutePythonScript={abs_worker}',
        '-unattended',
        '-nopause',
        '-nosplash',
        '-NullRHI',
        '-buildmachine',
        '-NoSound',
        '-AllowStdOutLogVerbosity',
        '-FullStdOutLogOutput',
        '-log',
    ]
    
    logger.info(f"Command: {' '.join(ue_args)}")
    logger.blank(1)
    logger.separator(width=40, char='-')
    
    try:
        result = subprocess.run(ue_args, check=False)

        logger.blank(1)
        logger.separator(width=40, char='-')
        
        if result.returncode == 0:
            logger.info("Job completed successfully")
            return 0
        else:
            logger.error(f"Job failed with exit code: {result.returncode}")
            return result.returncode
            
    except Exception as e:
        logger.error(f"Failed to launch UE: {e}")
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

    logger.header("UE Create LevelSequence Test")
    
    manifest = load_manifest(args.manifest_path)
    job_id, job_type = validate_manifest(manifest)
    
    ue_editor, project, ue_config = get_ue_config(manifest)
    
    # Merge complete ue_config back into manifest for worker
    manifest['ue_config'] = ue_config
    
    # Save updated manifest with merged ue_config
    try:
        with open(args.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.info(f"Manifest file updated: {args.manifest_path}")
    except Exception as e:
        logger.warning(f"Failed to update manifest file: {e}")
    
    logger.kv("Job ID:", job_id)
    logger.kv("Job Type:", job_type)
    logger.kv("Manifest:", args.manifest_path)
    logger.kv("UE Editor:", ue_editor)
    logger.kv("Project:", project)
    logger.kv("Output Base:", ue_config.get('output_base_dir', 'N/A'))
    logger.blank(1)
    
    validate_paths(ue_editor, project, worker)
    
    logger.info("Creating LevelSequence...")
    logger.blank(1)
    
    exit_code = run_ue_job(ue_editor, project, args.manifest_path, worker)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
