#!/usr/bin/env python3
"""
Quick test script for NavMesh auto-scale baking
Run this to verify Step 2 implementation
"""
import os
import sys
import json
from pathlib import Path

def print_header(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

def check_file_exists(filepath, description):
    """Check if a file exists and print status"""
    if Path(filepath).exists():
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description} NOT FOUND: {filepath}")
        return False

def check_json_valid(filepath, description):
    """Check if JSON file is valid"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ {description} is valid JSON")
        return True, data
    except Exception as e:
        print(f"❌ {description} JSON error: {e}")
        return False, None

def main():
    print_header("Step 2: NavMesh Auto-Scale Implementation Test")
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent if script_dir.name == 'ue_pipeline' else script_dir
    ue_pipeline = project_root / 'ue_pipeline'
    
    all_ok = True
    
    # Test 1: Core Python files
    print_header("Test 1: Core Python Files")
    files_to_check = [
        (ue_pipeline / 'python' / 'pre_process' / 'add_navmesh_to_scene.py', 
         "NavMeshManager (with auto_scale)"),
        (ue_pipeline / 'python' / 'worker_bake_navmesh.py', 
         "Worker script"),
        (ue_pipeline / 'run_bake_navmesh.py', 
         "CLI runner"),
    ]
    
    for filepath, desc in files_to_check:
        if not check_file_exists(filepath, desc):
            all_ok = False
    
    # Test 2: Example manifests
    print_header("Test 2: Example Job Manifests")
    examples = [
        'job_bake_navmesh_auto.json',
        'job_bake_navmesh_manual.json',
        'job_bake_navmesh_batch.json'
    ]
    
    for example in examples:
        filepath = ue_pipeline / 'examples' / example
        exists = check_file_exists(filepath, f"Example: {example}")
        if exists:
            valid, data = check_json_valid(filepath, example)
            if not valid:
                all_ok = False
        else:
            all_ok = False
    
    # Test 3: Check implementation details
    print_header("Test 3: Implementation Features Check")
    
    navmesh_file = ue_pipeline / 'python' / 'pre_process' / 'add_navmesh_to_scene.py'
    if navmesh_file.exists():
        content = navmesh_file.read_text(encoding='utf-8')
        features = [
            ('calculate_map_bounds', 'Auto boundary calculation'),
            ('calculate_navmesh_scale', 'Scale calculation'),
            ('auto_scale_navmesh', 'Auto-scale main function'),
            ('wait_for_navmesh_build', 'Build wait mechanism'),
            ('verify_navmesh_data', 'NavMesh verification'),
        ]
        
        for method, desc in features:
            if method in content:
                print(f"✅ {desc} ({method})")
            else:
                print(f"❌ {desc} ({method}) NOT FOUND")
                all_ok = False
    
    worker_file = ue_pipeline / 'python' / 'worker_bake_navmesh.py'
    if worker_file.exists():
        content = worker_file.read_text(encoding='utf-8')
        features = [
            ('auto_scale', 'Auto-scale parameter support'),
            ('wait_for_build', 'Wait for build parameter'),
            ('verify_navmesh', 'Verification parameter'),
            ('pre_bake_mtime', 'File save verification'),
        ]
        
        for keyword, desc in features:
            if keyword in content:
                print(f"✅ {desc} ({keyword})")
            else:
                print(f"❌ {desc} ({keyword}) NOT FOUND")
                all_ok = False
    
    # Test 4: Configuration example validation
    print_header("Test 4: Configuration Validation")
    
    auto_example = ue_pipeline / 'examples' / 'job_bake_navmesh_auto.json'
    if auto_example.exists():
        valid, data = check_json_valid(auto_example, "Auto-scale example")
        if valid and data:
            navmesh_config = data.get('navmesh_config', {})
            checks = [
                ('auto_scale' in navmesh_config and navmesh_config['auto_scale'] == True, 
                 'auto_scale enabled'),
                ('scale_margin' in navmesh_config, 'scale_margin configured'),
                ('min_scale' in navmesh_config, 'min_scale configured'),
                ('max_scale' in navmesh_config, 'max_scale configured'),
                ('wait_for_build' in navmesh_config, 'wait_for_build configured'),
                ('verify_navmesh' in navmesh_config, 'verify_navmesh configured'),
            ]
            
            for check, desc in checks:
                if check:
                    print(f"✅ Config: {desc}")
                else:
                    print(f"❌ Config: {desc} MISSING")
                    all_ok = False
    
    # Test 5: Documentation
    print_header("Test 5: Documentation")
    readme = ue_pipeline / 'NAVMESH_AUTOSCALE_README.md'
    if check_file_exists(readme, "Quick reference documentation"):
        content = readme.read_text(encoding='utf-8')
        print(f"   Documentation size: {len(content)} bytes")
        if len(content) > 1000:
            print(f"✅ Documentation appears complete")
        else:
            print(f"⚠️  Documentation may be incomplete")
    else:
        all_ok = False
    
    # Final summary
    print_header("Test Summary")
    if all_ok:
        print("✅ All tests passed!")
        print("\nNext steps:")
        print("1. Review the example configs in ue_pipeline/examples/")
        print("2. Update UE paths in examples to match your environment")
        print("3. Run a test bake:")
        print("   python ue_pipeline/run_bake_navmesh.py ue_pipeline/examples/job_bake_navmesh_auto.json")
        print("\n4. Check UE logs for NavMesh build status")
        print("5. Verify .umap and _BuiltData.uasset files are updated")
        return 0
    else:
        print("❌ Some tests failed. Please review the errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
