import unreal
import sys
import json

# Import utilities
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
import export_UE_camera

print("[WorkerExport] Starting camera export job execution...")

# Parse command line arguments
manifest_path = None
for i, arg in enumerate(sys.argv):
    if arg.startswith("--manifest="):
        manifest_path = arg.split("=", 1)[1]
    elif arg == "--manifest" and i + 1 < len(sys.argv):
        manifest_path = sys.argv[i + 1]

if not manifest_path:
    print("[WorkerExport] ERROR: No manifest path provided")
    sys.exit(1)

print(f"[WorkerExport] Manifest: {manifest_path}")

# Read manifest
try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
except Exception as e:
    print(f"[WorkerExport] ERROR: Failed to read manifest: {e}")
    sys.exit(1)

job_id = manifest.get("job_id", "unknown")
job_type = manifest.get("job_type", "unknown")
recorded_sequence = manifest.get("sequence")
camera_export_config = manifest.get("camera_export", {})

print(f"[WorkerExport] Job ID: {job_id}")
print(f"[WorkerExport] Job Type: {job_type}")
print(f"[WorkerExport] Recorded Sequence: {recorded_sequence}")

# Validate job type
if job_type != "export":
    print(f"[WorkerExport] ERROR: Invalid job type '{job_type}', expected 'export'")
    sys.exit(1)

if not recorded_sequence:
    print("[WorkerExport] ERROR: No sequence specified in manifest")
    sys.exit(1)

# Build subscene path
# Example: /Game/CameraController/2025-12-08/Scene_1_10
# -> /Game/CameraController/2025-12-08/Scene_1_10_Subscenes/BP_FirstPersonCharacter0_Scene_1_10
path_parts = recorded_sequence.rsplit('/', 1)
if len(path_parts) == 2:
    parent_path = path_parts[0]
    sequence_name = path_parts[1]
else:
    parent_path = ""
    sequence_name = recorded_sequence

binding_transform = camera_export_config.get("binding_transform", "BP_FirstPersonCharacter0")
subscene_folder = f"{sequence_name}_Subscenes"
subscene_name = f"{binding_transform}_{sequence_name}"

if parent_path:
    subscene_path = f"{parent_path}/{subscene_folder}/{subscene_name}"
else:
    subscene_path = f"{subscene_folder}/{subscene_name}"

print(f"[WorkerExport] Subscene Path: {subscene_path}")
print(f"[WorkerExport] Binding Transform: {binding_transform}")

# Update manifest with subscene path for export_UE_camera
manifest["sequence"] = subscene_path

# Execute export job
try:
    print("[WorkerExport] Starting camera export...")
    result = export_UE_camera.export_camera_from_manifest(manifest)
    
    if result.get("status") == "success":
        print("[WorkerExport] ✓ Camera export completed successfully")
        print(f"[WorkerExport] Sequence: {result.get('sequence')}")
        print(f"[WorkerExport] Output directory: {result.get('output_dir')}")
        print(f"[WorkerExport] Extrinsic CSV: {result.get('extrinsic_csv')}")
        print(f"[WorkerExport] Transform CSV: {result.get('transform_csv')}")
        
        # Log to job_history.log
        try:
            import datetime
            log_entry = {
                "job_type": "export",
                "job_id": job_id,
                "recorded_sequence": recorded_sequence,
                "subscene_sequence": subscene_path,
                "output_path": result.get('output_dir'),
                "extrinsic_csv": result.get('extrinsic_csv'),
                "transform_csv": result.get('transform_csv'),
                "timestamp": datetime.datetime.now().isoformat(timespec='seconds')
            }
            # Use path relative to script location
            script_dir = os.path.dirname(os.path.abspath(__file__))
            pipeline_dir = os.path.dirname(script_dir)
            log_file = os.path.join(pipeline_dir, "job_history.log")
            with open(log_file, "a", encoding="utf-8") as logf:
                logf.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as logerr:
            print(f"[WorkerExport] WARNING: Failed to write job_history.log: {logerr}")
        
        sys.exit(0)
    else:
        print(f"[WorkerExport] ERROR: Export returned unexpected status: {result}")
        sys.exit(1)
        
except Exception as e:
    print(f"[WorkerExport] ERROR: Failed to execute export job: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
