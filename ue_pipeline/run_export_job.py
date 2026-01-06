#!/usr/bin/env python3
"""
UE Camera Export Job Executor (Python version)
Execute a camera export job using UnrealEditor-Cmd.exe (Headless mode)
"""

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

def load_ue_config():
    """Load UE configuration from config file"""
    script_dir = Path(__file__).parent
    env_config_path = os.environ.get('UE_CONFIG_PATH')
    config_path = Path(env_config_path) if env_config_path else (script_dir / 'config' / 'ue_config.json')
    
    if not config_path.exists():
        logger.error(f"UE config file not found: {config_path}")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logger.error(f"Failed to load UE config: {e}")
        sys.exit(1)

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='Execute UE camera export job')
    parser.add_argument('manifest', help='Path to manifest JSON file')
    args = parser.parse_args()

    manifest_path = args.manifest

    logger.header("UE Camera Export Job Executor")

    # Load UE configuration from config file
    ue_config_global = load_ue_config()

    # Check manifest file
    if not os.path.isfile(manifest_path):
        logger.error(f"Manifest file not found: {manifest_path}")
        return 1

    # Parse manifest to get job_id, job_type, and ue_config
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        job_id = manifest.get('job_id')
        job_type = manifest.get('job_type')

        if job_type != 'export':
            logger.error(f"Invalid job type '{job_type}', expected 'export'")
            return 1

        # Read UE paths from manifest or use config file defaults
        ue_config = manifest.get('ue_config', {})
        ue_editor = ue_config.get('editor_path', ue_config_global.get('editor_path'))
        project = ue_config.get('project_path', ue_config_global.get('project_path'))
        
        # Handle "default" value - use ue_template project
        if project == "default":
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project = os.path.join(script_dir, "ue_template", "project", "WorldData.uproject")
            logger.info(f"Using default project: {project}")

        # Merge ue_config into manifest if not present
        if not manifest.get('ue_config'):
            logger.warning("No ue_config in manifest, merging config file defaults")
            manifest['ue_config'] = ue_config_global
            # Save updated manifest
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.kv("Job ID:", job_id)
        logger.kv("Job Type:", job_type)

    except json.JSONDecodeError as e:
        logger.error(f"Cannot parse manifest: {e}")
        return 1
    except Exception as e:
        logger.error(f"Failed to read manifest: {e}")
        return 1

    # Worker Export script path
    script_dir = Path(__file__).parent
    worker_export = script_dir / 'python' / 'worker_export.py'

    logger.kv("Manifest:", manifest_path)
    logger.kv("UE Editor:", ue_editor)
    logger.kv("Project:", project)
    logger.blank(1)

    # Check required files
    if not os.path.isfile(ue_editor):
        logger.error(f"UE Editor not found at: {ue_editor}")
        return 1

    if not os.path.isfile(project):
        logger.error(f"Project not found at: {project}")
        return 1

    if not os.path.isfile(worker_export):
        logger.error(f"Worker export script not found at: {worker_export}")
        return 1

    logger.info("Starting export job...")
    logger.blank(1)

    # Resolve absolute path for manifest
    abs_manifest_path = os.path.abspath(manifest_path)
    abs_project = os.path.abspath(project)

    # Pass manifest path via environment variable (for headless mode)
    os.environ['UE_MANIFEST_PATH'] = abs_manifest_path

    # Build UE launch arguments (Headless mode)
    ue_args = [
        abs_project,
        f'-ExecutePythonScript={worker_export}',
        '-unattended',
        '-nopause',
        '-nosplash',
        '-NullRHI',
        '-buildmachine',
        '-NoSound',
        '-AllowStdOutLogVerbosity',
        '-FullStdOutLogOutput',
        '-log'
    ]

    # Print command
    command_str = f'{ue_editor} {" ".join(ue_args)}'
    logger.info(f"Command: {command_str}")
    logger.blank(1)
    logger.separator(width=40, char='-')

    # Launch UE
    try:
        process = subprocess.run(
            [ue_editor] + ue_args,
            check=False
        )

        logger.blank(1)
        logger.separator(width=40, char='-')

        if process.returncode == 0:
            logger.info("Export job completed successfully")
            return 0
        else:
            logger.error(f"Export job failed with exit code: {process.returncode}")
            return process.returncode

    except Exception as e:
        logger.error(f"Failed to launch UE: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
