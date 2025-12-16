import unreal
import sys
import os
import time

print("[SimpleTest] Starting...")
print("[SimpleTest] Python version:", sys.version)

# Hardcoded manifest path for testing
manifest_path = r"D:\WorldDataPipeline\ue_pipeline\examples\test_map_only.json"
print(f"[SimpleTest] Manifest: {manifest_path}")

# Read manifest
import json
with open(manifest_path, 'r') as f:
    manifest = json.load(f)

map_path = manifest['map']
print(f"[SimpleTest] Loading map: {map_path}")

# Load map
level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
success = level_editor.load_level(map_path)

if success:
    print(f"[SimpleTest] SUCCESS: Map loaded!")
    time.sleep(1)
    
    # Start PIE
    print("[SimpleTest] Starting PIE...")
    level_editor.editor_request_begin_play()
    
    # Wait
    print("[SimpleTest] Running for 5 seconds...")
    time.sleep(5)
    
    # Stop PIE
    print("[SimpleTest] Stopping PIE...")
    level_editor.editor_request_end_play()
    
    print("[SimpleTest] Test complete!")
    sys.exit(0)
else:
    print(f"[SimpleTest] FAILED: Could not load map")
    sys.exit(1)
