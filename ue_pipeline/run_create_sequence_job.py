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
from ue_pipeline.python import job_utils


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
    
    manifest = job_utils.load_manifest(args.manifest_path)
    job_id = job_utils.validate_manifest_type(manifest, 'create_sequence')
    
    ue_config = job_utils.get_ue_config(manifest)
    ue_editor = ue_config['editor_cmd']
    project = ue_config['project_path']
    
    # Merge complete ue_config back into manifest for worker
    manifest['ue_config'] = ue_config
    
    # Save updated manifest with merged ue_config
    job_utils.save_manifest(manifest, args.manifest_path)
    
    logger.kv("Job ID:", job_id)
    logger.kv("Job Type:", "create_sequence")
    logger.kv("Manifest:", args.manifest_path)
    logger.kv("UE Editor:", ue_editor)
    logger.kv("Project:", project)
    logger.kv("Output Base:", ue_config.get('output_base_dir', 'N/A'))
    logger.blank(1)
    
    job_utils.validate_paths(ue_config, [worker])
    
    logger.info("Creating LevelSequence...")
    logger.blank(1)
    
    exit_code = run_ue_job(ue_editor, project, args.manifest_path, worker)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
