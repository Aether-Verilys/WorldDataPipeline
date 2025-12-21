import os
import json
import shutil
import argparse
from pathlib import Path
from typing import List, Dict
from datetime import datetime


class SceneAssetCopier:
    def __init__(self, config_path: str):
        self.config = self.load_config(config_path)
        self.raw_folder = Path(self.config['raw_folder'])
        self.target_content_folder = Path(self.config['target_content_folder'])
        self.start_index = self.config.get('start_index', 1)
        self.prefix = self.config.get('scene_prefix', 'S')
        self.exclude_patterns = self.config.get('exclude_patterns', [])
        self.project_name = self.config.get('project_name', 'Unknown')
        
        # 场景状态文件路径
        script_dir = Path(__file__).parent.parent
        status_filename = f'{self.project_name}_scenes_status.json'
        self.scene_status_file = script_dir / 'scenes' / status_filename
        self.scene_status_file.parent.mkdir(parents=True, exist_ok=True)
        
    def load_config(self, config_path: str) -> dict:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_scene_status(self) -> dict:
        if not self.scene_status_file.exists():
            return {
                "project_name": self.project_name,
                "last_updated": "",
                "scenes": []
            }
        
        with open(self.scene_status_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_scene_status(self, status_data: dict):
        status_data['project_name'] = self.project_name
        status_data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(self.scene_status_file, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, indent=2, ensure_ascii=False)
    
    def update_scene_status(self, scene_id: str, name: str):
        status_data = self.load_scene_status()
        
        # 查找是否已存在该场景
        existing_scene = None
        for scene in status_data['scenes']:
            if scene['id'] == scene_id:
                existing_scene = scene
                break
        
        if existing_scene:
            existing_scene['name'] = name
        else:
            status_data['scenes'].append({
                "id": scene_id,
                "name": name,
                "actor_added": False,
                "baked": False
            })
        
        # 按场景ID排序
        status_data['scenes'].sort(key=lambda x: x['id'])
        
        self.save_scene_status(status_data)
    
    def find_content_folders(self) -> List[Dict[str, Path]]:
        content_folders = []
        
        if not self.raw_folder.exists():
            print(f"Error: Raw folder does not exist: {self.raw_folder}")
            return content_folders
        
        for item in self.raw_folder.iterdir():
            if not item.is_dir():
                continue
            
            content_path = None
            for root, dirs, files in os.walk(item):
                if 'Content' in dirs:
                    content_path = Path(root) / 'Content'
                    break
            
            if content_path and content_path.exists():
                content_folders.append({
                    'name': item.name,
                    'content_path': content_path,
                    'asset_root': item
                })
                print(f"Found asset: {item.name} -> {content_path}")
        
        return content_folders
    
    def should_exclude(self, path: Path) -> bool:
        path_str = str(path)
        for pattern in self.exclude_patterns:
            if pattern in path_str:
                return True
        return False
    
    def get_directory_info(self, path: Path) -> int:
        total_files = 0
        
        for root, dirs, files in os.walk(path):
            # 过滤排除的目录
            dirs[:] = [d for d in dirs if not self.should_exclude(Path(root) / d)]
            
            for file in files:
                file_path = Path(root) / file
                if not self.should_exclude(file_path):
                    total_files += 1
        
        return total_files
    
    def format_size(self, size_bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    def copy_with_progress(self, src: Path, dst: Path, file_num: int, total_files: int):
        try:
            size = src.stat().st_size
            size_str = self.format_size(size)
            print(f"    [{file_num}/{total_files}] {src.name} ({size_str})")
            shutil.copy2(src, dst)
            return True
        except Exception as e:
            print(f"    [Error] Copy failed {src.name}: {e}")
            return False
    
    def copytree_with_progress(self, src: Path, dst: Path, prefix: str = "  "):
        total_files = self.get_directory_info(src)
        print(f"{prefix}Total {total_files} files")
        
        copied_files = 0
        skipped_files = 0
        failed_count = 0
        
        dst.mkdir(parents=True, exist_ok=True)
        
        for root, dirs, files in os.walk(src):
            # 过滤排除的目录
            dirs[:] = [d for d in dirs if not self.should_exclude(Path(root) / d)]
            
            rel_path = Path(root).relative_to(src)
            target_dir = dst / rel_path
            
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 复制文件
            for file in files:
                src_file = Path(root) / file
                
                if self.should_exclude(src_file):
                    continue
                
                dst_file = target_dir / file
                
                # 跳过已存在的重复文件
                if dst_file.exists():
                    skipped_files += 1
                    print(f"{prefix}  [Skipped] {src_file.name} (already exists)")
                    continue
                
                copied_files += 1
                
                try:
                    file_size = src_file.stat().st_size
                    size_str = self.format_size(file_size)
                    
                    print(f"{prefix}  [{copied_files}/{total_files}] {src_file.name} ({size_str})")
                    
                    shutil.copy2(src_file, dst_file)
                except Exception as e:
                    print(f"{prefix}  [Error] {src_file.name}: {e}")
                    failed_count += 1
        
        print(f"{prefix}Completed: {copied_files}/{total_files} files copied")
        if skipped_files > 0:
            print(f"{prefix}Skipped: {skipped_files} files (already existed)")
        if failed_count > 0:
            print(f"{prefix}Failed: {failed_count} files")
        
        return failed_count == 0
    
    def copy_content(self, source_content: Path, target_scene_folder: Path) -> bool:
        try:
            target_scene_folder.mkdir(parents=True, exist_ok=True)
            
            # 先列出所有要复制的项目
            items_to_copy = [item for item in source_content.iterdir() if not self.should_exclude(item)]
            
            if not items_to_copy:
                print("  No files to copy")
                return True
            
            all_success = True
            
            for idx, item in enumerate(items_to_copy, 1):
                target_path = target_scene_folder / item.name
                
                if item.is_dir():
                    if target_path.exists():
                        print(f"  [{idx}/{len(items_to_copy)}] Skipping folder: {item.name} (already exists)")
                        continue
                    
                    print(f"  [{idx}/{len(items_to_copy)}] Copying folder: {item.name}")
                    success = self.copytree_with_progress(item, target_path, prefix="    ")
                    if not success:
                        all_success = False
                else:
                    if target_path.exists():
                        print(f"  [{idx}/{len(items_to_copy)}] Skipping file: {item.name} (already exists)")
                        continue
                    
                    file_size = item.stat().st_size
                    size_str = self.format_size(file_size)
                    print(f"  [{idx}/{len(items_to_copy)}] Copying file: {item.name} ({size_str})")
                    shutil.copy2(item, target_path)
            
            return all_success
        except Exception as e:
            print(f"Copy failed: {e}")
            return False
    
    def generate_scene_id(self, index: int) -> str:
        return f"{self.prefix}{index:04d}"
    
    def process_all(self, dry_run: bool = False):
        content_folders = self.find_content_folders()
        
        if not content_folders:
            print("No assets containing Content folder found")
            return
        
        print(f"\nFound {len(content_folders)} assets")
        print(f"Target folder: {self.target_content_folder}")
        
        if dry_run:
            print("\n=== Preview Mode (No actual copy) ===")
        
        # 按名称排序以保证一致性
        content_folders.sort(key=lambda x: x['name'])
        
        success_count = 0
        for idx, folder_info in enumerate(content_folders):
            scene_id = self.generate_scene_id(self.start_index + idx)
            source_path = folder_info['content_path']
            target_path = self.target_content_folder / scene_id
            
            print(f"\n[{idx + 1}/{len(content_folders)}] Processing asset: {folder_info['name']}")
            print(f"  Scene ID: {scene_id}")
            print(f"  Source path: {source_path}")
            print(f"  Target path: {target_path}")
            
            if dry_run:
                print(f"  [Preview] Will copy to: {target_path}")
                success_count += 1
            else:
                if self.copy_content(source_path, target_path):
                    print(f"Copy succeeded")
                    self.update_scene_status(scene_id, folder_info['name'])
                    success_count += 1
                else:
                    print(f"Copy failed")
        
        print(f"\n=== Completed ===")
        print(f"Success: {success_count}/{len(content_folders)}")
    
    def list_assets(self):
        content_folders = self.find_content_folders()
        
        if not content_folders:
            print("No assets found")
            return
        
        print(f"\nFound {len(content_folders)} assets:")
        content_folders.sort(key=lambda x: x['name'])
        
        for idx, folder_info in enumerate(content_folders):
            scene_id = self.generate_scene_id(self.start_index + idx)
            print(f"{scene_id} - {folder_info['name']}")
            print(f"  Content path: {folder_info['content_path']}")


def main():
    parser = argparse.ArgumentParser(description='Batch copy scene assets to UE project')
    parser.add_argument('--config', '-c', 
                       default='copy_scene_config.json',
                       help='Config file path')
    parser.add_argument('--dry-run', '-d', 
                       action='store_true',
                       help='Preview mode, no actual copy')
    parser.add_argument('--list', '-l', 
                       action='store_true',
                       help='List found assets only')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.config):
        print(f"Error: Config file does not exist: {args.config}")
        print("Please create config file or specify config file path with --config")
        return
    
    copier = SceneAssetCopier(args.config)
    
    if args.list:
        copier.list_assets()
    else:
        copier.process_all(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
