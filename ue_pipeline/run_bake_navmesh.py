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


def load_default_ue_config() -> dict:
    script_dir = Path(__file__).parent
    env_config_path = os.environ.get('UE_CONFIG_PATH')
    config_path = Path(env_config_path) if env_config_path else (script_dir / 'config' / 'ue_config.json')
    
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Cannot load default ue_config: {e}")
        sys.exit(1)


def get_ue_config(manifest: dict) -> tuple[str, str]:
    default_config = load_default_ue_config()
    
    manifest_config = manifest.get('ue_config', {})
    ue_config = {**default_config, **manifest_config}
    
    if not ue_config:
        logger.error("No ue_config found in manifest or default config file")
        sys.exit(1)
    
    editor_path = ue_config.get('editor_path')
    if not editor_path:
        logger.error("Missing 'editor_path' in ue_config")
        sys.exit(1)
    
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
    
    return ue_editor, project


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
    
    manifest = load_manifest(args.manifest_path)
    
    job_id = manifest.get('job_id', 'unknown')
    job_type = manifest.get('job_type', 'unknown')
    
    if job_type != 'bake_navmesh':
        logger.error(f"Invalid job type '{job_type}', expected 'bake_navmesh'")
        sys.exit(1)
    
    ue_editor, project = get_ue_config(manifest)
    
    full_config = load_default_ue_config()
    
    navmesh_config = manifest.get('navmesh_config', {})
    maps = navmesh_config.get('maps', [])
    auto_scale = navmesh_config.get('auto_scale', False)
    
    # Display configuration
    if auto_scale:
        scale_margin = navmesh_config.get('scale_margin', 1.2)
        min_scale = navmesh_config.get('min_scale', [20.0, 20.0, 5.0])
        max_scale = navmesh_config.get('max_scale', [500.0, 500.0, 50.0])
        logger.kv("Mode:", "Auto-scale")
        logger.kv("Scale Margin:", f"{scale_margin}x")
        logger.kv("Min Scale:", str(min_scale))
        logger.kv("Max Scale:", str(max_scale))
    else:
        location = navmesh_config.get('location', [0.0, 0.0, 0.0])
        scale = navmesh_config.get('scale', [100.0, 100.0, 10.0])
        logger.kv("Mode:", "Manual")
        logger.kv("Location:", str(location))
        logger.kv("Scale:", str(scale))
    
    logger.kv("Maps:", str(len(maps)))

    logger.kv("Job ID:", job_id)
    logger.kv("Maps:", str(len(maps)))
    logger.kv("UE Editor:", ue_editor)
    logger.kv("Project:", project)
    logger.blank(1)
    
    if args.verbose:
        logger.info("Full manifest configuration:")
        logger.plain(json.dumps(manifest, indent=2))
        logger.blank(1)
    
    validate_paths(ue_editor, project, worker_phase1)
    
    if not os.path.exists(worker_phase2):
        logger.error(f"Worker script not found at: {worker_phase2}")
        sys.exit(1)
    
    logger.info("Starting NavMesh bake job...")
    logger.blank(1)
    
    exit_code = run_ue_job(ue_editor, project, args.manifest_path, worker_phase1, worker_phase2, job_id, full_config)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
