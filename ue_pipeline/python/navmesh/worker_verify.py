import unreal
import sys
import os
import time

_current_dir = os.path.dirname(os.path.abspath(__file__))
# Add workspace root to path for ue_pipeline imports
workspace_root = os.path.abspath(os.path.join(_current_dir, "..", "..", ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from ue_pipeline.python.core import logger, get_editor_world, get_level_editor_subsystem, get_navigation_system
from ue_pipeline.python.assets import save_current_level


def trigger_navmesh_rebuild(world) -> bool:
    """Trigger NavMesh rebuild and wait for completion"""
    try:
        logger.info("Triggering NavMesh rebuild...")
        
        # Get navigation system
        nav_sys = get_navigation_system(world)
        
        # Check initial build status
        if nav_sys.is_navigation_being_built(world):
            logger.info("Navigation is already being built")
        else:
            logger.info("Navigation not built yet")
        
        # Execute rebuild command
        editor_world = get_editor_world()
        logger.info("Executing RebuildNavigation command...")
        unreal.SystemLibrary.execute_console_command(editor_world, "RebuildNavigation")
        
        # Wait for rebuild to start and complete
        logger.info("Waiting for NavMesh rebuild to complete...")
        time.sleep(10)
        
        # Check final build status
        nav_sys = get_navigation_system(world)
        if nav_sys.is_navigation_being_built(world):
            logger.info("Navigation is being built")
            # Wait a bit more if still building
            max_wait = 30
            elapsed = 0
            while nav_sys.is_navigation_being_built(world) and elapsed < max_wait:
                time.sleep(2)
                elapsed += 2
                logger.info(f"Still building... ({elapsed}s)")
            
            if nav_sys.is_navigation_being_built(world):
                logger.warning("NavMesh build still in progress after timeout")
                return False
            else:
                logger.info("NavMesh build completed")
                return True
        else:
            logger.info("NavMesh build completed")
            return True
            
    except Exception as e:
        logger.error(f"Failed to trigger NavMesh rebuild: {e}")
        import traceback
        traceback.print_exc()
        return False


def main(argv=None) -> int:
    """Phase 2: Trigger NavMesh rebuild and verify after map is loaded via command line"""
    logger.info("Starting NavMesh rebuild and verification (Phase 2)...")
    
    argv = list(argv) if argv is not None else sys.argv
    
    # Get map path from command line or environment
    map_path = None
    if len(argv) > 1:
        map_path = argv[1]
    
    if not map_path:
        map_path = os.environ.get('UE_VERIFY_MAP_PATH')
    
    if not map_path:
        logger.warning("No map path provided for verification")
        return 0
    
    logger.info(f"Processing map: {map_path}")
    
    try:
        # Get world
        try:
            world = get_editor_world()
        except Exception as e:
            logger.error(f"Failed to get editor world: {e}")
            return 1
        
        # Trigger NavMesh rebuild
        rebuild_success = trigger_navmesh_rebuild(world)
        if not rebuild_success:
            logger.warning("NavMesh rebuild may not have completed successfully")
        
        # Now verify NavMesh data
        from pre_process.add_navmesh_to_scene import NavMeshManager
        
        manager = NavMeshManager()
        
        logger.info("Verifying NavMesh data...")
        is_valid = manager.verify_navmesh_data()
        
        if is_valid:
            logger.info("✓ NavMesh verification passed - navigable areas detected")
        else:
            logger.warning("✗ NavMesh verification failed - no navigable areas found")
        
        # Save the level after rebuild
        logger.info("Saving level after NavMesh rebuild...")
        save_start = time.time()
        try:
            save_current_level()
            save_elapsed = time.time() - save_start
            logger.info(f"Level saved successfully ({save_elapsed:.2f}s)")
        except Exception as e:
            logger.error(f"Failed to save level: {e}")
            return 1
        
        if is_valid:
            logger.info("Phase 2 completed successfully - NavMesh rebuilt, verified and saved")
            return 0
        else:
            logger.warning("Phase 2 completed with warnings - NavMesh saved but verification failed")
            return 1
            
    except Exception as e:
        logger.error(f"Failed to verify NavMesh: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
