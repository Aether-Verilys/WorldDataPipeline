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
from ue_pipeline.python import job_utils

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='Execute UE camera export job')
    parser.add_argument('manifest', help='Path to manifest JSON file')
    args = parser.parse_args()

    manifest_path = args.manifest

    logger.header("UE Camera Export Job Executor")

    # Load and validate manifest
    manifest = job_utils.load_manifest(manifest_path)
    job_id = job_utils.validate_manifest_type(manifest, 'export')

    # Get UE configuration
    ue_config = job_utils.get_ue_config(manifest)
    ue_editor = ue_config['editor_cmd']
    project = ue_config['project_path']
    
    # Merge complete ue_config back into manifest for worker
    manifest['ue_config'] = ue_config
    
    # Save updated manifest with merged ue_config
    job_utils.save_manifest(manifest, manifest_path)

    # Worker Export script path
    script_dir = Path(__file__).parent
    worker_export = str(script_dir / 'python' / 'worker_export.py')

    logger.kv("Job ID:", job_id)
    logger.kv("Job Type:", "export")
    logger.kv("Manifest:", manifest_path)
    logger.kv("UE Editor:", ue_editor)
    logger.kv("Project:", project)
    logger.blank(1)

    # Validate paths
    job_utils.validate_paths(ue_config, [worker_export])

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
