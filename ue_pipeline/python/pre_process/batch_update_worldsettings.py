"""
Batch update WorldSettings GameMode for multiple UE maps
Override default GameMode with project-specific GameMode
"""
import os
import unreal


class WorldSettingsUpdater:
    """Utility class to batch update WorldSettings GameMode"""
    
    def __init__(self):
        self.editor_subsystem = unreal.UnrealEditorSubsystem()
        self.editor_asset_subsystem = unreal.EditorAssetSubsystem()
    
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
    
    def get_world_settings(self):
        """
        Get WorldSettings actor from current level
        
        Returns:
            unreal.WorldSettings or None
        """
        world = unreal.EditorLevelLibrary.get_editor_world()
        if not world:
            unreal.log_error("Failed to get editor world")
            return None
        
        world_settings = unreal.GameplayStatics.get_world_settings(world)
        return world_settings
    
    def update_gamemode(self, gamemode_path):
        """
        Update WorldSettings GameMode override
        
        Args:
            gamemode_path: UE asset path to GameMode Blueprint
                          e.g., '/Game/Blueprints/MyGameMode.MyGameMode_C'
        
        Returns:
            bool: True if successful
        """
        world_settings = self.get_world_settings()
        if not world_settings:
            return False
        
        try:
            # Load the GameMode asset
            gamemode_class = unreal.EditorAssetLibrary.load_asset(gamemode_path)
            if not gamemode_class:
                unreal.log_error(f"  Failed to load GameMode asset: {gamemode_path}")
                return False
            
            # Set GameMode override in WorldSettings
            world_settings.set_editor_property('default_gamemode_override', gamemode_class)
            unreal.log(f"  ✓ Set GameMode: {gamemode_path}")
            
            # Mark package as dirty and save changes
            package = world_settings.get_outer()
            unreal.EditorAssetLibrary.save_loaded_asset(package)
            
            return True
        except Exception as e:
            unreal.log_error(f"Error updating GameMode: {str(e)}")
            return False
    
    def batch_update_gamemode(self, map_list, gamemode_path):
        """
        Batch update GameMode override for multiple maps
        
        Args:
            map_list: List of map package paths
            gamemode_path: UE asset path to GameMode Blueprint
            
        Returns:
            dict: Results with success/failure counts
        """
        results = {
            'total': len(map_list),
            'success': 0,
            'failed': 0,
            'failed_maps': []
        }
        
        unreal.log("=" * 60)
        unreal.log("Batch Updating GameMode Override")
        unreal.log("=" * 60)
        unreal.log(f"GameMode to apply: {gamemode_path}")
        unreal.log(f"Total maps: {len(map_list)}")
        unreal.log("")
        
        for i, map_path in enumerate(map_list, 1):
            unreal.log(f"[{i}/{len(map_list)}] Processing: {map_path}")
            
            # Load map
            if not self.load_map(map_path):
                results['failed'] += 1
                results['failed_maps'].append(map_path)
                continue
            
            # Update GameMode
            if self.update_gamemode(gamemode_path):
                results['success'] += 1
                unreal.log(f"  ✓ Successfully updated GameMode")
            else:
                results['failed'] += 1
                results['failed_maps'].append(map_path)
                unreal.log_warning(f"  ✗ Failed to update GameMode")
            
            unreal.log("")
        
        unreal.log("=" * 60)
        unreal.log("Batch GameMode Update Complete")
        unreal.log(f"Success: {results['success']}/{results['total']}")
        unreal.log(f"Failed: {results['failed']}/{results['total']}")
        if results['failed_maps']:
            unreal.log("Failed maps:")
            for map_path in results['failed_maps']:
                unreal.log(f"  - {map_path}")
        unreal.log("=" * 60)
        
        return results


def example_usage():
    """Example: Update GameMode override for multiple maps"""
    
    # Example map list
    map_list = [
        '/Game/Maps/Level01',
        '/Game/Maps/Level02',
    ]
    
    # GameMode Blueprint path (must end with _C for Blueprint class)
    # Example: '/Game/Blueprints/BP_MyGameMode.BP_MyGameMode_C'
    gamemode_path = '/Game/Blueprints/BP_CustomGameMode.BP_CustomGameMode_C'
    
    updater = WorldSettingsUpdater()
    results = updater.batch_update_gamemode(map_list, gamemode_path)
    
    return results


if __name__ == "__main__":
    # Uncomment to run example
    # example_usage()
    pass
