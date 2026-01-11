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


def run_ue_job(ue_editor: str, project: str, manifest_path: str, worker_phase1: str, worker_phase2: str, job_id: str, full_config: dict) -> int:
    abs_manifest_path = os.path.abspath(manifest_path)
    abs_worker_phase1 = os.path.abspath(worker_phase1)
    abs_worker_phase2 = os.path.abspath(worker_phase2)
    
    with open(abs_manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    manifest['ue_config'] = full_config
    
    import tempfile
    temp_manifest_fd, temp_manifest_path = tempfile.mkstemp(suffix='.json', prefix='navmesh_manifest_')
    try:
        with os.fdopen(temp_manifest_fd, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        
        os.environ['UE_NAVMESH_MANIFEST'] = temp_manifest_path
        
        abs_project = os.path.abspath(project)
        
        # Get maps list for Phase 2
        navmesh_config = manifest.get('navmesh_config', {})
        maps = navmesh_config.get('maps', [])
        
        # ============================================================
        # PHASE 1: Add NavMeshBoundsVolume and save maps
        # ============================================================
        logger.info("=" * 60)
        logger.info("PHASE 1: Adding NavMeshBoundsVolume to maps")
        logger.info("=" * 60)
        
        ue_args_phase1 = [
            ue_editor,
            abs_project,
            f'-ExecutePythonScript={abs_worker_phase1}',
            '-RenderOffscreen',
            '-ResX=1920',
            '-ResY=1080',
            '-ForceRes',
            '-Windowed',
            '-NoLoadingScreen',
            '-NoScreenMessages',
            '-NoSplash',
            '-Unattended',
            '-NoSound',
            '-AllowStdOutLogVerbosity',
            '-log',
            '-FullStdOutLogOutput',
            f'LOG=NavMeshBake_Phase1_{job_id}.txt',
        ]
        
        logger.info(f"Command: {' '.join(ue_args_phase1)}")
        logger.blank(1)
        logger.separator(width=40, char='-')
        
        try:
            result_phase1 = subprocess.run(ue_args_phase1, check=False)

            logger.blank(1)
            logger.separator(width=40, char='-')
            
            if result_phase1.returncode != 0:
                logger.error(f"Phase 1 failed with exit code: {result_phase1.returncode}")
                return result_phase1.returncode
            
            logger.info("Phase 1 completed - NavMeshBoundsVolume added and saved")
            logger.blank(1)
            
        except Exception as e:
            logger.error(f"Failed to launch UE Phase 1: {e}")
            return 1
        
        # ============================================================
        # PHASE 2: Reload each map with cmd to trigger NavMesh build
        # ============================================================
        logger.info("=" * 60)
        logger.info("PHASE 2: Triggering NavMesh build by reloading maps")
        logger.info("=" * 60)
        
        for i, map_path in enumerate(maps, 1):
            logger.info(f"[{i}/{len(maps)}] Reloading map to trigger build and verify: {map_path}")
            
            # Set environment variable for worker to know which map to verify
            os.environ['UE_VERIFY_MAP_PATH'] = map_path
            
            ue_args_phase2 = [
                ue_editor,
                abs_project,
                map_path,  # Directly load the map to trigger NavMesh build
                f'-ExecutePythonScript={abs_worker_phase2}',
                map_path,  # Directly load the map to trigger NavMesh build
                '-RenderOffscreen',
                '-ResX=1920',
                '-ResY=1080',
                '-ForceRes',
                '-Windowed',
                '-NoLoadingScreen',
                '-NoScreenMessages',
                '-NoSplash',
                '-Unattended',
                '-NoSound',
                '-AllowStdOutLogVerbosity',
                '-log',
                '-FullStdOutLogOutput',
                f'LOG=NavMeshBake_Phase2_{job_id}_Map{i}.txt',
            ]
            
            logger.info(f"Command: {' '.join(ue_args_phase2)}")
            logger.blank(1)
            logger.separator(width=40, char='-')
            
            try:
                result_phase2 = subprocess.run(ue_args_phase2, check=False)

                logger.blank(1)
                logger.separator(width=40, char='-')
                
                if result_phase2.returncode != 0:
                    logger.warning(f"Phase 2 map {i} completed with exit code: {result_phase2.returncode}")
                else:
                    logger.info(f"Phase 2 map {i} completed successfully")
                    
            except Exception as e:
                logger.error(f"Failed to launch UE Phase 2 for map {i}: {e}")
                continue
            
            logger.blank(1)
        
        logger.info("=" * 60)
        logger.info("NavMesh bake job completed (2-phase execution)")
        logger.info("=" * 60)
        return 0
                
    finally:
        try:
            if os.path.exists(temp_manifest_path):
                os.remove(temp_manifest_path)
        except:
            pass


def main():
    parser = argparse.ArgumentParser(
        description='UE NavMesh Bake Tool (Headless Mode) - Supports auto-scale and manual configuration'
    )
    parser.add_argument(
        'manifest_path',
        help='Path to the navmesh bake manifest JSON file'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    worker_phase1 = str(script_dir / 'python' / 'worker_bake_navmesh.py')
    worker_phase2 = str(script_dir / 'python' / 'worker_verify_navmesh.py')
    
    logger.header("UE NavMesh Bake Tool (Headless Mode)")
    
    manifest = job_utils.load_manifest(args.manifest_path)
    job_id = job_utils.validate_manifest_type(manifest, 'bake_navmesh')
    
    ue_config = job_utils.get_ue_config(manifest)
    ue_editor = ue_config['editor_cmd']
    project = ue_config['project_path']
    
    full_config = job_utils.load_default_ue_config()
    
    navmesh_config = manifest.get('navmesh_config', {})
    maps = navmesh_config.get('maps', [])
    scale_margin = navmesh_config.get('scale_margin', 1.2)
    min_scale = navmesh_config.get('min_scale', [20.0, 20.0, 5.0])
    max_scale = navmesh_config.get('max_scale', [500.0, 500.0, 50.0])

    logger.kv("Mode:", "Auto-scale")
    logger.kv("Scale Margin:", f"{scale_margin}x")
    logger.kv("Min Scale:", str(min_scale))
    logger.kv("Max Scale:", str(max_scale))
    logger.kv("Job ID:", job_id)
    logger.kv("Maps:", str(len(maps)))
    logger.kv("UE Editor:", ue_editor)
    logger.kv("Project:", project)
    logger.blank(1)
    
    job_utils.validate_paths(ue_config, [worker_phase1, worker_phase2])
    
    logger.info("Starting NavMesh bake job...")
    logger.blank(1)
    
    exit_code = run_ue_job(ue_editor, project, args.manifest_path, worker_phase1, worker_phase2, job_id, full_config)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
