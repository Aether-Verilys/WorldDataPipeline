import unreal
import sys
import time

print("[TestMapRun] Starting test...")

# Hardcoded for simplicity - user can change this
manifest_path = r"D:\WorldDataPipeline\ue_pipeline\examples\test_map_only.json"
map_path = "/Game/Maps/Lvl_FirstPerson"

print(f"[TestMapRun] Loading map: {map_path}")

# Load map
level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
success = level_editor.load_level(map_path)

if not success:
    print(f"[TestMapRun] FAILED: Could not load map")
    sys.exit(1)

print(f"[TestMapRun] SUCCESS: Map loaded!")
time.sleep(2)

# Start PIE
print("[TestMapRun] Starting PIE...")
level_editor.editor_request_begin_play()

# Wait for PIE to start
time.sleep(2)

print("[TestMapRun] PIE started successfully!")
print("[TestMapRun] UE will remain open. Manually close when done testing.")
print("[TestMapRun] Script execution complete.")

# Script ends here - UE stays open with PIE running
