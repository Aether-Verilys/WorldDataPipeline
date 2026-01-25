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

from ue_pipeline.python.core import logger
from ue_pipeline.python.core import job_utils

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

    # 使用新的配置合并机制
    manifest = job_utils.merge_configs(manifest)
    ue_config = manifest['ue_config']
    ue_editor = ue_config['editor_cmd']
    project = ue_config['project_path']

    # Worker Export script path
    script_dir = Path(__file__).parent
    worker_export = str(script_dir / 'python' / 'export' / 'worker_export.py')

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

    # Create a temporary manifest with merged config
    import tempfile
    temp_manifest_fd, temp_manifest_path = tempfile.mkstemp(suffix='.json', prefix='export_manifest_')
    try:
        with os.fdopen(temp_manifest_fd, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        
        # Resolve absolute path for manifest
        abs_project = os.path.abspath(project)

        # Pass manifest path via environment variable (for headless mode)
        os.environ['UE_MANIFEST_PATH'] = temp_manifest_path

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
                logger.info("Export job completed")
                return 0
            else:
                logger.error(f"Export job failed with exit code: {process.returncode}")
                return process.returncode

        except Exception as e:
            logger.error(f"Failed to launch UE: {e}")
            return 1
    finally:
        # Clean up temporary manifest
        try:
            if os.path.exists(temp_manifest_path):
                os.remove(temp_manifest_path)
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
