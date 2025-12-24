#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def print_header(title: str):
    print("=" * 40)
    print(title)
    print("=" * 40)
    print()


def print_error(message: str):
    print(f"ERROR: {message}", file=sys.stderr)


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


def load_default_ue_config() -> dict:
    script_dir = Path(__file__).parent
    config_path = script_dir / 'config' / 'ue_config.json'
    
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print_error(f"Cannot load default ue_config: {e}")
        sys.exit(1)


def get_ue_config(manifest: dict) -> tuple[str, str]:
    default_config = load_default_ue_config()
    
    manifest_config = manifest.get('ue_config', {})
    ue_config = {**default_config, **manifest_config}
    
    if not ue_config:
        print_error("No ue_config found in manifest or default config file")
        sys.exit(1)
    
    editor_path = ue_config.get('editor_path')
    if not editor_path:
        print_error("Missing 'editor_path' in ue_config")
        sys.exit(1)
    
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


def run_ue_job(ue_editor: str, project: str, manifest_path: str, worker: str, job_id: str, full_config: dict) -> int:
    abs_manifest_path = os.path.abspath(manifest_path)
    abs_worker = os.path.abspath(worker)
    
    with open(abs_manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    manifest['ue_config'] = full_config
    
    import tempfile
    temp_manifest_fd, temp_manifest_path = tempfile.mkstemp(suffix='.json', prefix='navmesh_manifest_')
    try:
        with os.fdopen(temp_manifest_fd, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        
        os.environ['UE_NAVMESH_MANIFEST'] = temp_manifest_path
        
        ue_args = [
            ue_editor,
            project,
            f'-ExecutePythonScript={abs_worker}',
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
            '-stdout',
            '-FullStdOutLogOutput',
            f'LOG=NavMeshBake_{job_id}.txt',
        ]
        
        print(f"Command: {' '.join(ue_args)}")
        print()
        print("-" * 40)
        
        try:
            result = subprocess.run(ue_args, check=False)
            
            print()
            print("-" * 40)
            
            if result.returncode == 0:
                print("NavMesh bake job completed successfully")
                return 0
            else:
                print_error(f"NavMesh bake job failed with exit code: {result.returncode}")
                return result.returncode
                
        except Exception as e:
            print_error(f"Failed to launch UE: {e}")
            return 1
    finally:
        try:
            if os.path.exists(temp_manifest_path):
                os.remove(temp_manifest_path)
        except:
            pass


def main():
    parser = argparse.ArgumentParser(
        description='UE NavMesh Bake Tool (Headless Mode)'
    )
    parser.add_argument(
        'manifest_path',
        help='Path to the navmesh bake manifest JSON file'
    )
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    worker = str(script_dir / 'python' / 'worker_bake_navmesh.py')
    
    print_header("UE NavMesh Bake Tool (Headless Mode)")
    
    manifest = load_manifest(args.manifest_path)
    
    job_id = manifest.get('job_id', 'unknown')
    job_type = manifest.get('job_type', 'unknown')
    
    if job_type != 'bake_navmesh':
        print_error(f"Invalid job type '{job_type}', expected 'bake_navmesh'")
        sys.exit(1)
    
    ue_editor, project = get_ue_config(manifest)
    
    full_config = load_default_ue_config()
    
    navmesh_config = manifest.get('navmesh_config', {})
    maps = navmesh_config.get('maps', [])
    location = navmesh_config.get('location', [0.0, 0.0, 0.0])
    scale = navmesh_config.get('scale', [100.0, 100.0, 10.0])
    
    print_info("Job ID:", job_id)
    print_info("Maps:", str(len(maps)))
    print_info("Location:", str(location))
    print_info("Scale:", str(scale))
    print_info("UE Editor:", ue_editor)
    print_info("Project:", project)
    print()
    
    validate_paths(ue_editor, project, worker)
    
    print("Starting NavMesh bake job...")
    print()
    
    exit_code = run_ue_job(ue_editor, project, args.manifest_path, worker, job_id, full_config)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
