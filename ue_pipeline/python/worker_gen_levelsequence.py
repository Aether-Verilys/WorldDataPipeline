import json
import os
import sys
import time
from typing import Optional

import unreal

# Ensure local modules resolve
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import gen_levelsequence
import level_launcher

print("[WorkerGenLevelSequence] Starting job execution...")


def _parse_manifest_path(argv) -> Optional[str]:
    manifest_path = None
    for i, arg in enumerate(argv):
        if arg.startswith("--manifest="):
            manifest_path = arg.split("=", 1)[1]
        elif arg == "--manifest" and i + 1 < len(argv):
            manifest_path = argv[i + 1]
    return manifest_path


def _wait_for_pie(timeout_seconds: float = 30.0) -> unreal.World:
    start = time.time()
    while time.time() - start < timeout_seconds:
        if level_launcher.is_pie_playing():
            world = level_launcher.get_pie_world()
            if world:
                try:
                    if hasattr(world, "has_begun_play"):
                        if world.has_begun_play():
                            return world
                    else:
                        return world
                except Exception:
                    return world
        time.sleep(0.1)
    raise RuntimeError("Timeout waiting for PIE world")


def main() -> int:
    manifest_path = _parse_manifest_path(sys.argv)
    if not manifest_path:
        print("[WorkerGenLevelSequence] ERROR: No manifest path provided")
        return 1

    print(f"[WorkerGenLevelSequence] Manifest: {manifest_path}")

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"[WorkerGenLevelSequence] ERROR: Failed to read manifest: {e}")
        return 1

    job_id = manifest.get("job_id", "unknown")
    job_type = manifest.get("job_type", "unknown")
    map_path = manifest.get("map")

    print(f"[WorkerGenLevelSequence] Job ID:   {job_id}")
    print(f"[WorkerGenLevelSequence] Job Type: {job_type}")

    if job_type != "gen_levelsequence":
        print(f"[WorkerGenLevelSequence] ERROR: Invalid job type '{job_type}', expected 'gen_levelsequence'")
        return 1

    prefer_pie = bool(manifest.get("prefer_pie", True))

    # Load map if provided
    if map_path:
        try:
            level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            print(f"[WorkerGenLevelSequence] Loading map: {map_path}")
            if not level_editor.load_level(map_path):
                print("[WorkerGenLevelSequence] ERROR: Failed to load map")
                return 1
            print("[WorkerGenLevelSequence] ✓ Map loaded")
        except Exception as e:
            print(f"[WorkerGenLevelSequence] ERROR: Exception loading map: {e}")
            return 1

    # Optionally run in PIE for runtime NavSystem
    level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    started_pie = False
    try:
        if prefer_pie:
            try:
                print("[WorkerGenLevelSequence] Starting PIE...")
                level_editor.editor_request_begin_play()
                _wait_for_pie(timeout_seconds=30.0)
                started_pie = True
                print("[WorkerGenLevelSequence] ✓ PIE ready")
            except Exception as e:
                print(f"[WorkerGenLevelSequence] WARNING: PIE not available, falling back to editor world: {e}")
                manifest["prefer_pie"] = False

        print("[WorkerGenLevelSequence] Generating LevelSequence from NavMesh...")
        result = gen_levelsequence.generate_nav_camera_sequence_from_manifest(manifest)

        if result.get("status") == "success":
            print("[WorkerGenLevelSequence] ✓ Generation completed")
            print(f"[WorkerGenLevelSequence] Sequence: {result.get('sequence')}")
            return 0

        print(f"[WorkerGenLevelSequence] ERROR: Unexpected result: {result}")
        return 1

    except Exception as e:
        print(f"[WorkerGenLevelSequence] ERROR: Failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        if started_pie:
            try:
                print("[WorkerGenLevelSequence] Stopping PIE...")
                level_editor.editor_request_end_play()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
