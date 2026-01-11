import os
import json
import sys
from pathlib import Path
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

def validate_manifest_type(manifest: dict, expected_type: str) -> str:
    job_id = manifest.get('job_id', 'unknown')
    job_type = manifest.get('job_type', 'unknown')
    
    if job_type != expected_type:
        logger.error(f"Invalid job type '{job_type}', expected '{expected_type}'")
        sys.exit(1)
    
    return job_id

def load_default_ue_config() -> dict:
    # This utility is in ue_pipeline/python/job_utils.py
    # Config is in ue_pipeline/config/ue_config.json
    script_dir = Path(__file__).parent.parent
    env_config_path = os.environ.get('UE_CONFIG_PATH')
    config_path = Path(env_config_path) if env_config_path else (script_dir / 'config' / 'ue_config.json')
    
    if not config_path.exists():
        logger.warning(f"UE config file not found: {config_path}")
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load UE config: {e}")
        return {}

def get_ue_config(manifest: dict) -> dict:
    # Load default config first
    default_config = load_default_ue_config()
    
    # Merge with manifest config (manifest overrides default)
    manifest_config = manifest.get('ue_config', {})
    ue_config = {**default_config, **manifest_config}
    
    if not ue_config:
        logger.error("No ue_config found in manifest or default config file")
        sys.exit(1)
    
    # Resolve Editor path
    editor_path = ue_config.get('editor_path')
    if not editor_path:
        logger.error("Missing 'editor_path' in ue_config")
        sys.exit(1)
    
    # Use UnrealEditor-Cmd.exe for headless/scripting jobs
    ue_config['editor_cmd'] = editor_path.replace('UnrealEditor.exe', 'UnrealEditor-Cmd.exe')
    
    # Resolve Project path
    project = ue_config.get('project_path')
    if not project:
        logger.error("Missing 'project_path' in ue_config")
        sys.exit(1)
    
    # Handle "default" value - use ue_template project
    if project == "default":
        # Root is 3 levels up from this file (ue_pipeline/python/job_utils.py)
        repo_root = Path(__file__).parent.parent.parent
        project = str(repo_root / "ue_template" / "project" / "WorldData.uproject")
        ue_config['project_path'] = project
        logger.info(f"Using default project: {project}")
    
    # Handle optional output_base_dir
    output_base_dir = ue_config.get('output_base_dir')
    if output_base_dir == "default":
        repo_root = Path(__file__).parent.parent.parent
        output_base_dir = str(repo_root / "output")
        ue_config['output_base_dir'] = output_base_dir
        logger.info(f"Using default output directory: {output_base_dir}")
        
    return ue_config

def validate_paths(ue_config: dict, worker_scripts: list = None):
    editor_cmd = ue_config.get('editor_cmd')
    project = ue_config.get('project_path')
    
    if not os.path.exists(editor_cmd):
        logger.error(f"UE Editor not found at: {editor_cmd}")
        sys.exit(1)
    
    if not os.path.exists(project):
        logger.error(f"Project not found at: {project}")
        sys.exit(1)
    
    if worker_scripts:
        for script in worker_scripts:
            if not os.path.exists(script):
                logger.error(f"Worker script not found at: {script}")
                sys.exit(1)

def save_manifest(manifest: dict, manifest_path: str):
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.info(f"Manifest file updated: {manifest_path}")
    except Exception as e:
        logger.warning(f"Failed to update manifest file: {e}")
