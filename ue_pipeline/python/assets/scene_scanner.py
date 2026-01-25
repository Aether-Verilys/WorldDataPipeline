"""
场景扫描工具模块
提供UE工程中场景、地图、序列的扫描和查询功能
支持本地路径和BOS路径扫描
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# 添加项目根目录到 Python 路径
script_dir = Path(__file__).parent
repo_root = script_dir.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ue_pipeline.python.core import logger
from .scene_registry import SceneRegistry

# BOS 支持（可选）
try:
    from ..storage import BosClientManager
    HAS_BOS = True
except ImportError:
    HAS_BOS = False


def load_scan_config(config_path: str = "ue_pipeline/config/scan_config.json") -> dict:
    default_config = {
        "exclude_map_names": ["Overview", "prop", "test", "Test", "Presentation"]
    }
    
    config_file = Path(config_path)
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config
        except Exception as e:
            logger.warning(f"读取扫描配置失败: {e}，使用默认配置")
    
    return default_config


def should_exclude_map(map_name: str, exclude_patterns: list[str]) -> bool:
    """
    检查地图名是否应该被排除
    
    Args:
        map_name: 地图名称
        exclude_patterns: 排除模式列表
    
    Returns:
        如果应该排除返回 True
    """
    for pattern in exclude_patterns:
        if pattern.lower() in map_name.lower():
            return True
    return False


def build_ue_asset_path(relative_path: Path, base_game_path: str, asset_name: str) -> str:
    """
    构建 UE 资产路径
    
    Args:
        relative_path: 相对于启动目录的路径
        base_game_path: 基础游戏路径 (如 /Game/SceneName)
        asset_name: 资产名称
    
    Returns:
        完整的 UE 资产路径
    """
    path_parts = relative_path.parts[:-1] if relative_path.parts else []
    if path_parts:
        return f"{base_game_path}/{'/'.join(path_parts)}/{asset_name}"
    return f"{base_game_path}/{asset_name}"


def scan_local_scene_folders(project_path: str) -> list[str]:
    """
    扫描当前UE工程的Content目录，获取所有场景文件夹
    排除UE系统目录
    
    Args:
        project_path: UE项目文件路径 (.uproject)
    
    Returns:
        场景文件夹名称列表
    """
    # UE系统目录，需要排除
    EXCLUDED_FOLDERS = {
        'FirstPerson',
        'CameraController', 
        'Collections',
        'Developers',
        'Input',
        '__ExternalActors__',
        '__ExternalObjects__'
    }
    
    project_dir = Path(project_path).parent
    content_dir = project_dir / "Content"
    
    if not content_dir.exists():
        logger.error(f"Content目录不存在: {content_dir}")
        return []
    
    # 获取Content下的所有子目录（排除系统目录）
    scene_folders = []
    for item in content_dir.iterdir():
        if item.is_dir() and not item.name.startswith('_') and item.name not in EXCLUDED_FOLDERS:
            scene_folders.append(item.name)
    
    return sorted(scene_folders)


def scan_scene_maps(project_path: str, scene_name: str, exclude_names: list[str]) -> list[dict]:
    """
    扫描场景文件夹下的所有.umap文件
    
    Args:
        project_path: UE项目路径
        scene_name: 场景名称
        exclude_names: 要排除的地图名称列表
    
    Returns:
        地图信息列表 [{"map_name": "...", "map_path": "..."}, ...]
    """
    project_dir = Path(project_path).parent
    scene_dir = project_dir / "Content" / scene_name
    
    if not scene_dir.exists():
        return []
    
    # 递归查找所有.umap文件
    maps = []
    for umap_file in scene_dir.rglob("*.umap"):
        map_name = umap_file.stem
        
        # 检查是否在排除列表中
        if should_exclude_map(map_name, exclude_names):
            continue
        
        # 构建UE资产路径
        # Content/Hong_Kong_Street/Maps/Level.umap -> /Game/Hong_Kong_Street/Maps/Level
        rel_path = umap_file.relative_to(project_dir / "Content")
        base_path = "/Game/" + "/".join(rel_path.parts[:-1])
        ue_path = f"{base_path}/{map_name}"
        
        maps.append({
            "map_name": map_name,
            "map_path": ue_path
        })
    
    return maps


def scan_local_sequences(project_path: str, sequence_dir: str) -> list:
    """
    扫描序列目录下的所有序列资产
    
    Args:
        project_path: UE项目路径
        sequence_dir: 序列目录的UE资产路径 (e.g., /Game/SceneName/Sequence)
    
    Returns:
        序列UE资产路径列表
    """
    # Convert UE asset path to local file system path
    # /Game/SceneName/Sequence -> Content/SceneName/Sequence
    ue_path_parts = sequence_dir.split('/')
    if len(ue_path_parts) >= 2 and ue_path_parts[1] == 'Game':
        relative_path = '/'.join(ue_path_parts[2:])  # Remove /Game
        project_dir = Path(project_path).parent
        content_dir = project_dir / 'Content' / relative_path
        
        logger.info(f"Scanning local directory: {content_dir}")
        
        if not content_dir.exists():
            logger.error(f"Directory does not exist: {content_dir}")
            return []
        
        # Find all .uasset files (LevelSequence assets)
        sequences = []
        for uasset_file in content_dir.glob('*.uasset'):
            # Convert back to UE asset path
            # Content/SceneName/Sequence/MySeq.uasset -> /Game/SceneName/Sequence/MySeq
            asset_name = uasset_file.stem
            ue_asset_path = f"{sequence_dir}/{asset_name}"
            sequences.append(ue_asset_path)
            logger.info(f"  Found: {ue_asset_path}")
        
        return sorted(sequences)
    else:
        logger.error(f"Invalid UE asset path format: {sequence_dir}")
        return []


def load_scenes_json(json_path: str = "database/scenes.json") -> dict:
    """
    加载 scenes.json 数据库
    
    Args:
        json_path: JSON文件路径
    
    Returns:
        场景数据字典
    """
    json_file = Path(json_path)
    if json_file.exists():
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('scenes', {})
        except Exception as e:
            logger.warning(f"读取 scenes.json 失败: {e}")
    return {}


def find_scene_by_launch_directory(scenes_data: dict, launch_dir: str) -> tuple:
    """
    通过 launch_directory 查找场景
    
    Args:
        scenes_data: 场景数据字典 (from scenes.json)
        launch_dir: 启动目录名称
    
    Returns:
        (scene_name, scene_data) 或 (None, None)
    """
    for scene_name, scene_info in scenes_data.items():
        if scene_info.get('launch_directory') == launch_dir:
            return scene_name, scene_info
    return None, None


def select_scene_from_local_project(registry: SceneRegistry, project_path: str, 
                                    scan_config: dict) -> tuple[str, list]:
    """
    扫描本地工程的场景文件夹（以本地为准），同时标记数据库状态
    
    Args:
        registry: SceneRegistry 实例
        project_path: UE项目路径
        scan_config: 扫描配置
    
    Returns:
        (scene_name, maps): 场景名称和地图列表
    """
    exclude_names = scan_config.get('exclude_map_names', [])
    
    # 加载 scenes.json 数据库（用于标记）
    scenes_json = load_scenes_json()
    
    # 扫描本地场景文件夹
    logger.info("扫描当前工程的场景文件夹...")
    scene_folders = scan_local_scene_folders(project_path)
    
    if not scene_folders:
        logger.error("未找到任何场景文件夹")
        logger.info(f"请检查项目路径: {project_path}")
        sys.exit(1)
    
    logger.info(f"找到 {len(scene_folders)} 个场景文件夹:")
    for folder in scene_folders:
        logger.info(f"  - {folder}")
    logger.blank(1)
    
    # 对每个场景，扫描地图并检查数据库状态
    available_scenes = []
    
    for folder_name in scene_folders:
        logger.info(f"扫描场景: {folder_name}")
        
        # 扫描本地地图文件
        maps = scan_scene_maps(project_path, folder_name, exclude_names)
        
        if not maps:
            logger.warning(f"  ✗ 未找到任何地图")
            logger.blank(1)
            continue
        
        # 检查数据库状态（用于标记）
        db_status = []
        scene_name = folder_name  # 默认使用文件夹名
        
        # 检查 SQLite
        scene_info_sqlite = registry.get_scene(folder_name)
        if scene_info_sqlite:
            db_status.append("SQLite✓")
        
        # 检查 scenes.json (通过 launch_directory)
        if scenes_json:
            scene_name_json, scene_data_json = find_scene_by_launch_directory(scenes_json, folder_name)
            if scene_name_json:
                db_status.append("scenes.json✓")
                scene_name = scene_name_json  # 使用数据库中的正式名称
        
        # 显示结果
        status_str = ", ".join(db_status) if db_status else "仅本地"
        logger.info(f"  ✓ 找到 {len(maps)} 个地图 [{status_str}]")
        
        available_scenes.append((scene_name, maps, status_str))
        logger.blank(1)
    
    if not available_scenes:
        logger.error("没有找到包含地图的场景")
        sys.exit(1)
    
    # 如果只有一个场景，自动选择
    if len(available_scenes) == 1:
        scene_name, maps, status = available_scenes[0]
        logger.info(f"自动选择唯一场景: {scene_name} (包含 {len(maps)} 个地图)")
        return scene_name, maps
    
    # 多个场景，让用户选择
    logger.separator(width=60, char='-')
    logger.info(f"找到 {len(available_scenes)} 个可用场景:")
    logger.blank(1)
    for idx, (scene_name, maps, status) in enumerate(available_scenes, 1):
        logger.info(f"  {idx}. {scene_name} ({len(maps)} 个地图) [{status}]")
        for map_info in maps[:3]:  # 只显示前3个地图
            logger.info(f"     - {map_info['map_name']}: {map_info['map_path']}")
        if len(maps) > 3:
            logger.info(f"     ... 还有 {len(maps) - 3} 个地图")
    logger.blank(1)
    
    # 读取用户输入
    while True:
        try:
            choice = input(f"请选择场景 (1-{len(available_scenes)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(available_scenes):
                scene_name, maps, status = available_scenes[idx]
                logger.info(f"已选择场景: {scene_name}")
                return scene_name, maps
            else:
                print(f"无效选择，请输入 1-{len(available_scenes)}")
        except ValueError:
            print("请输入数字")
        except KeyboardInterrupt:
            logger.info("\n操作已取消")
            sys.exit(0)


def ensure_output_directory(output_path: str):
    """
    确保输出目录存在，不存在则创建
    
    Args:
        output_path: 输出目录路径
    """
    if output_path:
        abs_output_path = os.path.abspath(output_path)
        if not os.path.exists(abs_output_path):
            os.makedirs(abs_output_path, exist_ok=True)
            logger.info(f"Created output directory: {abs_output_path}")


# ============================================================
# SceneStructureScanner - 完整场景结构扫描器
# ============================================================

class SceneStructureScanner:
    """
    场景结构扫描器
    支持本地和BOS场景扫描，保存到SQLite数据库和JSON文件
    """
    
    def __init__(self, config_path: str = None, dry_run: bool = False, 
                 database_dir: str = None, use_bos: bool = False, 
                 bos_config: str = None, db_name: str = None):
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
        return should_exclude_map(map_name, self.exclude_map_names)
    
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
                    relative_path = obj_key[len(search_prefix):].lstrip('/')
                    rel_path = Path(relative_path)
                    ue_path = build_ue_asset_path(rel_path, base_game_path, map_name)
                    
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
        """扫描BOS上的单个场景"""
        print(f"\nScanning BOS scene: {scene_name}")
        print(f"  Bucket: {bucket}")
        print(f"  Prefix: {scene_prefix}")
        
        # 查找Content目录
        content_prefix = self.find_bos_content_folder(bucket, scene_prefix)
        
        if not content_prefix:
            print(f"  Warning: No Content folder found, skipping")
            return None
        
        print(f"  Found Content: {content_prefix}")
        
        # 获取启动目录名（Content下一级）
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
        if not self.dry_run:
            self._save_to_database(scene_config)
            print(f"  Updated database")
        else:
            print(f"  [DRY RUN] Would update database")
        
        return scene_config
    
    def scan_all_scenes(self, root_dir: Path = None, bos_bucket: str = None, bos_prefix: str = None) -> List[Dict]:
        """扫描根目录或BOS前缀下的所有场景"""
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
            scene_prefix = f"{prefix}/{scene_name}"
            scene_config = self.scan_bos_scene(bucket, scene_prefix, scene_name)
            if scene_config:
                scenes.append(scene_config)
        
        print("\n" + "="*70)
        print(f"Scan completed: {len(scenes)}/{len(scene_folders)} scene(s) processed successfully")
        
        # 保存累加的数据到 JSON
        if scenes and not self.dry_run:
            self._save_to_json()
            print(f"\nDatabase and JSON saved:")
            print(f"  - {self.db_path}")
            print(f"  - {self.json_path}")
        
        return scenes
    
    def _scan_local_scenes(self, root_dir: Path) -> List[Dict]:
        """扫描本地场景"""
        print(f"Scanning local directory: {root_dir}")
        print(f"Dry run mode: {self.dry_run}")
        print(f"Exclude map patterns: {self.exclude_map_names}")
        print("="*70)
        
        if not root_dir.exists():
            print(f"Error: Directory does not exist: {root_dir}")
            return []
        
        # 查找所有子目录作为场景
        scene_dirs = [d for d in root_dir.iterdir() if d.is_dir()]
        
        print(f"\nFound {len(scene_dirs)} potential scene(s)")
        
        scenes = []
        for scene_path in sorted(scene_dirs):
            scene_config = self.scan_scene(scene_path)
            if scene_config:
                scenes.append(scene_config)
        
        print("\n" + "="*70)
        print(f"Scan completed: {len(scenes)}/{len(scene_dirs)} scene(s) processed successfully")
        
        # 保存到 JSON
        if scenes and not self.dry_run:
            self._save_to_json()
            print(f"\nDatabase and JSON saved:")
            print(f"  - {self.db_path}")
            print(f"  - {self.json_path}")
        
        return scenes
    
    def scan_scene(self, scene_path: Path) -> Optional[Dict]:
        """扫描单个本地场景"""
        scene_name = scene_path.name
        print(f"\nScanning scene: {scene_name}")
        print(f"  Path: {scene_path}")
        
        # 查找Content目录
        content_path = self.find_content_folder(scene_path)
        
        if content_path:
            print(f"  Found Content: {content_path}")
            launch_dir_path = content_path / self.get_launch_directory_name(content_path)
            launch_dir_name = launch_dir_path.name
        else:
            print(f"  No Content folder found, skipping")
            return None
        
        print(f"  Launch directory: {launch_dir_name}")
        
        # 扫描.umap文件
        base_game_path = f"/Game/{launch_dir_name}"
        maps = self.find_umap_files(launch_dir_path, base_game_path)
        
        print(f"  Found {len(maps)} valid map(s)")
        for map_info in maps:
            print(f"    - {map_info['name']}: {map_info['path']}")
        
        # 构建场景配置
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
        
        # 保存到数据库
        if not self.dry_run:
            self._save_to_database(scene_config)
            print(f"  Updated database")
        else:
            print(f"  [DRY RUN] Would update database")
        
        return scene_config
    
    def find_content_folder(self, scene_path: Path) -> Optional[Path]:
        """在场景目录中查找Content文件夹"""
        for root, dirs, files in os.walk(scene_path):
            if 'Content' in dirs:
                return Path(root) / 'Content'
        return None
    
    def get_launch_directory_name(self, content_path: Path) -> str:
        """获取启动目录名（Content下一级的第一个目录）"""
        subdirs = [d for d in content_path.iterdir() if d.is_dir()]
        if subdirs:
            return subdirs[0].name
        return content_path.parent.name
    
    def find_umap_files(self, search_path: Path, base_game_path: str) -> List[Dict[str, str]]:
        """查找.umap文件并转换为UE路径格式"""
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
                        continue
                    
                    # 构建UE路径
                    rel_path = file_path.relative_to(search_path)
                    ue_path = build_ue_asset_path(rel_path, base_game_path, map_name)
                    
                    maps.append({
                        "name": map_name,
                        "path": ue_path
                    })
        
        return sorted(maps, key=lambda x: x['name'])
