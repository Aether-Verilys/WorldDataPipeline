import unreal
import sys
import json
import os

print("[WorkerBakeNavMesh] Starting NavMesh bake job execution...")

manifest_path = None

manifest_path = os.environ.get("UE_NAVMESH_MANIFEST")

if not manifest_path:
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--manifest="):
            manifest_path = arg.split("=", 1)[1]
        elif arg == "--manifest" and i + 1 < len(sys.argv):
            manifest_path = sys.argv[i + 1]

if not manifest_path:
    print("[WorkerBakeNavMesh] ERROR: No manifest path provided")
    print(f"[WorkerBakeNavMesh] sys.argv: {sys.argv}")
    print(f"[WorkerBakeNavMesh] Environment vars: UE_NAVMESH_MANIFEST={os.environ.get('UE_NAVMESH_MANIFEST')}")
    sys.exit(1)

print(f"[WorkerBakeNavMesh] Manifest: {manifest_path}")

try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
except Exception as e:
    print(f"[WorkerBakeNavMesh] ERROR: Failed to read manifest: {e}")
    sys.exit(1)

job_id = manifest.get("job_id", "unknown")
job_type = manifest.get("job_type", "unknown")

print(f"[WorkerBakeNavMesh] Job ID: {job_id}")
print(f"[WorkerBakeNavMesh] Job Type: {job_type}")

if job_type != "bake_navmesh":
    print(f"[WorkerBakeNavMesh] ERROR: Invalid job type '{job_type}', expected 'bake_navmesh'")
    sys.exit(1)

ue_config = manifest.get("ue_config", {})
navmesh_config = manifest.get("navmesh_config", {})

location = navmesh_config.get("location", [0.0, 0.0, 0.0])
scale = navmesh_config.get("scale", [100.0, 100.0, 10.0])
maps = navmesh_config.get("maps", [])

if not maps:
    print("[WorkerBakeNavMesh] ERROR: No maps specified in navmesh_config")
    sys.exit(1)

print(f"[WorkerBakeNavMesh] Location: {location}")
print(f"[WorkerBakeNavMesh] Scale: {scale}")
print(f"[WorkerBakeNavMesh] Maps to process: {len(maps)}")

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from pre_process.add_navmesh_to_scene import NavMeshManager

try:
    manager = NavMeshManager()
    
    location_vec = unreal.Vector(location[0], location[1], location[2])
    scale_vec = unreal.Vector(scale[0], scale[1], scale[2])
    
    total_maps = len(maps)
    success_count = 0
    failed_count = 0
    
    print("[WorkerBakeNavMesh] " + "="*60)
    print("[WorkerBakeNavMesh] Starting NavMesh Bake Process")
    print("[WorkerBakeNavMesh] " + "="*60)
    
    for i, map_path in enumerate(maps, 1):
        print(f"[WorkerBakeNavMesh] [{i}/{total_maps}] Processing: {map_path}")
        
        if not manager.load_map(map_path):
            print(f"[WorkerBakeNavMesh] ERROR: Failed to load map: {map_path}")
            failed_count += 1
            continue
        
        navmesh = manager.add_navmesh_bounds_volume(location_vec, scale_vec)
        if not navmesh:
            print(f"[WorkerBakeNavMesh] WARNING: NavMesh already exists or failed to add")
        
        print(f"[WorkerBakeNavMesh] Rebuilding NavMesh for {map_path}...")
        manager.rebuild_navmesh()
        
        unreal.EditorLevelLibrary.save_current_level()
        print(f"[WorkerBakeNavMesh] Level saved: {map_path}")
        
        success_count += 1
        print(f"[WorkerBakeNavMesh] Completed: {map_path}")
        print("")
    
    print("[WorkerBakeNavMesh] " + "="*60)
    print("[WorkerBakeNavMesh] NavMesh Bake Process Complete")
    print("[WorkerBakeNavMesh] " + "="*60)
    print(f"[WorkerBakeNavMesh] Total maps: {total_maps}")
    print(f"[WorkerBakeNavMesh] Success: {success_count}")
    print(f"[WorkerBakeNavMesh] Failed: {failed_count}")
    print("[WorkerBakeNavMesh] " + "="*60)
    
    if failed_count > 0:
        print(f"[WorkerBakeNavMesh] WARNING: {failed_count} map(s) failed")
        sys.exit(1)
    else:
        print("[WorkerBakeNavMesh] All maps processed successfully")
        sys.exit(0)
        
except Exception as e:
    print(f"[WorkerBakeNavMesh] ERROR: Failed to execute NavMesh bake job: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
