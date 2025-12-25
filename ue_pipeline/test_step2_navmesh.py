#!/usr/bin/env python3
"""
Test script for Step 2: NavMesh Auto-scale Baking System
验证NavMesh自适应烘焙功能是否正确实现

Usage:
    python test_step2_navmesh.py --map /Game/YourScene/Maps/YourMap
"""

import argparse
import json
import os
import sys
from pathlib import Path
import subprocess

def print_header(title):
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)

def create_test_manifest(map_path, output_dir, job_id="test_navmesh_001"):
    """Create a test manifest for NavMesh baking"""
    
    manifest = {
        "job_id": job_id,
        "job_type": "bake_navmesh",
        "description": f"Test NavMesh auto-scale for {map_path}",
        "navmesh_config": {
            "auto_scale": True,
            "scale_margin": 1.2,
            "min_scale": [20.0, 20.0, 5.0],
            "max_scale": [500.0, 500.0, 50.0],
            "agent_max_step_height": 50.0,
            "agent_max_jump_height": 200.0,
            "wait_for_build": True,
            "build_timeout": 120,
            "verify_navmesh": True,
            "maps": [map_path]
        }
    }
    
    manifest_path = output_dir / f"test_manifest_{job_id}.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    
    return manifest_path

def run_bake_test(manifest_path, verbose=False):
    """Run the NavMesh bake test"""
    
    script_dir = Path(__file__).parent
    run_script = script_dir / "run_bake_navmesh.py"
    
    if not run_script.exists():
        print(f"ERROR: run_bake_navmesh.py not found at {run_script}")
        return False
    
    cmd = [sys.executable, str(run_script), str(manifest_path)]
    
    if verbose:
        cmd.append("--verbose")
    
    print(f"\nRunning command: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode == 0
    except Exception as e:
        print(f"ERROR: Failed to run bake test: {e}")
        return False

def verify_results(map_path):
    """Verify that NavMesh was successfully baked"""
    
    print("\n" + "=" * 70)
    print("  Verification Checklist")
    print("=" * 70)
    
    checklist = [
        ("Map loaded successfully", "Check UE logs for map load confirmation"),
        ("Navigable components filtered", "Check logs for 'can_ever_affect_navigation' filtering"),
        ("Z-axis physics parameters applied", "Check logs for agent step/jump heights"),
        ("Volume layout strategy selected", "Check logs for SMALL/MEDIUM/LARGE scene strategy"),
        ("NavMeshBoundsVolume created", "Check logs for volume creation with calculated scale"),
        ("NavMesh build completed", "Check logs for 'NavMesh build completed'"),
        ("NavData exists", "Check logs for 'NavData exists'"),
        ("Tile count > 0", "Check logs for 'NavMesh tile count'"),
        ("Reachability test passed", "Check logs for reachability success rate >= 80%"),
        ("Level saved", "Check logs for 'Level saved successfully'"),
    ]
    
    for i, (item, hint) in enumerate(checklist, 1):
        print(f"\n{i}. [{' ' * 3}] {item}")
        print(f"    Hint: {hint}")
    
    print("\n" + "=" * 70)
    print("Please review the UE logs above to verify all items in the checklist.")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(
        description='Test Step 2: NavMesh Auto-scale Baking System'
    )
    parser.add_argument(
        '--map',
        required=True,
        help='Map path to test (e.g., /Game/YourScene/Maps/YourMap)'
    )
    parser.add_argument(
        '--job-id',
        default='test_navmesh_001',
        help='Job ID for this test (default: test_navmesh_001)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=None,
        help='Output directory for test manifest (default: ue_pipeline/jobs/inbox)'
    )
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    
    if args.output_dir is None:
        output_dir = script_dir / 'jobs' / 'inbox'
    else:
        output_dir = args.output_dir
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print_header("Step 2: NavMesh Auto-scale Baking Test")
    
    print(f"\nTest Configuration:")
    print(f"  Map Path:     {args.map}")
    print(f"  Job ID:       {args.job_id}")
    print(f"  Output Dir:   {output_dir}")
    print(f"  Verbose:      {args.verbose}")
    
    # Create test manifest
    print("\nCreating test manifest...")
    manifest_path = create_test_manifest(args.map, output_dir, args.job_id)
    print(f"Manifest created: {manifest_path}")
    
    # Display manifest
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    print("\nManifest contents:")
    print(json.dumps(manifest, indent=2))
    
    # Run the test
    print_header("Running NavMesh Bake Test")
    
    success = run_bake_test(manifest_path, args.verbose)
    
    # Verify results
    verify_results(args.map)
    
    # Final result
    print_header("Test Result")
    
    if success:
        print("✓ NavMesh bake test COMPLETED")
        print("\nNext steps:")
        print("1. Open the map in UE Editor")
        print("2. Verify NavMeshBoundsVolume exists with correct scale")
        print("3. Press 'P' key to visualize NavMesh (green overlay)")
        print("4. Check that navigable areas are highlighted")
        return 0
    else:
        print("✗ NavMesh bake test FAILED")
        print("\nTroubleshooting:")
        print("1. Check the UE logs above for error messages")
        print("2. Verify the map path is correct")
        print("3. Ensure UE Editor path in ue_config.json is correct")
        print("4. Check that the map has navigable geometry")
        return 1

if __name__ == '__main__':
    sys.exit(main())
