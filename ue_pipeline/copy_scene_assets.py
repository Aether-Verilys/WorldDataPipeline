import os
import json
import shutil
import argparse
from pathlib import Path
from typing import List, Dict
from datetime import datetime


class SceneAssetCopier:
    def __init__(self, config_path: str, overwrite: bool = False):
        self.config = self.load_config(config_path)
        self.raw_folder = Path(self.config['raw_folder'])
        self.target_content_folder = Path(self.config['target_content_folder'])
        self.start_index = self.config.get('start_index', 1)
        self.prefix = self.config.get('scene_prefix', 'S')
        self.exclude_patterns = self.config.get('exclude_patterns', [])
        self.project_name = self.config.get('project_name', 'Unknown')
        self.overwrite = overwrite
        
        # 场景状态文件路径
        script_dir = Path(__file__).parent
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
                "project_path": str(self.target_content_folder.parent),
                "last_updated": "",
                "scenes": []
            }
        
        with open(self.scene_status_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def find_umap_files(self, scene_folder: Path, scene_id: str) -> List[str]:
        """查找场景文件夹下的所有.umap文件，并转换为UE路径格式
        
        Args:
            scene_folder: 场景文件夹路径，如 Content/S0001
            scene_id: 场景ID，如 S0001
        
        Returns:
            UE路径格式的地图列表，如 ['/Game/S0001/Maps/MainMap']
        """
        umap_paths = []
        
        if not scene_folder.exists():
            return umap_paths
        
        for root, dirs, files in os.walk(scene_folder):
            # 过滤排除的目录
            dirs[:] = [d for d in dirs if not self.should_exclude(Path(root) / d)]
            
            for file in files:
                if file.endswith('.umap'):
                    file_path = Path(root) / file
                    if not self.should_exclude(file_path):
                        # 转换为UE路径格式: /Game/S0001/FolderPath/MapName
                        # scene_folder 是 Content/S0001，file_path 相对于它的路径
                        rel_path = file_path.relative_to(scene_folder)
                        # 构建UE路径，移除.umap扩展名
                        if rel_path.parent == Path('.'):
                            # 文件直接在S0001根目录
                            ue_path = f"/Game/{scene_id}/{rel_path.stem}"
                        else:
                            # 文件在子文件夹中
                            folder_path = str(rel_path.parent).replace('\\', '/')
                            ue_path = f"/Game/{scene_id}/{folder_path}/{rel_path.stem}"
                        
                        umap_paths.append(ue_path)
        
        return sorted(umap_paths)
    
    def save_scene_status(self, status_data: dict):
        status_data['project_name'] = self.project_name
        status_data['project_path'] = str(self.target_content_folder.parent)
        status_data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(self.scene_status_file, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, indent=2, ensure_ascii=False)
    
    def update_scene_status(self, scene_id: str, name: str, map_paths: List[str]):
        """更新场景状态，包括地图路径列表"""
        status_data = self.load_scene_status()
        
        # 查找是否已存在该场景
        existing_scene = None
        for scene in status_data['scenes']:
            if scene['id'] == scene_id:
                existing_scene = scene
                break
        
        if existing_scene:
            # 更新场景名称
            existing_scene['name'] = name
            
            # 更新地图列表（保留已有的actor_added和baked状态）
            existing_maps = {m['path']: m for m in existing_scene.get('maps', [])}
            new_maps = []
            map_index = 1
            
            for map_path in map_paths:
                if map_path in existing_maps:
                    # 保留现有状态
                    new_maps.append(existing_maps[map_path])
                else:
                    # 新地图，初始化状态
                    map_id = f"{scene_id}M{map_index:03d}"
                    new_maps.append({
                        "id": map_id,
                        "path": map_path,
                        "actor_added": False,
                        "baked": False
                    })
                map_index += 1
            
            existing_scene['maps'] = new_maps
        else:
            # 新场景
            new_scene = {
                "id": scene_id,
                "name": name,
                "maps": [
                    {
                        "id": f"{scene_id}M{idx+1:03d}",
                        "path": map_path,
                        "actor_added": False,
                        "baked": False
                    }
                    for idx, map_path in enumerate(map_paths)
                ]
            }
            status_data['scenes'].append(new_scene)
        
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
    
    def get_directory_info(self, path: Path) -> tuple:
        """返回 (文件数量, 总大小)"""
        total_files = 0
        total_size = 0
        
        for root, dirs, files in os.walk(path):
            # 过滤排除的目录
            dirs[:] = [d for d in dirs if not self.should_exclude(Path(root) / d)]
            
            for file in files:
                file_path = Path(root) / file
                if not self.should_exclude(file_path):
                    total_files += 1
                    try:
                        total_size += file_path.stat().st_size
                    except:
                        pass
        
        return total_files, total_size
    
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
        total_files, total_size = self.get_directory_info(src)
        size_str = self.format_size(total_size)
        print(f"{prefix}Folder size: {size_str}, {total_files} files")
        
        copied_files = 0
        skipped_files = 0
        failed_count = 0
        copied_size = 0
        
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
                
                # 检查文件是否存在
                if dst_file.exists():
                    if not self.overwrite:
                        skipped_files += 1
                        continue
                    # 覆盖模式：继续复制
                
                copied_files += 1
                
                try:
                    file_size = src_file.stat().st_size
                    copied_size += file_size
                    shutil.copy2(src_file, dst_file)
                except PermissionError as e:
                    print(f"{prefix}  [Permission Denied] {src_file.name} - File may be open in UE Editor or locked")
                    failed_count += 1
                    copied_files -= 1  # 不计入已复制数
                except Exception as e:
                    print(f"{prefix}  [Error] {src_file.name}: {e}")
                    failed_count += 1
                    copied_files -= 1
        
        copied_size_str = self.format_size(copied_size)
        print(f"{prefix}Completed: {copied_files}/{total_files} files copied ({copied_size_str})")
        if skipped_files > 0:
            print(f"{prefix}Skipped: {skipped_files} files (already exist)")
        if failed_count > 0:
            print(f"{prefix}Failed: {failed_count} files (check permissions or close UE Editor)")
        
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
                    if target_path.exists() and not self.overwrite:
                        print(f"  [{idx}/{len(items_to_copy)}] Skipping folder: {item.name} (already exists)")
                        continue
                    
                    action = "Overwriting" if target_path.exists() else "Copying"
                    print(f"  [{idx}/{len(items_to_copy)}] {action} folder: {item.name}")
                    success = self.copytree_with_progress(item, target_path, prefix="    ")
                    if not success:
                        all_success = False
                else:
                    if target_path.exists() and not self.overwrite:
                        print(f"  [{idx}/{len(items_to_copy)}] Skipping file: {item.name} (already exists)")
                        continue
                    
                    file_size = item.stat().st_size
                    size_str = self.format_size(file_size)
                    action = "Overwriting" if target_path.exists() else "Copying"
                    print(f"  [{idx}/{len(items_to_copy)}] {action} file: {item.name} ({size_str})")
                    try:
                        shutil.copy2(item, target_path)
                    except PermissionError:
                        print(f"    [Permission Denied] File may be open in UE Editor or locked")
                        all_success = False
                    except Exception as e:
                        print(f"    [Error] {e}")
                        all_success = False
            
            return all_success
        except Exception as e:
            print(f"Copy failed: {e}")
            return False
    
    def generate_scene_id(self, index: int) -> str:
        return f"{self.prefix}{index:04d}"
    
    def process_all(self, dry_run: bool = False, batch_size: int = 10):
        content_folders = self.find_content_folders()
        
        if not content_folders:
            print("No assets containing Content folder found")
            return
        
        print(f"\nFound {len(content_folders)} assets")
        print(f"Target folder: {self.target_content_folder}")
        print(f"Batch size: {batch_size} assets per batch")
        
        # 按名称排序以保证一致性
        content_folders.sort(key=lambda x: x['name'])
        
        # 计算批次数量
        total_batches = (len(content_folders) + batch_size - 1) // batch_size
        print(f"Total batches: {total_batches}")
        
        if dry_run:
            print("\n=== Preview Mode (No actual copy) ===")
        else:
            print("\nExecuting scene asset copy...")
        
        success_count = 0
        
        # 分批处理
        for batch_idx in range(total_batches):
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(content_folders))
            batch_folders = content_folders[batch_start:batch_end]
            
            print(f"\n{'='*70}")
            print(f"BATCH {batch_idx + 1}/{total_batches}: Processing assets {batch_start + 1} to {batch_end}")
            print(f"{'='*70}")
            
            batch_success = 0
            for idx, folder_info in enumerate(batch_folders):
                global_idx = batch_start + idx
                scene_id = self.generate_scene_id(self.start_index + global_idx)
                source_path = folder_info['content_path']
                target_path = self.target_content_folder / scene_id
                
                print(f"\n[{global_idx + 1}/{len(content_folders)}] Processing asset: {folder_info['name']}")
                print(f"  Scene ID: {scene_id}")
                print(f"  Source path: {source_path}")
                print(f"  Target path: {target_path}")
                
                if dry_run:
                    print(f"  [Preview] Will copy to: {target_path}")
                    batch_success += 1
                    success_count += 1
                else:
                    if self.copy_content(source_path, target_path):
                        print(f"  [OK] Copy succeeded")
                        
                        # 扫描并记录.umap文件
                        print(f"  Scanning for .umap files...")
                        umap_paths = self.find_umap_files(target_path, scene_id)
                        if umap_paths:
                            print(f"  Found {len(umap_paths)} map(s):")
                            for umap_path in umap_paths:
                                print(f"    - {umap_path}")
                        else:
                            print(f"  No .umap files found")
                        
                        self.update_scene_status(scene_id, folder_info['name'], umap_paths)
                        print(f"  [OK] Scene status saved to {self.scene_status_file.name}")
                        batch_success += 1
                        success_count += 1
                    else:
                        print(f"  [FAILED] Copy failed")
            
            print(f"\n{'='*70}")
            print(f"BATCH {batch_idx + 1}/{total_batches} COMPLETED")
            print(f"Batch success: {batch_success}/{len(batch_folders)}")
            print(f"Overall progress: {success_count}/{len(content_folders)}")
            print(f"{'='*70}")
            
            # 批次之间的提示
            if batch_idx < total_batches - 1:
                print(f"\nBatch {batch_idx + 1} finished. Proceeding to next batch...\n")
        
        print(f"\n{'='*70}")
        print(f"ALL BATCHES COMPLETED")
        print(f"{'='*70}")
        print(f"Total success: {success_count}/{len(content_folders)}")
        print(f"Total failed: {len(content_folders) - success_count}/{len(content_folders)}")
    
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
    parser.add_argument('--batch-size', '-b',
                       type=int,
                       default=10,
                       help='Number of assets to process per batch (default: 10)')
    parser.add_argument('--overwrite', '-o',
                       action='store_true',
                       help='Overwrite existing files instead of skipping them')
    
    args = parser.parse_args()
    
    # Process config path
    config_path = Path(args.config)
    
    # If not absolute path, resolve relative to script directory (ue_pipeline)
    if not config_path.is_absolute():
        script_dir = Path(__file__).parent
        config_path = script_dir / config_path
    
    # Normalize path
    config_path = config_path.resolve()
    
    if not config_path.exists():
        print(f"Error: Config file does not exist: {config_path}")
        print("Please create config file or specify config file path with --config")
        return
    
    copier = SceneAssetCopier(str(config_path), overwrite=args.overwrite)
    
    if args.list:
        copier.list_assets()
    else:
        copier.process_all(dry_run=args.dry_run, batch_size=args.batch_size)


if __name__ == '__main__':
    main()
