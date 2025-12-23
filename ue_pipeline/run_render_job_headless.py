#!/usr/bin/env python3
"""
UE Render Job Executor (Headless Mode)
Execute a render job using command-line MRQ execution
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# ============================================================
# Helper Functions
# ============================================================

def print_header(title: str):
    """Print a formatted header"""
    print("=" * 40)
    print(title)
    print("=" * 40)
    print()


def print_error(message: str):
    """Print an error message"""
    print(f"ERROR: {message}", file=sys.stderr)


def print_info(key: str, value: str):
    """Print an info line"""
    print(f"{key:14s} {value}")


def load_manifest(manifest_path: str) -> dict:
    """Load and validate manifest file"""
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


def validate_manifest(manifest: dict) -> tuple[str, str]:
    """Validate manifest and return job_id and job_type"""
    job_id = manifest.get('job_id', 'unknown')
    job_type = manifest.get('job_type', 'unknown')
    
    if job_type != 'render':
        print_error(f"Invalid job type '{job_type}', expected 'render'")
        sys.exit(1)
    
    return job_id, job_type


def load_default_ue_config() -> dict:
    """Load default UE configuration from config file"""
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


def get_ue_config(manifest: dict) -> tuple[str, str, str]:
    """Extract UE configuration from manifest or default config file"""
    # Load default config first
    default_config = load_default_ue_config()
    
    # Merge with manifest config (manifest overrides default)
    manifest_config = manifest.get('ue_config', {})
    ue_config = {**default_config, **manifest_config}
    
    if not ue_config:
        print_error("No ue_config found in manifest or default config file")
        sys.exit(1)
    
    editor_path = ue_config.get('editor_path')
    if not editor_path:
        print_error("Missing 'editor_path' in ue_config")
        sys.exit(1)
    
    # Replace UnrealEditor.exe with UnrealEditor-Cmd.exe
    ue_editor = editor_path.replace('UnrealEditor.exe', 'UnrealEditor-Cmd.exe')
    
    project = ue_config.get('project_path')
    if not project:
        print_error("Missing 'project_path' in ue_config")
        sys.exit(1)
    
    output_base_dir = ue_config.get('output_base_dir', '')
    if not output_base_dir:
        print_error("Missing 'output_base_dir' in ue_config")
        sys.exit(1)
    
    return ue_editor, project, output_base_dir


def get_render_config(manifest: dict, ue_config: dict) -> dict:
    """Extract render configuration from manifest and lookup map from ue_config scenes"""
    sequence = manifest.get('sequence', '')
    rendering = manifest.get('rendering', {})
    
    config_preset = rendering.get('preset', '')
    
    # Extract map name from sequence path
    # Format: /Game/CameraController/Generated/Lvl_FirstPerson_001
    # Sequence name: Lvl_FirstPerson_001
    # Map name: Lvl_FirstPerson
    map_path = None
    
    if sequence:
        # Get the last part of the sequence path (sequence name)
        parts = sequence.split('/')
        sequence_name = parts[-1] if parts else ''
        
        if sequence_name:
            # Extract map name by removing trailing _### pattern
            # e.g., Lvl_FirstPerson_001 -> Lvl_FirstPerson
            import re
            map_name = re.sub(r'_\d+$', '', sequence_name)
            
            # Lookup map path from ue_config scenes
            scenes = ue_config.get('scenes', [])
            for scene in scenes:
                maps = scene.get('maps', [])
                for map_info in maps:
                    if map_info.get('name') == map_name:
                        map_path = map_info.get('path')
                        print(f"Extracted map name '{map_name}' from sequence '{sequence_name}'")
                        print(f"Found map path in config: {map_path}")
                        break
                if map_path:
                    break
            
            if not map_path:
                print_error(f"Cannot find map '{map_name}' in ue_config scenes")
                sys.exit(1)
        else:
            print_error(f"Cannot extract sequence name from path: {sequence}")
            sys.exit(1)
    
    return {
        'sequence': sequence,
        'map': map_path,
        'preset': config_preset
    }


def validate_paths(ue_editor: str, project: str, worker: str):
    """Validate that all required paths exist"""
    if not os.path.exists(ue_editor):
        print_error(f"UE Editor not found at: {ue_editor}")
        sys.exit(1)
    
    if not os.path.exists(project):
        print_error(f"Project not found at: {project}")
        sys.exit(1)
    
    if not os.path.exists(worker):
        print_error(f"Worker script not found at: {worker}")
        sys.exit(1)


def ensure_output_directory(output_path: str):
    """Ensure output directory exists"""
    if output_path:
        abs_output_path = os.path.abspath(output_path)
        if not os.path.exists(abs_output_path):
            os.makedirs(abs_output_path, exist_ok=True)
            print(f"Created output directory: {abs_output_path}")


def run_ue_job(ue_editor: str, project: str, manifest_path: str, worker: str, job_id: str, full_config: dict) -> int:
    """Run the UE render job and return exit code"""
    abs_manifest_path = os.path.abspath(manifest_path)
    abs_worker = os.path.abspath(worker)
    
    # Load original manifest
    with open(abs_manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    # Inject full ue_config into manifest for worker to use
    manifest['ue_config'] = full_config
    
    # Create a temporary manifest with ue_config injected
    import tempfile
    temp_manifest_fd, temp_manifest_path = tempfile.mkstemp(suffix='.json', prefix='render_manifest_')
    try:
        with os.fdopen(temp_manifest_fd, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        
        # Set manifest path as environment variable for Python script to read
        os.environ['UE_RENDER_MANIFEST'] = temp_manifest_path
        
        # Build UE command-line arguments
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
            f'LOG=RenderLog_{job_id}.txt',
        ]
        
        print(f"Command: {' '.join(ue_args)}")
        print()
        print("-" * 40)
        
        try:
            result = subprocess.run(ue_args, check=False)
            
            print()
            print("-" * 40)
            
            if result.returncode == 0:
                print("Render job completed successfully")
                return 0
            else:
                print_error(f"Render job failed with exit code: {result.returncode}")
                return result.returncode
                
        except Exception as e:
            print_error(f"Failed to launch UE: {e}")
            return 1
    finally:
        # Clean up temporary manifest file
        try:
            if os.path.exists(temp_manifest_path):
                os.remove(temp_manifest_path)
        except:
            pass


# ============================================================
# Main Function
# ============================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='UE Render Job Executor (Headless Mode)'
    )
    parser.add_argument(
        'manifest_path',
        help='Path to the job manifest JSON file'
    )
    
    args = parser.parse_args()
    
    # Get worker script path (relative to this script)
    script_dir = Path(__file__).parent
    worker = str(script_dir / 'python' / 'worker_render.py')
    
    # Print header
    print_header("UE Render Job Executor (Headless Mode)")
    
    # Load and validate manifest
    manifest = load_manifest(args.manifest_path)
    job_id, job_type = validate_manifest(manifest)
    
    # Get UE configuration
    ue_editor, project, output_base_dir = get_ue_config(manifest)
    
    # Load full config for scene lookup
    full_config = load_default_ue_config()
    
    # Get render configuration (with map lookup)
    render_config = get_render_config(manifest, full_config)
    
    # Print job info
    print_info("Job ID:", job_id)
    print_info("Sequence:", render_config['sequence'])
    print_info("Map:", render_config['map'])
    print_info("Config:", render_config['preset'])
    print_info("Output:", output_base_dir)
    print_info("UE Editor:", ue_editor)
    print_info("Project:", project)
    print()
    
    # Validate paths
    validate_paths(ue_editor, project, worker)
    
    # Ensure output directory exists
    ensure_output_directory(output_base_dir)
    
    # Run the job
    print("Starting headless render job...")
    print()
    
    exit_code = run_ue_job(ue_editor, project, args.manifest_path, worker, job_id, full_config)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
