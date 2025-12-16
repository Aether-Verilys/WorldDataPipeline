import unreal
import sys
import os
import time
import traceback
import json

print("=" * 60)
print("[TestMapRun] Map Load and Run Test Starting")
print("=" * 60)

# Get parameters from environment variables
manifest_path = os.environ.get('UE_MANIFEST_PATH')
run_seconds_str = os.environ.get('UE_RUN_SECONDS', '10')

print(f"[TestMapRun] Manifest from env: {manifest_path}")
print(f"[TestMapRun] Run seconds from env: {run_seconds_str}")

if not manifest_path:
    print("[TestMapRun] ERROR: UE_MANIFEST_PATH environment variable not set")
    sys.exit(1)

try:
    run_seconds = float(run_seconds_str)
except:
    run_seconds = 10.0

print(f"[TestMapRun] Will run for {run_seconds} seconds")

try:
    # Read manifest
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    map_path = manifest.get('map')
    if not map_path:
        print("[TestMapRun] ERROR: No 'map' field in manifest")
        sys.exit(1)
    
    print(f"[TestMapRun] Loading map: {map_path}")
    
    # Load map
    level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level_editor:
        print("[TestMapRun] ERROR: Cannot get LevelEditorSubsystem")
        sys.exit(1)
    
    success = level_editor.load_level(map_path)
    if not success:
        print(f"[TestMapRun] FAILED: Could not load map: {map_path}")
        sys.exit(1)
    
    print(f"[TestMapRun] SUCCESS: Map loaded!")
    time.sleep(2)
    
    # Start PIE
    print(f"[TestMapRun] Starting PIE for {run_seconds} seconds...")
    level_editor.editor_request_begin_play()
    
    # Wait for PIE to start
    print("[TestMapRun] Waiting for PIE to start...")
    for i in range(20):  # Wait up to 10 seconds
        if level_editor.is_in_play_in_editor_session():
            print("[TestMapRun] PIE started!")
            break
        time.sleep(0.5)
    else:
        print("[TestMapRun] WARNING: PIE did not start in time")
    
    # Run for specified duration
    start_time = time.time()
    while time.time() - start_time < run_seconds:
        elapsed = time.time() - start_time
        if int(elapsed) % 2 == 0 and elapsed - int(elapsed) < 0.1:
            print(f"[TestMapRun] Running... {int(elapsed)}/{int(run_seconds)} seconds")
        time.sleep(0.1)
    
    # Stop PIE
    print("[TestMapRun] Stopping PIE...")
    level_editor.editor_request_end_play()
    time.sleep(1)
    
    print("=" * 60)
    print("[TestMapRun] SUCCESS: Test completed!")
    print(f"[TestMapRun] - Loaded map: {map_path}")
    print(f"[TestMapRun] - Ran scene for {run_seconds} seconds")
    print("=" * 60)
    
    sys.exit(0)

except Exception as e:
    print(f"[TestMapRun] ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
