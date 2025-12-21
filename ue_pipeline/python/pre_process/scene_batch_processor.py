"""
Main batch processor script that integrates all scene processing functions
"""
import json
import os
import unreal
from pathlib import Path

# Import our custom modules
import sys
pipeline_python_path = os.path.dirname(os.path.abspath(__file__))
if pipeline_python_path not in sys.path:
    sys.path.append(pipeline_python_path)

try:
    from detect_scene_maps import find_all_umap_files, get_project_content_path
    from batch_update_worldsettings import WorldSettingsUpdater
    from add_navmesh_to_scene import NavMeshManager
except ImportError as e:
    unreal.log_error(f"Failed to import modules: {e}")
    unreal.log_warning("Make sure all Python scripts are in the same directory")


class SceneBatchProcessor:
    """Main processor to orchestrate all scene batch operations"""
    
    def __init__(self, config_path=None):
        """
        Initialize batch processor
        
        Args:
            config_path: Path to scene status JSON file
        """
        self.config_path = config_path
        self.config = None
        self.project_path = None
        self.detected_maps = []
        
        if config_path:
            self.load_config(config_path)
    
    def load_config(self, config_path):
        """Load scene status configuration"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            self.project_path = self.config.get('project_path', '')
            unreal.log(f"Loaded config from: {config_path}")
            unreal.log(f"Project: {self.config.get('project_name', 'Unknown')}")
            unreal.log(f"Project Path: {self.project_path}")
            
            return True
        except Exception as e:
            unreal.log_error(f"Failed to load config: {e}")
            return False
    
    def detect_all_maps(self):
        """Detect all .umap files in the project"""
        unreal.log("\n" + "=" * 60)
        unreal.log("Step 1: Detecting Scene Maps")
        unreal.log("=" * 60)
        
        content_path = get_project_content_path()
        self.detected_maps = find_all_umap_files(content_path)
        
        unreal.log(f"Found {len(self.detected_maps)} map(s):")
        for i, umap in enumerate(self.detected_maps, 1):
            unreal.log(f"  {i}. {umap['name']} - {umap['package_path']}")
        
        return self.detected_maps
    
    def update_worldsettings_batch(self, settings_dict, map_filter=None):
        """
        Batch update WorldSettings for detected maps
        
        Args:
            settings_dict: Settings to apply
            map_filter: Optional list of map names to process (None = all)
        """
        unreal.log("\n" + "=" * 60)
        unreal.log("Step 2: Batch Update WorldSettings")
        unreal.log("=" * 60)
        
        # Get map package paths
        if map_filter:
            map_paths = [
                m['package_path'] for m in self.detected_maps 
                if m['name'] in map_filter
            ]
        else:
            map_paths = [m['package_path'] for m in self.detected_maps]
        
        if not map_paths:
            unreal.log_warning("No maps to process")
            return None
        
        # Update WorldSettings
        updater = WorldSettingsUpdater()
        results = updater.batch_update_maps(map_paths, settings_dict)
        
        return results
    
    def add_navmesh_batch(self, location=None, scale=None, map_filter=None):
        """
        Batch add NavMesh to detected maps
        
        Args:
            location: NavMesh location
            scale: NavMesh scale
            map_filter: Optional list of map names to process (None = all)
        """
        unreal.log("\n" + "=" * 60)
        unreal.log("Step 3: Batch Add NavMesh")
        unreal.log("=" * 60)
        
        # Get map package paths
        if map_filter:
            map_paths = [
                m['package_path'] for m in self.detected_maps 
                if m['name'] in map_filter
            ]
        else:
            map_paths = [m['package_path'] for m in self.detected_maps]
        
        if not map_paths:
            unreal.log_warning("No maps to process")
            return None
        
        # Add NavMesh
        manager = NavMeshManager()
        results = manager.batch_add_navmesh_to_maps(map_paths, location, scale)
        
        return results
    
    def save_results_to_config(self):
        """Save detected maps back to config file"""
        if not self.config_path or not self.config:
            unreal.log_warning("No config to save")
            return False
        
        try:
            # Update scenes in config
            self.config['scenes'] = [
                {
                    'name': m['name'],
                    'package_path': m['package_path'],
                    'relative_path': m['relative_path']
                }
                for m in self.detected_maps
            ]
            
            # Update timestamp
            from datetime import datetime
            self.config['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Save to file
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            
            unreal.log(f"✓ Saved results to: {self.config_path}")
            return True
            
        except Exception as e:
            unreal.log_error(f"Failed to save config: {e}")
            return False
    
    def run_full_pipeline(self, worldsettings=None, navmesh_config=None, map_filter=None):
        """
        Run the complete processing pipeline
        
        Args:
            worldsettings: Dict of WorldSettings to apply
            navmesh_config: Dict with 'location' and 'scale' for NavMesh
            map_filter: Optional list of map names to process
        """
        unreal.log("\n" + "=" * 80)
        unreal.log("SCENE BATCH PROCESSING PIPELINE")
        unreal.log("=" * 80)
        
        # Step 1: Detect maps
        self.detect_all_maps()
        
        # Step 2: Update WorldSettings (if provided)
        if worldsettings:
            self.update_worldsettings_batch(worldsettings, map_filter)
        
        # Step 3: Add NavMesh (if provided)
        if navmesh_config:
            location = navmesh_config.get('location')
            scale = navmesh_config.get('scale')
            self.add_navmesh_batch(location, scale, map_filter)
        
        # Step 4: Save results
        self.save_results_to_config()
        
        unreal.log("\n" + "=" * 80)
        unreal.log("PIPELINE COMPLETE")
        unreal.log("=" * 80)


def example_full_pipeline():
    """Example: Run the complete pipeline"""
    
    # Config file path
    config_path = "E:/WorldDataPipeline/ue_pipeline/scenes/World1_scenes_status.json"
    
    # Initialize processor
    processor = SceneBatchProcessor(config_path)
    
    # WorldSettings to apply
    worldsettings = {
        'kill_z': -10000.0,
        'enable_world_composition': False,
        'default_gravity_z': -980.0,
    }
    
    # NavMesh configuration
    navmesh_config = {
        'location': (0.0, 0.0, 0.0),
        'scale': (100.0, 100.0, 10.0)
    }
    
    # Run full pipeline
    # Optional: specify map_filter=['MapName1', 'MapName2'] to process specific maps only
    processor.run_full_pipeline(
        worldsettings=worldsettings,
        navmesh_config=navmesh_config,
        map_filter=None  # None = process all maps
    )


if __name__ == "__main__":
    # Uncomment to run example
    # example_full_pipeline()
    pass
