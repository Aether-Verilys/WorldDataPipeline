import unreal
import sys
import json
import os
import time
from pathlib import Path

print("[WorkerBakeNavMesh] Starting NavMesh bake job execution...")
print(f"[WorkerBakeNavMesh] Python version: {sys.version}")
print(f"[WorkerBakeNavMesh] Working directory: {os.getcwd()}")

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

# Get configuration parameters
auto_scale = navmesh_config.get("auto_scale", False)
location = navmesh_config.get("location", [0.0, 0.0, 0.0])
scale = navmesh_config.get("scale", [100.0, 100.0, 10.0])
maps = navmesh_config.get("maps", [])

# Auto-scale parameters
scale_margin = navmesh_config.get("scale_margin", 1.2)
min_scale = navmesh_config.get("min_scale", [20.0, 20.0, 5.0])
max_scale = navmesh_config.get("max_scale", [500.0, 500.0, 50.0])

# Agent physics parameters
agent_max_step_height = navmesh_config.get("agent_max_step_height", 50.0)
agent_max_jump_height = navmesh_config.get("agent_max_jump_height", 200.0)

# Build parameters
wait_for_build = navmesh_config.get("wait_for_build", True)
build_timeout = navmesh_config.get("build_timeout", 60)
verify_navmesh = navmesh_config.get("verify_navmesh", True)

if not maps:
    print("[WorkerBakeNavMesh] ERROR: No maps specified in navmesh_config")
    sys.exit(1)

print(f"[WorkerBakeNavMesh] Auto-scale enabled: {auto_scale}")
if auto_scale:
    print(f"[WorkerBakeNavMesh] Scale margin: {scale_margin}")
    print(f"[WorkerBakeNavMesh] Min scale: {min_scale}")
    print(f"[WorkerBakeNavMesh] Max scale: {max_scale}")
    print(f"[WorkerBakeNavMesh] Agent MaxStepHeight: {agent_max_step_height} cm")
    print(f"[WorkerBakeNavMesh] Agent MaxJumpHeight: {agent_max_jump_height} cm")
else:
    print(f"[WorkerBakeNavMesh] Manual location: {location}")
    print(f"[WorkerBakeNavMesh] Manual scale: {scale}")
print(f"[WorkerBakeNavMesh] Wait for build: {wait_for_build}")
print(f"[WorkerBakeNavMesh] Build timeout: {build_timeout}s")
print(f"[WorkerBakeNavMesh] Verify NavMesh: {verify_navmesh}")
print(f"[WorkerBakeNavMesh] Maps to process: {len(maps)}")

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from pre_process.add_navmesh_to_scene import NavMeshManager

