"""
Add NavMesh to UE scene/level
"""
import unreal


class NavMeshManager:
    """Utility class to add and configure NavMesh in levels"""
    
    def __init__(self):
        self.editor_subsystem = unreal.UnrealEditorSubsystem()
        self.editor_actor_subsystem = unreal.EditorActorSubsystem()
    
    def load_map(self, map_package_path):
        """
        Load a map by package path
        
        Args:
            map_package_path: Package path like '/Game/Maps/MyLevel'
            
        Returns:
            bool: True if successful
        """
        try:
            success = self.editor_subsystem.load_level(map_package_path)
            if success:
                unreal.log(f"Loaded map: {map_package_path}")
            else:
                unreal.log_warning(f"Failed to load map: {map_package_path}")
            return success
        except Exception as e:
            unreal.log_error(f"Error loading map {map_package_path}: {str(e)}")
            return False
    
    def check_navmesh_exists(self):
        """
        Check if NavMeshBoundsVolume already exists in current level
        
        Returns:
            unreal.NavMeshBoundsVolume or None
        """
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        
        for actor in all_actors:
            if isinstance(actor, unreal.NavMeshBoundsVolume):
                unreal.log(f"Found existing NavMeshBoundsVolume: {actor.get_name()}")
                return actor
        
        return None
    
    def add_navmesh_bounds_volume(self, location=None, scale=None):
        """
        Add a NavMeshBoundsVolume to the current level
        
        Args:
            location: unreal.Vector or tuple (x, y, z), default (0, 0, 0)
            scale: unreal.Vector or tuple (x, y, z), default (10, 10, 10)
            
        Returns:
            unreal.NavMeshBoundsVolume or None
        """
        # Check if already exists
        existing = self.check_navmesh_exists()
        if existing:
            unreal.log_warning("NavMeshBoundsVolume already exists in this level")
            return existing
        
        # Default location and scale
        if location is None:
            location = unreal.Vector(0.0, 0.0, 0.0)
        elif isinstance(location, (tuple, list)):
            location = unreal.Vector(location[0], location[1], location[2])
        
        if scale is None:
            scale = unreal.Vector(10.0, 10.0, 10.0)
        elif isinstance(scale, (tuple, list)):
            scale = unreal.Vector(scale[0], scale[1], scale[2])
        
        try:
            # Spawn NavMeshBoundsVolume
            navmesh_volume = self.editor_actor_subsystem.spawn_actor_from_class(
                unreal.NavMeshBoundsVolume,
                location
            )
            
            if navmesh_volume:
                # Set scale
                navmesh_volume.set_actor_scale3d(scale)
                
                unreal.log(f"✓ Added NavMeshBoundsVolume at {location}")
                unreal.log(f"  Scale: {scale}")
                unreal.log(f"  Actor: {navmesh_volume.get_name()}")
                
                # Save level
                unreal.EditorLevelLibrary.save_current_level()
                
                return navmesh_volume
            else:
                unreal.log_error("Failed to spawn NavMeshBoundsVolume")
                return None
                
        except Exception as e:
            unreal.log_error(f"Error adding NavMeshBoundsVolume: {str(e)}")
            return None
    
    def configure_navmesh_settings(self, navmesh_volume, settings_dict):
        """
        Configure NavMeshBoundsVolume settings
        
        Args:
            navmesh_volume: The NavMeshBoundsVolume actor
            settings_dict: Dictionary of settings
                          e.g., {'supported_agents': [...]}
        """
        try:
            for prop_name, prop_value in settings_dict.items():
                if navmesh_volume.has_property(prop_name):
                    navmesh_volume.set_editor_property(prop_name, prop_value)
                    unreal.log(f"  Set {prop_name} = {prop_value}")
                else:
                    unreal.log_warning(f"  Property '{prop_name}' not found")
            
            unreal.EditorLevelLibrary.save_current_level()
            
        except Exception as e:
            unreal.log_error(f"Error configuring NavMesh: {str(e)}")
    
    def batch_add_navmesh_to_maps(self, map_list, location=None, scale=None):
        """
        Batch add NavMesh to multiple maps
        
        Args:
            map_list: List of map package paths
            location: NavMesh location
            scale: NavMesh scale
            
        Returns:
            dict: Results with success/failure counts
        """
        results = {
            'total': len(map_list),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'failed_maps': []
        }
        
        unreal.log("=" * 60)
        unreal.log("Batch Adding NavMesh to Maps")
        unreal.log("=" * 60)
        unreal.log(f"Total maps: {len(map_list)}")
        unreal.log(f"Location: {location}")
        unreal.log(f"Scale: {scale}")
        unreal.log("")
        
        for i, map_path in enumerate(map_list, 1):
            unreal.log(f"[{i}/{len(map_list)}] Processing: {map_path}")
            
            # Load map
            if not self.load_map(map_path):
                results['failed'] += 1
                results['failed_maps'].append(map_path)
                continue
            
            # Add NavMesh
            navmesh = self.add_navmesh_bounds_volume(location, scale)
            if navmesh:
                # Check if it was newly created or already existed
                if self.check_navmesh_exists():
                    results['success'] += 1
                    unreal.log(f"  ✓ NavMesh added/verified")
            else:
                results['failed'] += 1
                results['failed_maps'].append(map_path)
                unreal.log_warning(f"  ✗ Failed to add NavMesh")
            
            unreal.log("")
        
        unreal.log("=" * 60)
        unreal.log("Batch Add NavMesh Complete")
        unreal.log(f"Success: {results['success']}/{results['total']}")
        unreal.log(f"Failed: {results['failed']}/{results['total']}")
        if results['failed_maps']:
            unreal.log("Failed maps:")
            for map_path in results['failed_maps']:
                unreal.log(f"  - {map_path}")
        unreal.log("=" * 60)
        
        return results
    
    def rebuild_navmesh(self):
        """Rebuild navigation data for current level"""
        try:
            unreal.log("Rebuilding NavMesh...")
            unreal.NavigationSystemLibrary.rebuild_navigation_data(
                unreal.EditorLevelLibrary.get_editor_world()
            )
            unreal.log("✓ NavMesh rebuilt")
        except Exception as e:
            unreal.log_error(f"Error rebuilding NavMesh: {str(e)}")


def example_usage():
    """Example: Add NavMesh to multiple maps"""
    
    # Example map list
    map_list = [
        '/Game/Maps/Level01',
        '/Game/Maps/Level02',
    ]
    
    # NavMesh configuration
    location = (0.0, 0.0, 0.0)
    scale = (100.0, 100.0, 10.0)  # Large area coverage
    
    manager = NavMeshManager()
    results = manager.batch_add_navmesh_to_maps(map_list, location, scale)
    
    # Rebuild navmesh for the last loaded map
    manager.rebuild_navmesh()
    
    return results


if __name__ == "__main__":
    # Uncomment to run example
    # example_usage()
    pass
