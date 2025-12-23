#!/usr/bin/env python3
"""
UE Scene Map Scanner
Scan UE project for scene folders and update scene status JSON
"""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict


class SceneMapScanner:
    def __init__(self, config_path: str = None):
        """Initialize scanner with UE config"""
        self.script_dir = Path(__file__).parent
        
        # Load UE config
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = self.script_dir / 'config' / 'ue_config.json'
        
        if not self.config_path.exists():
            print(f"Error: Config file not found: {self.config_path}")
            exit(1)
        
        self.config = self.load_config()
        self.project_path = Path(self.config['project_path'])
        self.project_name = self.project_path.stem
        self.content_folder = self.project_path.parent / 'Content'
        
        print(f"Project: {self.project_name}")
        print(f"Content folder: {self.content_folder}")
        print(f"Config file: {self.config_path}")
        print()
    
    def load_config(self) -> dict:
        """Load UE configuration"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error: Cannot load config: {e}")
            exit(1)
    
    def load_scene_status(self) -> dict:
        """Load existing scene status from config"""
        return self.config.get('scenes', [])
    
    def save_scene_status(self, scenes: list):
        """Save scene status to config file"""
        self.config['scenes'] = scenes
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            print(f"\nConfig updated: {self.config_path}")
        except Exception as e:
            print(f"Error: Cannot save config file: {e}")
    
    def find_scene_folders(self) -> List[Dict]:
        """Find all scene folders in Content directory (folders starting with S followed by digits)"""
        if not self.content_folder.exists():
            print(f"Error: Content folder does not exist: {self.content_folder}")
            return []
        
        scene_folders = []
        
        # Find folders matching pattern S#### (e.g., S0001, S0002)
        for item in self.content_folder.iterdir():
            if item.is_dir():
                name = item.name
                # Check if folder name matches S#### pattern
                if name.startswith('S') and len(name) >= 5:
                    # Check if characters after 'S' are digits
                    number_part = name[1:5]
                    if number_part.isdigit():
                        scene_folders.append({
                            'id': name,
                            'name': name,
                            'path': item
                        })
        
        # Sort by scene ID
        scene_folders.sort(key=lambda x: x['id'])
        
        return scene_folders
    
    def find_umap_files(self, scene_folder: Path, scene_id: str) -> List[str]:
        """Find all .umap files in scene folder and convert to UE path format
        
        Args:
            scene_folder: Scene folder path (e.g., Content/S0001)
            scene_id: Scene ID (e.g., S0001)
        
        Returns:
            List of map paths in UE format (e.g., ['/Game/S0001/Maps/MainMap'])
        """
        umap_paths = []
        
        if not scene_folder.exists():
            return umap_paths
        
        for root, dirs, files in os.walk(scene_folder):
            for file in files:
                if file.endswith('.umap'):
                    file_path = Path(root) / file
                    
                    # Convert to UE path format
                    # Content/S0001/Maps/MainMap.umap -> /Game/S0001/Maps/MainMap
                    rel_path = file_path.relative_to(self.content_folder)
                    ue_path = '/Game/' + str(rel_path.parent / rel_path.stem).replace('\\', '/')
                    umap_paths.append(ue_path)
        
        return sorted(umap_paths)
    
    def update_scene_status(self, scene_id: str, name: str, map_paths: List[str], scenes: list):
        """Update scene status with map paths"""
        # Find existing scene
        existing_scene = None
        for scene in scenes:
            if scene['id'] == scene_id:
                existing_scene = scene
                break
        
        if existing_scene:
            # Update scene name
            existing_scene['name'] = name
            
            # Update map list (preserve existing actor_added and baked status)
            existing_maps = {m['path']: m for m in existing_scene.get('maps', [])}
            new_maps = []
            
            for map_path in map_paths:
                # Extract map name from path (e.g., /Game/S0001/Maps/MainMap -> MainMap)
                map_name = map_path.split('/')[-1]
                
                if map_path in existing_maps:
                    # Preserve existing status, but update name to map name
                    existing_map = existing_maps[map_path].copy()
                    existing_map['name'] = map_name
                    new_maps.append(existing_map)
                else:
                    # New map, initialize status
                    new_maps.append({
                        "name": map_name,
                        "path": map_path,
                        "actor_added": False,
                        "baked": False
                    })
            
            existing_scene['maps'] = new_maps
        else:
            # New scene
            new_scene = {
                "id": scene_id,
                "name": name,
                "maps": [
                    {
                        "name": map_path.split('/')[-1],  # Use map name as name
                        "path": map_path,
                        "actor_added": False,
                        "baked": False
                    }
                    for map_path in map_paths
                ]
            }
            scenes.append(new_scene)
    
    def scan_all_scenes(self, dry_run: bool = False):
        """Scan all scene folders and update status"""
        print("=" * 70)
        print("UE Scene Map Scanner")
        print("=" * 70)
        print()
        
        # Find scene folders
        scene_folders = self.find_scene_folders()
        
        if not scene_folders:
            print("No scene folders found (looking for folders named S####)")
            return
        
        print(f"Found {len(scene_folders)} scene folder(s):")
        for folder in scene_folders:
            print(f"  - {folder['id']}")
        print()
        
        # Load existing status
        scenes = self.load_scene_status()
        
        if dry_run:
            print("=== Preview Mode (No changes will be saved) ===")
            print()
        
        # Scan each scene folder
        total_maps = 0
        for idx, folder_info in enumerate(scene_folders, 1):
            scene_id = folder_info['id']
            scene_path = folder_info['path']
            
            print(f"[{idx}/{len(scene_folders)}] Scanning scene: {scene_id}")
            print(f"  Path: {scene_path}")
            
            # Find all .umap files
            map_paths = self.find_umap_files(scene_path, scene_id)
            
            if map_paths:
                print(f"  Found {len(map_paths)} map(s):")
                for map_path in map_paths:
                    print(f"    - {map_path}")
                total_maps += len(map_paths)
            else:
                print(f"  No maps found")
            
            # Update status
            if not dry_run:
                self.update_scene_status(scene_id, scene_id, map_paths, scenes)
            
            print()
        
        # Sort scenes by ID
        scenes.sort(key=lambda x: x['id'])
        
        # Save status
        if not dry_run:
            self.save_scene_status(scenes)
        
        print("=" * 70)
        print("Scan Summary")
        print("=" * 70)
        print(f"Total scenes scanned: {len(scene_folders)}")
        print(f"Total maps found: {total_maps}")
        
        if dry_run:
            print("\nPreview mode - No changes saved")
        else:
            print(f"\nConfig updated: {self.config_path}")
    
    def list_scenes(self):
        """List all scenes from config file"""
        scenes = self.load_scene_status()
        
        if not scenes:
            print("No scenes in config file")
            return
        
        print("=" * 70)
        print(f"Scenes in {self.project_name}")
        print("=" * 70)
        print()
        
        for scene in scenes:
            scene_id = scene['id']
            scene_name = scene['name']
            maps = scene.get('maps', [])
            
            print(f"Scene: {scene_id} ({scene_name})")
            print(f"  Maps: {len(maps)}")
            
            for map_info in maps:
                map_name = map_info['name']
                map_path = map_info['path']
                actor_added = map_info.get('actor_added', False)
                baked = map_info.get('baked', False)
                
                status_flags = []
                if actor_added:
                    status_flags.append("Actor")
                if baked:
                    status_flags.append("Baked")
                
                status_str = f" [{', '.join(status_flags)}]" if status_flags else ""
                print(f"    [{map_name}] {map_path}{status_str}")
            
            print()


def main():
    parser = argparse.ArgumentParser(
        description='Scan UE project for scene folders and update scene status'
    )
    parser.add_argument(
        '--config', '-c',
        help='Path to ue_config.json (default: config/ue_config.json)'
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Preview mode, no changes will be saved'
    )
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List scenes from existing status file'
    )
    
    args = parser.parse_args()
    
    # Create scanner
    scanner = SceneMapScanner(config_path=args.config)
    
    if args.list:
        scanner.list_scenes()
    else:
        scanner.scan_all_scenes(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
