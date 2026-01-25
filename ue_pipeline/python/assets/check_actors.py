#!/usr/bin/env python3
"""
场景Actor数量检测工具
扫描项目中的场景，检测每个地图的StaticMeshActor数量
自动标记低于阈值的场景为low_actor
"""

import argparse
import json
import sys
from pathlib import Path

script_dir = Path(__file__).parent.parent.parent  # python/navmesh -> python -> ue_pipeline
repo_root = script_dir.parent  # WorldDataPipeline
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ue_pipeline.python.core import logger
from ue_pipeline.python.navmesh.batch_bake import BatchBakeManager


def main():
    parser = argparse.ArgumentParser(
        description='检测场景Actor数量并标记low_actor场景',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
说明:
  此脚本需要在UE Python环境中运行，用于检测场景中的StaticMeshActor数量
  低于阈值的场景会被标记为low_actor，批量烘焙时会跳过
  
  使用worker_bake_navmesh.py中的检测逻辑
        """
    )
    
    parser.add_argument('--threshold', '-t',
                       type=int,
                       default=50,
                       help='Actor数量阈值（默认：50）')
    
    parser.add_argument('--database-dir',
                       help='数据库目录路径（默认：项目根目录/database）')
    
    args = parser.parse_args()
    
    logger.header("Scene Actor Detection Tool")
    logger.kv("Threshold:", str(args.threshold))
    
    manager = BatchBakeManager(database_dir=args.database_dir)
    
    # 加载数据库
    db_scenes = manager.load_scenes_from_json()
    
    if not db_scenes:
        logger.error("No scenes found in database")
        return 1
    
    logger.info(f"Loaded {len(db_scenes)} scenes from database")
    logger.blank(1)
    
    # 扫描项目场景
    project_scenes = manager.scan_project_scenes()
    matched_scen
    
    es = manager.match_scenes(db_scenes, project_scenes)
    
    logger.blank(1)
    logger.info(f"Found {len(matched_scenes)} matching scenes")
    logger.separator(width=70)
    
    # 注意：实际的Actor检测需要在UE环境中运行
    # 这里只是演示框架
    logger.warning("Note: Actual actor detection requires UE Python environment")
    logger.warning("Use worker_bake_navmesh.py logic for detection")
    logger.blank(1)
    
    # 示例：手动标记场景
    logger.info("To mark a scene as low_actor manually:")
    logger.info("  manager.update_scene_metadata('SceneName', {'low_actor': True})")
    
    return 0


if __name__ == '__main__':
    exit(main())