try:
    manager = NavMeshManager()
    
    total_maps = len(maps)
    success_count = 0
    failed_count = 0
    failed_maps = []
    
    print("[WorkerBakeNavMesh] " + "="*60)
    print("[WorkerBakeNavMesh] Starting NavMesh Bake Process")
    print("[WorkerBakeNavMesh] " + "="*60)
    
    for i, map_path in enumerate(maps, 1):
        print(f"[WorkerBakeNavMesh] [{i}/{total_maps}] Processing: {map_path}")
        
        # Load map
        if not manager.load_map(map_path):
            print(f"[WorkerBakeNavMesh] ERROR: Failed to load map: {map_path}")
            failed_count += 1
            failed_maps.append({"map": map_path, "error": "Failed to load map"})
            continue
        
        # Record file modification time before bake
        level_path = map_path.replace("/Game/", "/Content/") + ".umap"
        project_path = Path(unreal.Paths.project_content_dir()).parent
        full_level_path = project_path / level_path.lstrip("/")
        pre_bake_mtime = None
        if full_level_path.exists():
            pre_bake_mtime = full_level_path.stat().st_mtime
            print(f"[WorkerBakeNavMesh] Level file tracked: {full_level_path}")
        
        # Add or configure NavMesh
        navmesh = None
        if auto_scale:
            print(f"[WorkerBakeNavMesh] Using auto-scale mode...")
            navmesh = manager.auto_scale_navmesh(
                margin=scale_margin,
                min_scale=min_scale,
                max_scale=max_scale,
                agent_max_step_height=agent_max_step_height,
                agent_max_jump_height=agent_max_jump_height
            )
        else:
            print(f"[WorkerBakeNavMesh] Using manual scale mode...")
            location_vec = unreal.Vector(location[0], location[1], location[2])
            scale_vec = unreal.Vector(scale[0], scale[1], scale[2])
            navmesh = manager.add_navmesh_bounds_volume(location_vec, scale_vec)
        
        if not navmesh:
            print(f"[WorkerBakeNavMesh] WARNING: NavMesh volume not created (may already exist)")
        
        # NavMesh auto-builds after adding NavMeshBoundsVolume, no manual rebuild needed
        print(f"[WorkerBakeNavMesh] NavMesh auto-building for {map_path}...")
        manager.rebuild_navmesh()  # Just logs a message
        
        # Wait for NavMesh build to complete
        if wait_for_build:
            print(f"[WorkerBakeNavMesh] Waiting for NavMesh build to complete...")
            build_success = manager.wait_for_navmesh_build(timeout_seconds=build_timeout)
            if not build_success:
                print(f"[WorkerBakeNavMesh] WARNING: NavMesh build timeout or failed")
        else:
            # Give it a moment even if not waiting
            time.sleep(2)
        
        # Save level
        print(f"[WorkerBakeNavMesh] Saving level: {map_path}")
        save_start = time.time()
        try:
            # Use LevelEditorSubsystem to save (recommended in UE 5.7+)
            level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            if level_editor:
                success = level_editor.save_current_level()
                save_elapsed = time.time() - save_start
                print(f"[WorkerBakeNavMesh] Level saved successfully ({save_elapsed:.2f}s)")
            else:
                # Fallback to EditorLevelLibrary (deprecated but works)
                unreal.EditorLevelLibrary.save_current_level()
                save_elapsed = time.time() - save_start
                print(f"[WorkerBakeNavMesh] Level saved successfully ({save_elapsed:.2f}s)")
            
            # Verify save by checking file modification time
            if full_level_path.exists():
                post_bake_mtime = full_level_path.stat().st_mtime
                if pre_bake_mtime and post_bake_mtime > pre_bake_mtime:
                    print(f"[WorkerBakeNavMesh] Save verified - file modified")
                elif pre_bake_mtime:
                    print(f"[WorkerBakeNavMesh] WARNING: File modification time unchanged")
            
        except Exception as e:
            print(f"[WorkerBakeNavMesh] ERROR: Failed to save level: {e}")
            failed_count += 1
            failed_maps.append({"map": map_path, "error": f"Failed to save: {e}"})
            continue
        
        # Verify NavMesh data
        if verify_navmesh:
            print(f"[WorkerBakeNavMesh] Verifying NavMesh data...")
            is_valid = manager.verify_navmesh_data()
            if is_valid:
                print(f"[WorkerBakeNavMesh] NavMesh verification passed")
            else:
                print(f"[WorkerBakeNavMesh] WARNING: NavMesh verification failed - may not have navigable areas")
        
        success_count += 1
        print(f"[WorkerBakeNavMesh] Completed: {map_path}")
        print("")
    
    print("[WorkerBakeNavMesh] " + "="*60)
    print("[WorkerBakeNavMesh] NavMesh Bake Process Complete")
    print("[WorkerBakeNavMesh] " + "="*60)
    print(f"[WorkerBakeNavMesh] Total maps: {total_maps}")
    print(f"[WorkerBakeNavMesh] Success: {success_count}")
    print(f"[WorkerBakeNavMesh] Failed: {failed_count}")
    
    if failed_maps:
        print("[WorkerBakeNavMesh] Failed maps details:")
        for failed in failed_maps:
            print(f"  - {failed['map']}: {failed['error']}")
    
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
