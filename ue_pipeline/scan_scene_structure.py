"""
场景结构扫描工具
扫描给定目录下的所有场景，记录场景名、启动目录名、地图位置等信息
支持本地路径和BOS路径扫描
将累加数据写入数据库 scenes.db 和统一的 scenes.json（位于 database 目录）
"""

import os
import json
import shutil
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 添加python模块路径
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir / 'python'))

try:
    from bos.bos_client import BosClientManager
    HAS_BOS = True
except ImportError:
    HAS_BOS = False


class SceneStructureScanner:
    def __init__(self, config_path: str = None, dry_run: bool = False, database_dir: str = None, use_bos: bool = False, bos_config: str = None, db_name: str = None):
        """
        Args:
            config_path: 配置文件路径（可选）
            dry_run: 预览模式，不实际创建Content目录和json文件
            database_dir: 数据库目录路径，默认为项目根目录的database文件夹
            use_bos: 是否使用BOS扫描
            bos_config: BOS配置文件路径
            db_name: 数据库文件名前缀（默认根据来源自动设置）
        """
        self.dry_run = dry_run
        self.use_bos = use_bos
        self.bos_manager = None
        
        # 初始化BOS（如果需要）
        if use_bos:
            if not HAS_BOS:
                raise ImportError("BOS support not available. Install bce-python-sdk: pip install bce-python-sdk")
            
            self.bos_manager = BosClientManager()
            if bos_config:
                self.bos_manager.initialize(config_file=bos_config)
            else:
                self.bos_manager.initialize()
            
            print(f"✓ BOS initialized")
        
        # 设置数据库目录
        if database_dir:
            self.database_dir = Path(database_dir)
        else:
            # 默认使用项目根目录的database文件夹
            script_dir = Path(__file__).parent
            repo_root = script_dir.parent
            self.database_dir = repo_root / 'database'
        
        # 确保数据库目录存在
        if not self.dry_run:
            self.database_dir.mkdir(parents=True, exist_ok=True)
        
        # 根据来源设置不同的数据库文件名
        if db_name:
            db_prefix = db_name
        elif use_bos:
            db_prefix = 'scenes_bos'
        else:
            db_prefix = 'scenes'
        
        self.db_path = self.database_dir / f'{db_prefix}.db'
        self.json_path = self.database_dir / f'{db_prefix}.json'
        
        # 默认配置
        self.config = {
            "fallback_markers": [
                "Blueprints",
                "Maps",
                "Map",
                "Level",
                "Levels"
            ],
            "exclude_map_names": [
                "Overview",
                "prop"
            ]
        }
        
        # 如果提供了配置文件，加载并合并
        if config_path and Path(config_path).exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                self.config.update(user_config)
        
        self.fallback_markers = self.config.get('fallback_markers', [])
        self.exclude_map_names = self.config.get('exclude_map_names', [])
        
        # 初始化数据库
        if not self.dry_run:
            self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建场景表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scenes (
                scene_name TEXT PRIMARY KEY,
                launch_directory TEXT NOT NULL,
                content_path TEXT NOT NULL,
                launch_directory_path TEXT NOT NULL,
                base_game_path TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                low_actor INTEGER DEFAULT 0,
                baked INTEGER DEFAULT 0,
                last_baked TEXT
            )
        ''')
        
        # 创建地图表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS maps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_name TEXT NOT NULL,
                map_name TEXT NOT NULL,
                map_path TEXT NOT NULL,
                FOREIGN KEY (scene_name) REFERENCES scenes(scene_name),
                UNIQUE(scene_name, map_path)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _save_to_database(self, scene_config: Dict):
        """保存场景配置到数据库（累加模式）"""
        if self.dry_run:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 插入或更新场景信息
            cursor.execute('''
                INSERT OR REPLACE INTO scenes 
                (scene_name, launch_directory, content_path, launch_directory_path, base_game_path, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                scene_config['scene_name'],
                scene_config['launch_directory'],
                scene_config['content_path'],
                scene_config['launch_directory_path'],
                scene_config['base_game_path'],
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
            
            # 删除该场景的旧地图记录
            cursor.execute('DELETE FROM maps WHERE scene_name = ?', (scene_config['scene_name'],))
            
            # 插入新的地图记录
            for map_info in scene_config['maps']:
                cursor.execute('''
                    INSERT INTO maps (scene_name, map_name, map_path)
                    VALUES (?, ?, ?)
                ''', (
                    scene_config['scene_name'],
                    map_info['name'],
                    map_info['path']
                ))
            
            conn.commit()
        finally:
            conn.close()
    
    def _save_to_json(self):
        """从数据库读取所有数据并保存到 scenes.json"""
        if self.dry_run:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 读取所有场景
            cursor.execute('SELECT * FROM scenes ORDER BY scene_name')
            scenes_data = {}
            
            for row in cursor.fetchall():
                scene_name = row[0]
                launch_dir = row[1]
                content_path = row[2]
                launch_dir_path = row[3]
                base_game_path = row[4]
                last_updated = row[5]
                low_actor = bool(row[6]) if len(row) > 6 else False
                baked = bool(row[7]) if len(row) > 7 else False
                last_baked = row[8] if len(row) > 8 else None
                
                # 读取该场景的所有地图
                cursor.execute('SELECT map_name, map_path FROM maps WHERE scene_name = ? ORDER BY map_name', 
                             (scene_name,))
                maps = [{'name': name, 'path': path} for name, path in cursor.fetchall()]
                
                scene_info = {
                    'scene_name': scene_name,
                    'launch_directory': launch_dir,
                    'content_path': content_path,
                    'launch_directory_path': launch_dir_path,
                    'base_game_path': base_game_path,
                    'maps': maps,
                    'last_updated': last_updated,
                    'low_actor': low_actor,
                    'baked': baked
                }
                
                if last_baked:
                    scene_info['last_baked'] = last_baked
                
                scenes_data[scene_name] = scene_info
            
            # 保存到JSON文件
            output = {
                'total_scenes': len(scenes_data),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'scenes': scenes_data
            }
            
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            
        finally:
            conn.close()

    
    def should_exclude_map(self, map_name: str) -> bool:
        """检查地图名是否应该被排除"""
        for exclude_pattern in self.exclude_map_names:
            if exclude_pattern.lower() in map_name.lower():
                return True
        return False
    
    def list_bos_folders(self, bucket: str, prefix: str) -> List[str]:
        """列出BOS指定前缀下的所有文件夹"""
        if not self.bos_manager:
            return []
        
        try:
            all_objects = self.bos_manager.list_objects(bucket, prefix=prefix)
            
            # 提取文件夹名（去重）
            folders = set()
            for obj_key in all_objects:
                # 移除prefix前缀
                relative_path = obj_key[len(prefix):].lstrip('/')
                if '/' in relative_path:
                    # 提取第一级文件夹名
                    folder = relative_path.split('/')[0]
                    folders.add(folder)
            
            return sorted(list(folders))
        except Exception as e:
            print(f"Error listing BOS folders: {e}")
            return []
    
    def find_bos_content_folder(self, bucket: str, scene_prefix: str) -> Optional[str]:
        """在BOS场景目录中查找Content文件夹"""
        try:
            all_objects = self.bos_manager.list_objects(bucket, prefix=scene_prefix)
            
            for obj_key in all_objects:
                if '/Content/' in obj_key:
                    # 找到Content文件夹的路径
                    parts = obj_key.split('/Content/')
                    return parts[0] + '/Content'
            
            return None
        except Exception as e:
            print(f"Error finding Content in BOS: {e}")
            return None
    
    def find_bos_umap_files(self, bucket: str, search_prefix: str, base_game_path: str) -> List[Dict[str, str]]:
        """查找BOS中的.umap文件"""
        maps = []
        
        try:
            all_objects = self.bos_manager.list_objects(bucket, prefix=search_prefix)
            
            for obj_key in all_objects:
                if obj_key.endswith('.umap'):
                    # 提取地图名
                    map_name = Path(obj_key).stem
                    
                    # 检查是否应该排除
                    if self.should_exclude_map(map_name):
                        print(f"    Excluding map: {map_name} (matches exclude pattern)")
                        continue
                    
                    # 构建UE路径
                    # 从search_prefix后的路径构建
                    relative_path = obj_key[len(search_prefix):].lstrip('/')
                    path_parts = Path(relative_path).parts[:-1]  # 移除文件名
                    ue_path = base_game_path + '/' + '/'.join(path_parts) + '/' + map_name if path_parts else base_game_path + '/' + map_name
                    
                    maps.append({
                        "name": map_name,
                        "path": ue_path,
                        "bos_key": obj_key
                    })
            
            return sorted(maps, key=lambda x: x['name'])
        except Exception as e:
            print(f"Error finding umap files in BOS: {e}")
            return []
    
    def scan_bos_scene(self, bucket: str, scene_prefix: str, scene_name: str) -> Optional[Dict]:
        """
        扫描BOS上的单个场景
        
        Args:
            bucket: BOS bucket名称
            scene_prefix: 场景在BOS中的前缀，如 "raw/SceneName"
            scene_name: 场景名称
        """
        print(f"\nScanning BOS scene: {scene_name}")
        print(f"  Bucket: {bucket}")
        print(f"  Prefix: {scene_prefix}")
        
        # 查找Content目录
        content_prefix = self.find_bos_content_folder(bucket, scene_prefix)
        
        if not content_prefix:
            print(f"  No Content folder found in BOS, checking for fallback markers...")
            # BOS场景没有Content的情况暂不处理，可以后续扩展
            print(f"  Warning: BOS scenes without Content folder are not supported yet")
            return None
        
        print(f"  Found Content: {content_prefix}")
        
        # 获取启动目录名（Content下一级）
        # 列出Content下的文件夹
        content_objects = self.bos_manager.list_objects(bucket, prefix=content_prefix + '/')
        
        launch_dir_name = None
        for obj_key in content_objects:
            relative = obj_key[len(content_prefix)+1:]
            if '/' in relative:
                launch_dir_name = relative.split('/')[0]
                break
        
        if not launch_dir_name:
            launch_dir_name = scene_name
        
        print(f"  Launch directory: {launch_dir_name}")
        
        # 扫描.umap文件
        base_game_path = f"/Game/{launch_dir_name}"
        launch_prefix = f"{content_prefix}/{launch_dir_name}"
        maps = self.find_bos_umap_files(bucket, launch_prefix, base_game_path)
        
        print(f"  Found {len(maps)} valid map(s)")
        for map_info in maps:
            print(f"    - {map_info['name']}: {map_info['path']}")
        
        # 构建场景配置
        scene_config = {
            "scene_name": scene_name,
            "launch_directory": launch_dir_name,
            "content_path": f"bos://{bucket}/{content_prefix}",
            "launch_directory_path": f"bos://{bucket}/{launch_prefix}",
            "base_game_path": base_game_path,
            "maps": [
                {
                    "name": m['name'],
                    "path": m['path']
                }
                for m in maps
            ],
            "source": "bos"
        }
        
        # 保存到数据库
        if self.dry_run:
            print(f"  [DRY RUN] Would update database")
            print(f"  [DRY RUN] Scene config:\n{json.dumps(scene_config, indent=2, ensure_ascii=False)}")
        else:
            self._save_to_database(scene_config)
            print(f"  Updated database")
        
        return scene_config
    
    def find_content_folder(self, scene_path: Path) -> Optional[Path]:
        """在场景目录中查找Content文件夹"""
        # 递归查找Content文件夹
        for root, dirs, files in os.walk(scene_path):
            if 'Content' in dirs:
                return Path(root) / 'Content'
        return None
    
    def find_fallback_content(self, scene_path: Path) -> Optional[Path]:
        """根据fallback_markers查找可能的内容目录"""
        for root, dirs, files in os.walk(scene_path):
            for marker in self.fallback_markers:
                if marker in dirs:
                    # 找到marker目录的父目录作为潜在的内容根目录
                    return Path(root)
        return None
    
    def get_launch_directory_name(self, content_path: Path) -> str:
        """获取启动目录名（Content下一级的第一个目录）"""
        # 查找Content下的子目录
        subdirs = [d for d in content_path.iterdir() if d.is_dir()]
        
        if subdirs:
            # 返回第一个子目录名
            return subdirs[0].name
        
        # 如果Content下没有子目录，返回场景名
        return content_path.parent.name
    
    def create_content_structure(self, scene_path: Path, scene_name: str) -> Tuple[Path, str]:
        """
        创建Content目录结构（如果不存在）
        
        Returns:
            (content_path, launch_dir_name)
        """
        fallback_root = self.find_fallback_content(scene_path)
        
        if not fallback_root:
            print(f"  Warning: No fallback markers found in {scene_name}")
            return None, None
        
        # 创建Content目录
        content_path = scene_path / 'Content' / scene_name
        
        if self.dry_run:
            print(f"  [DRY RUN] Would create: {content_path}")
        else:
            content_path.mkdir(parents=True, exist_ok=True)
            print(f"  Created Content structure: {content_path}")
        
        # 移动fallback目录下的内容到新的Content目录
        if not self.dry_run and fallback_root != scene_path:
            for item in fallback_root.iterdir():
                if item.is_dir() and item.name in self.fallback_markers:
                    target = content_path / item.name
                    if not target.exists():
                        print(f"  Moving {item.name} -> {target}")
                        shutil.move(str(item), str(target))
        
        return content_path / scene_name, scene_name
    
    def find_umap_files(self, search_path: Path, base_game_path: str) -> List[Dict[str, str]]:
        """
        查找.umap文件并转换为UE路径格式
        
        Args:
            search_path: 搜索起始路径（通常是启动目录）
            base_game_path: UE游戏路径的基础部分，如 /Game/SceneName
            
        Returns:
            地图列表，每个元素包含 name 和 path
        """
        maps = []
        
        if not search_path.exists():
            return maps
        
        for root, dirs, files in os.walk(search_path):
            for file in files:
                if file.endswith('.umap'):
                    file_path = Path(root) / file
                    map_name = file_path.stem
                    
                    # 检查是否应该排除
                    if self.should_exclude_map(map_name):
                        print(f"    Excluding map: {map_name} (matches exclude pattern)")
                        continue
                    
                    # 构建UE路径
                    rel_path = file_path.relative_to(search_path)
                    # 移除.umap扩展名
                    ue_path_parts = list(rel_path.parts[:-1]) + [map_name]
                    ue_path = base_game_path + '/' + '/'.join(ue_path_parts)
                    
                    maps.append({
                        "name": map_name,
                        "path": ue_path,
                        "file_path": str(file_path)  # 保存物理路径用于调试
                    })
        
        return sorted(maps, key=lambda x: x['name'])
    
    def scan_scene(self, scene_path: Path) -> Optional[Dict]:
        """
        扫描单个场景
        
        Returns:
            场景配置字典，如果扫描失败返回None
        """
        scene_name = scene_path.name
        print(f"\nScanning scene: {scene_name}")
        print(f"  Path: {scene_path}")
        
        # 1. 查找或创建Content目录
        content_path = self.find_content_folder(scene_path)
        
        if content_path:
            print(f"  Found Content: {content_path}")
            # 获取启动目录名（Content下一级）
            launch_dir_name = self.get_launch_directory_name(content_path)
            launch_dir_path = content_path / launch_dir_name
        else:
            print(f"  No Content folder found, using fallback markers...")
            # 使用fallback创建Content结构
            launch_dir_path, launch_dir_name = self.create_content_structure(scene_path, scene_name)
            
            if not launch_dir_path:
                print(f"  Failed to create Content structure for {scene_name}")
                return None
            
            content_path = launch_dir_path.parent
        
        print(f"  Launch directory: {launch_dir_name}")
        
        # 2. 扫描.umap文件
        base_game_path = f"/Game/{launch_dir_name}"
        maps = self.find_umap_files(launch_dir_path, base_game_path)
        
        print(f"  Found {len(maps)} valid map(s)")
        for map_info in maps:
            print(f"    - {map_info['name']}: {map_info['path']}")
        
        # 3. 构建场景配置
        scene_config = {
            "scene_name": scene_name,
            "launch_directory": launch_dir_name,
            "content_path": str(content_path),
            "launch_directory_path": str(launch_dir_path),
            "base_game_path": base_game_path,
            "maps": [
                {
                    "name": m['name'],
                    "path": m['path']
                }
                for m in maps
            ]
        }
        
        # 4. 保存到数据库（不再保存单个 scene.json 文件）
        if self.dry_run:
            print(f"  [DRY RUN] Would update database")
            print(f"  [DRY RUN] Scene config:\n{json.dumps(scene_config, indent=2, ensure_ascii=False)}")
        else:
            self._save_to_database(scene_config)
            print(f"  Updated database")
        
        return scene_config
    
    def scan_all_scenes(self, root_dir: Path = None, bos_bucket: str = None, bos_prefix: str = None) -> List[Dict]:
        """
        扫描根目录或BOS前缀下的所有场景
        
        Args:
            root_dir: 本地根目录（本地扫描模式）
            bos_bucket: BOS bucket名称（BOS扫描模式）
            bos_prefix: BOS前缀（BOS扫描模式）
            
        Returns:
            所有场景配置的列表
        """
        if self.use_bos:
            return self._scan_bos_scenes(bos_bucket, bos_prefix)
        else:
            return self._scan_local_scenes(root_dir)
    
    def _scan_bos_scenes(self, bucket: str, prefix: str) -> List[Dict]:
        """扫描BOS上的场景"""
        print(f"Scanning BOS bucket: {bucket}")
        print(f"Prefix: {prefix}")
        print(f"Dry run mode: {self.dry_run}")
        print(f"Exclude map patterns: {self.exclude_map_names}")
        print("="*70)
        
        scenes = []
        
        # 列出prefix下的所有场景文件夹
        scene_folders = self.list_bos_folders(bucket, prefix)
        
        print(f"\nFound {len(scene_folders)} potential scene(s) in BOS")
        
        for scene_name in sorted(scene_folders):
            scene_prefix = f"{prefix}/{scene_name}".replace('//', '/')
            scene_config = self.scan_bos_scene(bucket, scene_prefix, scene_name)
            if scene_config:
                scenes.append(scene_config)
        
        print("\n" + "="*70)
        print(f"Scan completed: {len(scenes)}/{len(scene_folders)} scene(s) processed successfully")
        
        # 保存累加的数据到 JSON
        if scenes and not self.dry_run:
            self._save_to_json()
            print(f"\nDatabase saved: {self.db_path}")
            print(f"JSON summary saved: {self.json_path}")
        elif self.dry_run:
            print(f"\n[DRY RUN] Would save to:")
            print(f"  Database: {self.db_path}")
            print(f"  JSON: {self.json_path}")
        
        return scenes
    
    def _scan_local_scenes(self, root_dir: Path) -> List[Dict]:
        """扫描本地场景（原有逻辑）"""
        if not root_dir.exists():
            print(f"Error: Directory does not exist: {root_dir}")
            return []
        
        print(f"Scanning root directory: {root_dir}")
        print(f"Dry run mode: {self.dry_run}")
        print(f"Exclude map patterns: {self.exclude_map_names}")
        print(f"Fallback markers: {self.fallback_markers}")
        print("="*70)
        
        scenes = []
        scene_dirs = [d for d in root_dir.iterdir() if d.is_dir()]
        
        print(f"\nFound {len(scene_dirs)} potential scene(s)")
        
        for scene_dir in sorted(scene_dirs):
            scene_config = self.scan_scene(scene_dir)
            if scene_config:
                scenes.append(scene_config)
        
        print("\n" + "="*70)
        print(f"Scan completed: {len(scenes)}/{len(scene_dirs)} scene(s) processed successfully")
        
        # 保存累加的数据到 JSON
        if scenes and not self.dry_run:
            self._save_to_json()
            print(f"\nDatabase saved: {self.db_path}")
            print(f"JSON summary saved: {self.json_path}")
        elif self.dry_run:
            print(f"\n[DRY RUN] Would save to:")
            print(f"  Database: {self.db_path}")
            print(f"  JSON: {self.json_path}")
        
        return scenes
    
    def query_scene(self, scene_name: str) -> Optional[Dict]:
        """从数据库查询单个场景信息"""
        if not self.db_path.exists():
            return None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT * FROM scenes WHERE scene_name = ?', (scene_name,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            scene_name, launch_dir, content_path, launch_dir_path, base_game_path, last_updated = row
            
            # 读取该场景的所有地图
            cursor.execute('SELECT map_name, map_path FROM maps WHERE scene_name = ? ORDER BY map_name', 
                         (scene_name,))
            maps = [{'name': name, 'path': path} for name, path in cursor.fetchall()]
            
            return {
                'scene_name': scene_name,
                'launch_directory': launch_dir,
                'content_path': content_path,
                'launch_directory_path': launch_dir_path,
                'base_game_path': base_game_path,
                'maps': maps,
                'last_updated': last_updated
            }
        finally:
            conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='扫描场景目录结构并生成scene.json配置文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描本地目录（数据保存到 database/scenes.json 和 scenes.db）
  python scan_scene_structure.py D:/UE/Scenes
  
  # 扫描BOS目录
  python scan_scene_structure.py --bos --bucket world-data --prefix raw
  
  # 预览模式（不创建文件）
  python scan_scene_structure.py D:/UE/Scenes --dry-run
  
  # 使用自定义配置
  python scan_scene_structure.py D:/UE/Scenes --config config/scan_config.json
  
  # 自定义数据库目录
  python scan_scene_structure.py D:/UE/Scenes --database-dir D:/MyDatabase
  
  # BOS扫描示例
  python scan_scene_structure.py --bos --bucket world-data --prefix raw --bos-config config/bos_config.json
        """
    )
    
    parser.add_argument('directory',
                       nargs='?',
                       help='要扫描的根目录路径（本地扫描模式）')
    
    parser.add_argument('--bos',
                       action='store_true',
                       help='使用BOS扫描模式')
    
    parser.add_argument('--bucket',
                       help='BOS bucket名称（BOS模式必需）')
    
    parser.add_argument('--prefix',
                       help='BOS前缀路径（BOS模式必需）')
    
    parser.add_argument('--bos-config',
                       help='BOS配置文件路径（可选，默认自动查找）')
    
    parser.add_argument('--config', '-c',
                       help='扫描配置文件路径（可选）')
    
    parser.add_argument('--dry-run', '-d',
                       action='store_true',
                       help='预览模式，不创建Content目录和数据库文件')
    
    parser.add_argument('--database-dir',
                       help='数据库目录路径（默认：项目根目录/database）')
    
    parser.add_argument('--db-name',
                       help='数据库文件名前缀（默认：本地=scenes，BOS=scenes_bos）')
    
    args = parser.parse_args()
    
    # 参数验证
    if args.bos:
        if not args.bucket or not args.prefix:
            print("Error: BOS mode requires --bucket and --prefix")
            return 1
    else:
        if not args.directory:
            print("Error: Local mode requires directory argument")
            return 1
        
        # 验证目录
        root_dir = Path(args.directory).resolve()
        
        if not root_dir.exists():
            print(f"Error: Directory does not exist: {root_dir}")
            return 1
    
    # 创建扫描器
    scanner = SceneStructureScanner(
        config_path=args.config,
        dry_run=args.dry_run,
        database_dir=args.database_dir,
        use_bos=args.bos,
        bos_config=args.bos_config,
        db_name=args.db_name
    )
    
    # 扫描所有场景
    if args.bos:
        scenes = scanner.scan_all_scenes(
            bos_bucket=args.bucket,
            bos_prefix=args.prefix
        )
    else:
        scenes = scanner.scan_all_scenes(root_dir=root_dir)
    
    return 0 if scenes else 1


if __name__ == '__main__':
    exit(main())
