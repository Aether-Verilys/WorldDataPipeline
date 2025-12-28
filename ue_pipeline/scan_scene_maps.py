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
        self.exclude_map_names = self.config.get('exclude_map_names', [])
        
        print(f"Project: {self.project_name}")
        print(f"Content folder: {self.content_folder}")
        print(f"Config file: {self.config_path}")
        if self.exclude_map_names:
            print(f"Excluding maps: {', '.join(self.exclude_map_names)}")
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
        scenes = self.config.get('scenes', [])
        # 兼容旧格式：如果是列表，转换为字典
        if isinstance(scenes, list):
            return {scene.get('id', scene.get('name', '')): {k: v for k, v in scene.items() if k != 'id'} for scene in scenes}
        return scenes
    
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
        """Find all scene folders in Content directory (excluding system folders)"""
        if not self.content_folder.exists():
            print(f"Error: Content folder does not exist: {self.content_folder}")
            return []
        
        scene_folders = []
        
        # 排除的系统文件夹
        exclude_folders = {
            'Collections', 'Developers', '__ExternalActors__', '__ExternalObjects__',
            'CameraController', 'FirstPerson', 'Input'
        }
        
        # 查找所有非系统文件夹
        for item in self.content_folder.iterdir():
            if item.is_dir() and item.name not in exclude_folders:
                scene_folders.append({
                    'name': item.name,
                    'path': item
                })
        
        # 按名称排序
        scene_folders.sort(key=lambda x: x['name'])
        
        return scene_folders
    
    def find_umap_files(self, scene_folder: Path, scene_name: str) -> List[str]:
        """Find all .umap files in scene folder and convert to UE path format
        
        Args:
            scene_folder: Scene folder path (e.g., Content/LevelPrototyping)
            scene_name: Scene name (e.g., LevelPrototyping)
        
        Returns:
            List of map paths in UE format (e.g., ['/Game/LevelPrototyping/Maps/MainMap'])
        """
        umap_paths = []
        
        if not scene_folder.exists():
            return umap_paths
        
        for root, dirs, files in os.walk(scene_folder):
            for file in files:
                if file.endswith('.umap'):
                    file_path = Path(root) / file
                    map_name = file_path.stem
                    
                    # Skip excluded map names
                    if map_name in self.exclude_map_names:
                        continue
                    
                    # Convert to UE path format
                    # Content/SceneName/Maps/MainMap.umap -> /Game/SceneName/Maps/MainMap
                    rel_path = file_path.relative_to(self.content_folder)
                    ue_path = '/Game/' + str(rel_path.parent / rel_path.stem).replace('\\', '/')
                    umap_paths.append(ue_path)
        
        return sorted(umap_paths)
    
    def update_scene_status(self, scene_name: str, map_paths: List[str], scenes: dict):
        """Update scene status with map paths"""
        if scene_name in scenes:
            # 场景已存在，更新地图列表（保留已有的actor_added状态）
            existing_maps = {m['path']: m for m in scenes[scene_name].get('maps', [])}}
            new_maps = []
            
            for map_path in map_paths:
                # Extract map name from path (e.g., /Game/LevelPrototyping/Maps/MainMap -> MainMap)
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
                        "low_mesh": False
                    })
            
            scenes[scene_name]['maps'] = new_maps
        else:
            # New scene
            scenes[scene_name] = {
                "maps": [
                    {
                        "name": map_path.split('/')[-1],  # Use map name as name
                        "path": map_path,
                        "actor_added": False,
                        "low_mesh": False
                    }
                    for map_path in map_paths
                ]
            }
    
    def scan_all_scenes(self, dry_run: bool = False):
        """Scan all scene folders and update status"""
        print("=" * 70)
        print("UE Scene Map Scanner")
        print("=" * 70)
        print()
        
        # Find scene folders
        scene_folders = self.find_scene_folders()
        
        if not scene_folders:
            print("No scene folders found")
            return
        
        print(f"Found {len(scene_folders)} scene folder(s):")
        for folder in scene_folders:
            print(f"  - {folder['name']}")
        print()
        
        # Load existing status
        scenes = self.load_scene_status()
        
        if dry_run:
            print("=== Preview Mode (No changes will be saved) ===")
            print()
        
        # Scan each scene folder
        total_maps = 0
        for idx, folder_info in enumerate(scene_folders, 1):
            scene_name = folder_info['name']
            scene_path = folder_info['path']
            
            print(f"[{idx}/{len(scene_folders)}] Scanning scene: {scene_name}")
            print(f"  Path: {scene_path}")
            
            # Find all .umap files
            map_paths = self.find_umap_files(scene_path, scene_name)
            
            if map_paths:
                print(f"  Found {len(map_paths)} map(s):")
                for map_path in map_paths:
                    print(f"    - {map_path}")
                total_maps += len(map_paths)
            else:
                print(f"  No maps found")
            
            # Update status
            if not dry_run:
                self.update_scene_status(scene_name, map_paths, scenes)
            
            print()
        
        # Remove scenes that no longer exist in Content folder
        scanned_scene_names = {folder['name'] for folder in scene_folders}
        scenes_to_remove = [name for name in scenes.keys() if name not in scanned_scene_names]
        
        if scenes_to_remove:
            print(f"Removing {len(scenes_to_remove)} scene(s) no longer in Content folder:")
            for scene_name in scenes_to_remove:
                print(f"  - {scene_name}")
                del scenes[scene_name]
            print()
        
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
        
        # 按场景名称排序
        sorted_scenes = sorted(scenes.items())
        
        for scene_name, scene_data in sorted_scenes:
            maps = scene_data.get('maps', [])
            
            print(f"Scene: {scene_name}")
            print(f"  Maps: {len(maps)}")
            
            for map_info in maps:
                map_name = map_info['name']
                map_path = map_info['path']
                actor_added = map_info.get('actor_added', False)
                low_mesh = map_info.get('low_mesh', False)
                
                status_flags = []
                if actor_added:
                    status_flags.append("Actor")
                if low_mesh:
                    status_flags.append("LowMesh")
                
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
