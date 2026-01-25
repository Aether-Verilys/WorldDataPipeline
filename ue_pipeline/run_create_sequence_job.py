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

from ue_pipeline.python.core import logger
from ue_pipeline.python.core import job_utils


def run_ue_job(ue_editor: str, project: str, merged_manifest: dict, worker: str) -> int:
    abs_worker = os.path.abspath(worker)
    abs_project = os.path.abspath(project)
    
    # Create a temporary manifest with merged config
    import tempfile
    import json
    temp_manifest_fd, temp_manifest_path = tempfile.mkstemp(suffix='.json', prefix='sequence_manifest_')
    try:
        with os.fdopen(temp_manifest_fd, 'w', encoding='utf-8') as f:
            json.dump(merged_manifest, f, indent=2)
        
        # UE-CMD mode: Use -ExecutePythonScript with manifest passed as environment variable
        os.environ['UE_MANIFEST_PATH'] = temp_manifest_path
        os.environ['UE_MANIFEST_PATH'] = temp_manifest_path
        
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
                logger.info("Job completed")
                return 0
            else:
                logger.error(f"Job failed with exit code: {result.returncode}")
                return result.returncode
                
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
    worker = str(script_dir / 'python' / 'sequence' / 'worker_create.py')
    
    manifest = job_utils.load_manifest(args.manifest_path)
    job_id = job_utils.validate_manifest_type(manifest, 'create_sequence')
    
    # 使用新的配置合并机制
    manifest = job_utils.merge_configs(manifest)
    ue_config = manifest['ue_config']
    ue_editor = ue_config['editor_cmd']
    project = ue_config['project_path']
    
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
    
    exit_code = run_ue_job(ue_editor, project, manifest, worker)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
