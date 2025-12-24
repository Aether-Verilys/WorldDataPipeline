#!/usr/bin/env python3

import json
import os
import sys
import subprocess
from pathlib import Path


def load_ue_config():
    script_dir = Path(__file__).parent
    config_path = script_dir / 'config' / 'ue_config.json'
    
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_navmesh_manifest(config: dict, output_path: str):
    scenes = config.get('scenes', [])
    
    all_maps = []
    for scene in scenes:
        maps = scene.get('maps', [])
        for map_info in maps:
            map_path = map_info.get('path')
            if map_path:
                all_maps.append(map_path)
    
    manifest = {
        "job_type": "bake_navmesh",
        "job_id": "job-navmesh-batch-all",
        "navmesh_config": {
            "location": [0.0, 0.0, 0.0],
            "scale": [150.0, 150.0, 15.0],
            "maps": all_maps
        },
        "metadata": {
            "description": "Batch add NavMesh to all scenes from ue_config.json",
            "created_date": "2025-12-25",
            "auto_generated": True
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"Generated manifest with {len(all_maps)} maps")
    print(f"Manifest saved to: {output_path}")
    
    return manifest


def main():
    print("="*60)
    print("Batch NavMesh Bake - All Scenes")
    print("="*60)
    print()
    
    config = load_ue_config()
    
    script_dir = Path(__file__).parent
    temp_manifest_path = script_dir / 'examples' / 'job_bake_navmesh_auto.json'
    
    manifest = create_navmesh_manifest(config, str(temp_manifest_path))
    
    print()
    print("Maps to process:")
    for i, map_path in enumerate(manifest['navmesh_config']['maps'], 1):
        print(f"  {i}. {map_path}")
    
    print()
    response = input("Continue with NavMesh bake? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    run_script = script_dir / 'run_bake_navmesh.py'
    
    cmd = [sys.executable, str(run_script), str(temp_manifest_path)]
    
    print()
    print("Executing NavMesh bake...")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd)
    
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
