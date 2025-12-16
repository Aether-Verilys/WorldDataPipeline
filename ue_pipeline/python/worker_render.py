
import unreal
import sys
import json

# 修正模块加载路径，确保 rendering.py 可用
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
import rendering

print("[WorkerRender] Starting render job execution...")

# Parse command line arguments or environment variable
manifest_path = None

# Try environment variable first (preferred for -ExecutePythonScript)
manifest_path = os.environ.get("UE_RENDER_MANIFEST")

# Fall back to command line arguments
if not manifest_path:
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--manifest="):
            manifest_path = arg.split("=", 1)[1]
        elif arg == "--manifest" and i + 1 < len(sys.argv):
            manifest_path = sys.argv[i + 1]

if not manifest_path:
    print("[WorkerRender] ERROR: No manifest path provided")
    print(f"[WorkerRender] sys.argv: {sys.argv}")
    print(f"[WorkerRender] Environment vars: UE_RENDER_MANIFEST={os.environ.get('UE_RENDER_MANIFEST')}")
    sys.exit(1)

print(f"[WorkerRender] Manifest: {manifest_path}")

# Read manifest
try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
except Exception as e:
    print(f"[WorkerRender] ERROR: Failed to read manifest: {e}")
    sys.exit(1)

job_id = manifest.get("job_id", "unknown")
job_type = manifest.get("job_type", "unknown")
sequence_path = manifest.get("sequence")

print(f"[WorkerRender] Job ID: {job_id}")
print(f"[WorkerRender] Job Type: {job_type}")
print(f"[WorkerRender] Sequence: {sequence_path}")

# Validate job type
if job_type != "render":
    print(f"[WorkerRender] ERROR: Invalid job type '{job_type}', expected 'render'")
    sys.exit(1)

if not sequence_path:
    print("[WorkerRender] ERROR: No sequence specified in manifest")
    sys.exit(1)

# Execute render job
try:
    print("[WorkerRender] Starting render job...")
    result = rendering.render_sequence_from_manifest(manifest)
    
    if result.get("status") == "started":
        print("[WorkerRender] ✓ Render job started successfully")
        print(f"[WorkerRender] Sequence: {result.get('sequence')}")
        print(f"[WorkerRender] Job Name: {result.get('job_name')}")
        print(f"[WorkerRender] Output: {result.get('output_directory')}")
        print("[WorkerRender] Note: Render will continue in background process")
        sys.exit(0)
    elif result.get("status") == "skipped":
        print(f"[WorkerRender] Job skipped: {result.get('reason')}")
        sys.exit(0)
    else:
        print(f"[WorkerRender] ERROR: Unknown result status: {result}")
        sys.exit(1)
        
except Exception as e:
    print(f"[WorkerRender] ERROR: Failed to execute render job: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
