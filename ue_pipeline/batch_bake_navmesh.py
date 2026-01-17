#!/usr/bin/env python3
"""
批量NavMesh烘焙作业系统
基于scenes.json数据库，自动扫描项目中的场景并依次烘焙每个地图
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

script_dir = Path(__file__).parent
repo_root = script_dir.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ue_pipeline.python.logger import logger
from ue_pipeline.python import job_utils


class BatchBakeManager:
    def __init__(self, database_dir: str = None, project_content_dir: str = None, db_name: str = 'scenes'):
        """
        Args:
            database_dir: 数据库目录，默认为项目根目录/database
            project_content_dir: UE项目Content目录路径
            db_name: 数据库文件名前缀，默认为'scenes'（本地），可指定'scenes_bos'（BOS）
        """
        # 数据库路径
        if database_dir:
            self.database_dir = Path(database_dir)
        else:
            self.database_dir = repo_root / 'database'
        
        self.db_path = self.database_dir / f'{db_name}.db'
        self.json_path = self.database_dir / f'{db_name}.json'
        
        # UE项目Content目录
        if project_content_dir:
            self.project_content_dir = Path(project_content_dir)
        else:
            # 从ue_config.json读取
            config = job_utils.load_default_ue_config()
            project_path = Path(config['project_path'])
            self.project_content_dir = project_path.parent / 'Content'
        
        logger.info(f"Database: {self.json_path}")
        logger.info(f"Project Content: {self.project_content_dir}")
    
    def load_scenes_from_json(self) -> Dict:
        """从scenes.json加载场景数据"""
        if not self.json_path.exists():
            logger.error(f"Database not found: {self.json_path}")
            return {}
        
        with open(self.json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data.get('scenes', {})
    
    def load_scenes_from_db(self) -> Dict:
        """从SQLite数据库加载场景数据"""
        if not self.db_path.exists():
            logger.error(f"Database not found: {self.db_path}")
            return {}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        scenes = {}
        try:
            cursor.execute('SELECT * FROM scenes ORDER BY scene_name')
            for row in cursor.fetchall():
                scene_name, launch_dir, content_path, launch_dir_path, base_game_path, last_updated = row
                
                # 读取该场景的所有地图
                cursor.execute('SELECT map_name, map_path FROM maps WHERE scene_name = ? ORDER BY map_name', 
                             (scene_name,))
                maps = [{'name': name, 'path': path} for name, path in cursor.fetchall()]
                
                scenes[scene_name] = {
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
        
        return scenes
    
    def scan_project_scenes(self) -> List[str]:
        """扫描项目Content目录，返回存在的启动目录名列表"""
        if not self.project_content_dir.exists():
            logger.error(f"Project Content directory not found: {self.project_content_dir}")
            return []
        
        scene_dirs = []
        for item in self.project_content_dir.iterdir():
            if item.is_dir():
                scene_dirs.append(item.name)
        
        return scene_dirs
    
    def match_scenes(self, db_scenes: Dict, project_scenes: List[str]) -> List[Dict]:
        """
        匹配数据库中的场景与项目中的场景
        基于launch_directory进行匹配
        
        Returns:
            匹配成功的场景列表
        """
        matched = []
        
        for scene_name, scene_data in db_scenes.items():
            launch_dir = scene_data['launch_directory']
            
            if launch_dir in project_scenes:
                matched.append(scene_data)
                logger.info(f"✓ Matched: {scene_name} ({launch_dir})")
            else:
                logger.warning(f"✗ Not found in project: {scene_name} ({launch_dir})")
        
        return matched
    
    def update_scene_metadata(self, scene_name: str, updates: Dict):
        """
        更新场景的元数据到数据库
        
        Args:
            scene_name: 场景名
            updates: 更新的字段，如 {'low_actor': True, 'baked': True, 'last_baked': '2026-01-16 10:30:00'}
        """
        # 更新JSON
        if self.json_path.exists():
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if scene_name in data.get('scenes', {}):
                data['scenes'][scene_name].update(updates)
                data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                with open(self.json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        
        # 更新SQLite（如果表结构支持）
        # 注意：需要先修改scan_scene_structure.py的数据库表结构
        if self.db_path.exists():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 检查列是否存在，如果不存在则添加
                cursor.execute("PRAGMA table_info(scenes)")
                columns = [col[1] for col in cursor.fetchall()]
                
                for field in ['low_actor', 'baked', 'last_baked']:
                    if field not in columns:
                        if field in ['low_actor', 'baked']:
                            cursor.execute(f"ALTER TABLE scenes ADD COLUMN {field} INTEGER DEFAULT 0")
                        else:
                            cursor.execute(f"ALTER TABLE scenes ADD COLUMN {field} TEXT")
                
                # 构建UPDATE语句
                set_clauses = []
                values = []
                for key, value in updates.items():
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
                
                if set_clauses:
                    values.append(scene_name)
                    sql = f"UPDATE scenes SET {', '.join(set_clauses)} WHERE scene_name = ?"
                    cursor.execute(sql, values)
                    conn.commit()
            finally:
                conn.close()
    
    def create_job_manifest(self, scene_data: Dict, map_path: str, job_id: str) -> Dict:
        """
        创建烘焙作业配置
        
        Args:
            scene_data: 场景数据
            map_path: 地图路径（如 /Game/CanyonScans/Maps/Canyon_DemoScene）
            job_id: 作业ID
        """
        manifest = {
            "job_id": job_id,
            "job_type": "bake_navmesh",
            "navmesh_config": {
                "scale_margin": 1.2,
                "min_scale": [20.0, 20.0, 5.0],
                "max_scale": [500.0, 500.0, 5.0],
                "agent_max_step_height": 50.0,
                "agent_max_jump_height": 200.0,
                "wait_for_build": True,
                "build_timeout": 120,
                "verify_navmesh": True,
                "maps": [map_path]
            }
        }
        
        return manifest
    
    def run_bake_job(self, manifest: Dict) -> int:
        """
        执行烘焙作业
        
        Returns:
            退出码，0表示成功
        """
        # 创建临时manifest文件
        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='batch_bake_')
        
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            
            # 调用run_bake_navmesh.py
            bake_script = script_dir / 'run_bake_navmesh.py'
            cmd = [sys.executable, str(bake_script), temp_path]
            
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=False)
            
            return result.returncode
        finally:
            try:
                Path(temp_path).unlink()
            except:
                pass
    
    def batch_bake(self, skip_low_actor: bool = True, dry_run: bool = False):
        """
        批量烘焙所有匹配的场景
        
        Args:
            skip_low_actor: 是否跳过低actor场景
            dry_run: 预览模式，不实际执行
        """
        logger.header("Batch NavMesh Bake System")
        
        # 加载数据库（优先使用JSON，因为更易读）
        logger.info("Loading database...")
        db_scenes = self.load_scenes_from_json()
        
        if not db_scenes:
            logger.warning("Trying SQLite database...")
            db_scenes = self.load_scenes_from_db()
        
        if not db_scenes:
            logger.error("No scenes found in database")
            return 1
        
        logger.info(f"Loaded {len(db_scenes)} scenes from database")
        logger.blank(1)
        
        # 扫描项目场景
        logger.info("Scanning project Content directory...")
        project_scenes = self.scan_project_scenes()
        logger.info(f"Found {len(project_scenes)} directories in project: {project_scenes}")
        logger.blank(1)
        
        # 匹配场景
        logger.info("Matching scenes...")
        matched_scenes = self.match_scenes(db_scenes, project_scenes)
        
        if not matched_scenes:
            logger.error("No matching scenes found")
            return 1
        
        logger.blank(1)
        logger.info(f"Found {len(matched_scenes)} matching scenes to bake")
        logger.separator(width=70)
        
        # 统计信息
        total_maps = sum(len(s['maps']) for s in matched_scenes)
        processed_maps = 0
        succeeded_maps = 0
        skipped_maps = 0
        failed_maps = 0
        
        # 依次处理每个场景
        for scene_idx, scene_data in enumerate(matched_scenes, 1):
            scene_name = scene_data['scene_name']
            launch_dir = scene_data['launch_directory']
            maps = scene_data['maps']
            
            logger.blank(1)
            logger.info(f"[SCENE {scene_idx}/{len(matched_scenes)}] {scene_name}")
            logger.info(f"Launch Directory: {launch_dir}")
            logger.info(f"Maps: {len(maps)}")
            
            # 检查是否为low_actor场景
            is_low_actor = scene_data.get('low_actor', False)
            if is_low_actor and skip_low_actor:
                logger.warning(f"Skipping {scene_name} (marked as low_actor)")
                skipped_maps += len(maps)
                continue
            
            # 处理每个地图
            for map_idx, map_info in enumerate(maps, 1):
                map_name = map_info['name']
                map_path = map_info['path']
                
                job_id = f"batch_bake_{scene_name}_{map_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                
                logger.blank(1)
                logger.info(f"  [MAP {map_idx}/{len(maps)}] {map_name}")
                logger.info(f"  Path: {map_path}")
                logger.info(f"  Job ID: {job_id}")
                
                processed_maps += 1
                
                if dry_run:
                    logger.info(f"  [DRY RUN] Would bake this map")
                    succeeded_maps += 1
                else:
                    # 创建作业配置
                    manifest = self.create_job_manifest(scene_data, map_path, job_id)
                    
                    # 执行烘焙
                    logger.info(f"  Starting bake job...")
                    exit_code = self.run_bake_job(manifest)
                    
                    if exit_code == 0:
                        logger.info(f"  ✓ Bake succeeded")
                        succeeded_maps += 1
                        
                        # 更新数据库
                        self.update_scene_metadata(scene_name, {
                            'baked': True,
                            'last_baked': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                    else:
                        logger.error(f"  ✗ Bake failed with exit code: {exit_code}")
                        failed_maps += 1
            
            logger.separator(width=70)
        
        # 最终统计
        logger.blank(1)
        logger.header("Batch Bake Summary")
        logger.kv("Total Scenes:", str(len(matched_scenes)))
        logger.kv("Total Maps:", str(total_maps))
        logger.kv("Processed:", str(processed_maps))
        logger.kv("Succeeded:", str(succeeded_maps))
        logger.kv("Skipped:", str(skipped_maps))
        logger.kv("Failed:", str(failed_maps))
        
        return 0 if failed_maps == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description='批量NavMesh烘焙系统 - 基于数据库自动烘焙所有场景',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 批量烘焙所有场景（本地数据库）
  python batch_bake_navmesh.py
  
  # 使用BOS数据库
  python batch_bake_navmesh.py --db-name scenes_bos
  
  # 预览模式
  python batch_bake_navmesh.py --dry-run
  
  # 包含低actor场景
  python batch_bake_navmesh.py --include-low-actor
  
  # 指定数据库目录
  python batch_bake_navmesh.py --database-dir D:/MyDatabase
        """
    )
    
    parser.add_argument('--database-dir',
                       help='数据库目录路径（默认：项目根目录/database）')
    
    parser.add_argument('--project-content',
                       help='UE项目Content目录路径（默认：从ue_config.json读取）')
    
    parser.add_argument('--dry-run', '-d',
                       action='store_true',
                       help='预览模式，不实际执行烘焙')
    
    parser.add_argument('--include-low-actor',
                       action='store_true',
                       help='包含低actor场景（默认跳过）')
    
    parser.add_argument('--db-name',
                       default='scenes',
                       help='数据库文件名前缀（默认：scenes，BOS场景使用：scenes_bos）')
    
    args = parser.parse_args()
    
    # 创建批处理管理器
    manager = BatchBakeManager(
        database_dir=args.database_dir,
        project_content_dir=args.project_content,
        db_name=args.db_name
    )
    
    # 执行批量烘焙
    exit_code = manager.batch_bake(
        skip_low_actor=not args.include_low_actor,
        dry_run=args.dry_run
    )
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
