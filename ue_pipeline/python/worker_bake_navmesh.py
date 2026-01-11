import unreal
import sys
import os
import time
from pathlib import Path

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import ue_api
from worker_common import load_json as _load_json, resolve_manifest_path_from_env as _resolve_manifest_path_from_env
from logger import logger
from assets_manager import save_current_level


def main(argv=None) -> int:
    logger.info("Starting NavMesh bake job execution...")
    # logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")

    argv = list(argv) if argv is not None else sys.argv

    env_key = "UE_NAVMESH_MANIFEST"
    manifest_path = _resolve_manifest_path_from_env(env_key, argv)
    if not manifest_path:
        logger.error("No manifest path provided")
        logger.info(f"sys.argv: {sys.argv}")
        logger.info(f"Environment vars: {env_key}={os.environ.get(env_key)}")
        return 1

    logger.info(f"Manifest: {manifest_path}")

    try:
        manifest = _load_json(manifest_path)
    except Exception as e:
        logger.error(f"Failed to read manifest: {e}")
        return 1

    job_id = manifest.get("job_id", "unknown")
    job_type = manifest.get("job_type", "unknown")

    logger.info(f"Job ID: {job_id}")
    logger.info(f"Job Type: {job_type}")

    if job_type != "bake_navmesh":
        logger.error(f"Invalid job type '{job_type}', expected 'bake_navmesh'")
        return 1

    navmesh_config = manifest.get("navmesh_config", {})

    # Get configuration parameters
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
        logger.error("No maps specified in navmesh_config")
        return 1

    logger.info(f"Scale margin: {scale_margin}")
    logger.info(f"Min scale: {min_scale}")
    logger.info(f"Max scale: {max_scale}")
    logger.info(f"Agent MaxStepHeight: {agent_max_step_height} cm")
    logger.info(f"Agent MaxJumpHeight: {agent_max_jump_height} cm")
    logger.info(f"Wait for build: {wait_for_build}")
    logger.info(f"Build timeout: {build_timeout}s")
    logger.info(f"Verify NavMesh: {verify_navmesh}")
    logger.info(f"Maps to process: {len(maps)}")

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

        logger.info("=" * 60)
        logger.info("Starting NavMesh Bake Process")
        logger.info("=" * 60)

        for i, map_path in enumerate(maps, 1):
            logger.info(f"[{i}/{total_maps}] Processing: {map_path}")

            # Load map
            if not ue_api.load_map(map_path):
                logger.error(f"Failed to load map: {map_path}")
                failed_count += 1
                failed_maps.append({"map": map_path, "error": "Failed to load map"})
                continue

            # Count StaticMeshActor instances
            logger.info("Counting StaticMeshActors...")
            mesh_count = manager.count_static_mesh_actors()
            is_low_mesh = mesh_count < 50
            logger.info(f"StaticMeshActor count: {mesh_count}")
            logger.info(f"LowMesh status: {is_low_mesh}")

            # Record file modification time before bake
            level_path = map_path.replace("/Game/", "/Content/") + ".umap"
            project_path = Path(unreal.Paths.project_content_dir()).parent
            full_level_path = project_path / level_path.lstrip("/")
            pre_bake_mtime = None
            if full_level_path.exists():
                pre_bake_mtime = full_level_path.stat().st_mtime
                logger.info(f"Level file tracked: {full_level_path}")

            # Add or configure NavMesh
            logger.info("Using auto-scale mode...")
            navmesh = manager.auto_scale_navmesh(
                margin=scale_margin,
                min_scale=min_scale,
                max_scale=max_scale,
                agent_max_step_height=agent_max_step_height,
                agent_max_jump_height=agent_max_jump_height,
            )

            if not navmesh:
                logger.warning("NavMesh volume not created (may already exist)")
            else:
                logger.info("NavMeshBoundsVolume added successfully")

            # Phase 1: Only add volume and save, don't wait for build
            # Build will be triggered in Phase 2 by reloading the map with cmd
            logger.info("Phase 1 mode: Skipping build wait, will be triggered in Phase 2")

            # Save level
            logger.info(f"Saving level: {map_path}")
            save_start = time.time()
            try:
                save_current_level()
                save_elapsed = time.time() - save_start
                logger.info(f"Level saved successfully ({save_elapsed:.2f}s)")

                # Verify save by checking file modification time
                if full_level_path.exists():
                    post_bake_mtime = full_level_path.stat().st_mtime
                    if pre_bake_mtime and post_bake_mtime > pre_bake_mtime:
                        logger.info("Save verified - file modified")
                    elif pre_bake_mtime:
                        logger.warning("File modification time unchanged")

            except Exception as e:
                logger.error(f"Failed to save level: {e}")
                failed_count += 1
                failed_maps.append({"map": map_path, "error": f"Failed to save: {e}"})
                continue

            success_count += 1
            logger.info(f"Completed: {map_path}")

            # Output lowMesh status for this map
            logger.info(f"Map metadata: mesh_count={mesh_count}, low_mesh={is_low_mesh}")
            logger.plain("")

        logger.info("=" * 60)
        logger.info("NavMesh Bake Process Complete")
        logger.info("=" * 60)
        logger.info(f"Total maps: {total_maps}")
        logger.info(f"Success: {success_count}")
        logger.info(f"Failed: {failed_count}")

        if failed_maps:
            logger.info("Failed maps details:")
            for failed in failed_maps:
                logger.plain(f"  - {failed['map']}: {failed['error']}")

        logger.info("=" * 60)

        if failed_count > 0:
            logger.warning(f"{failed_count} map(s) failed")
            return 1
        else:
            logger.info("All maps processed successfully")
            return 0

    except Exception as e:
        logger.error(f"Failed to execute NavMesh bake job: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
