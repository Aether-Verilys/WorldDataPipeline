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

# Parse command line arguments or environment variable
manifest_path = None

# First try environment variable (for headless mode)
manifest_path = os.environ.get('UE_MANIFEST_PATH')

# Fallback to command line arguments
if not manifest_path:
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--manifest="):
            manifest_path = arg.split("=", 1)[1]
        elif arg == "--manifest" and i + 1 < len(sys.argv):
            manifest_path = sys.argv[i + 1]

if not manifest_path:
    print("[WorkerExport] ERROR: No manifest path provided")
    print("[WorkerExport] Usage: Set UE_MANIFEST_PATH environment variable or use --manifest=<path>")
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
sequence_path = manifest.get("sequence")
camera_export_config = manifest.get("camera_export", {})

print(f"[WorkerExport] Job ID: {job_id}")
print(f"[WorkerExport] Job Type: {job_type}")
print(f"[WorkerExport] Sequence: {sequence_path}")

# Print actual UE project directory
try:
    from pathlib import Path
    # Use project_content_dir().parent to get real project root (same as worker_bake_navmesh.py)
    project_content_dir = unreal.Paths.project_content_dir()
    project_path = Path(project_content_dir).parent
    project_saved_dir = project_path / "Saved"
    
    print(f"[WorkerExport] ========== Current UE Project Info ==========")
    print(f"[WorkerExport] Project Root: {project_path}")
    print(f"[WorkerExport] Content Directory: {project_content_dir}")
    print(f"[WorkerExport] Saved Directory: {project_saved_dir}")
    print(f"[WorkerExport] =============================================")
except Exception as e:
    print(f"[WorkerExport] WARNING: Failed to get project directories: {e}")

# Validate job type
if job_type != "export":
    print(f"[WorkerExport] ERROR: Invalid job type '{job_type}', expected 'export'")
    sys.exit(1)

if not sequence_path:
    print("[WorkerExport] ERROR: No sequence specified in manifest")
    sys.exit(1)

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
                "sequence": sequence_path,
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
