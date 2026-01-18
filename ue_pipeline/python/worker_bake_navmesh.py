import unreal
import sys
import os
import time
import json
import sqlite3
from pathlib import Path
from datetime import datetime

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import ue_api
from worker_common import load_json as _load_json, resolve_manifest_path_from_env as _resolve_manifest_path_from_env
from logger import logger
from assets_manager import save_current_level


def process_single_map(map_path: str, manager, navmesh_config: dict) -> dict:
    scale_margin = navmesh_config.get("scale_margin", 1.2)
    min_scale = navmesh_config.get("min_scale", [20.0, 20.0, 5.0])
    max_scale = navmesh_config.get("max_scale", [500.0, 500.0, 50.0])
    agent_max_step_height = navmesh_config.get("agent_max_step_height", 50.0)
    agent_max_jump_height = navmesh_config.get("agent_max_jump_height", 200.0)
    
    # 1. 加载地图
    if not ue_api.load_map(map_path):
        logger.error(f"Failed to load map: {map_path}")
        logger.error(f"Map file does not exist or cannot be loaded")
        logger.error(f"Aborting task - no point continuing if map doesn't exist")
        unreal.SystemLibrary.quit_editor()
        return {"success": False, "error": "Map file not found"}
    
    # 2. 统计StaticMeshActor数量
    logger.info("Counting StaticMeshActors...")
    mesh_count = manager.count_static_mesh_actors()
    is_low_mesh = mesh_count < 50
    logger.info(f"StaticMeshActor count: {mesh_count}")
    logger.info(f"LowMesh status: {is_low_mesh}")
    
    # 3. 更新数据库状态
    update_scene_low_actor_status(map_path, is_low_mesh)
    
    # 4. 记录文件修改时间
    level_path = map_path.replace("/Game/", "/Content/") + ".umap"
    project_path = Path(unreal.Paths.project_content_dir()).parent
    full_level_path = project_path / level_path.lstrip("/")
    pre_bake_mtime = None
    if full_level_path.exists():
        pre_bake_mtime = full_level_path.stat().st_mtime
        logger.info(f"Level file tracked: {full_level_path}")
    
    # 5. 添加或配置NavMesh
    logger.info("Using auto-scale mode...")
    navmesh = manager.auto_scale_navmesh(
        margin=scale_margin,
        min_scale=min_scale,
        max_scale=max_scale,
        agent_max_step_height=agent_max_step_height,
        agent_max_jump_height=agent_max_jump_height,
    )
    
    if not navmesh:
        logger.warning("NavMesh volume not created (may already exist)")
    else:
        logger.info("NavMeshBoundsVolume added successfully")
    
    logger.info("Phase 1 mode: Skipping build wait, will be triggered in Phase 2")
    
    # 6. 保存关卡
    logger.info(f"Saving level: {map_path}")
    save_start = time.time()
    try:
        save_current_level()
        save_elapsed = time.time() - save_start
        logger.info(f"Level saved successfully ({save_elapsed:.2f}s)")
        
        # 验证保存
        if full_level_path.exists():
            post_bake_mtime = full_level_path.stat().st_mtime
            if pre_bake_mtime and post_bake_mtime > pre_bake_mtime:
                logger.info("Save verified - file modified")
            elif pre_bake_mtime:
                logger.warning("File modification time unchanged")
    
    except Exception as e:
        logger.error(f"Failed to save level: {e}")
        return {
            "success": False, 
            "error": f"Failed to save: {e}",
            "mesh_count": mesh_count,
            "is_low_mesh": is_low_mesh
        }
    
    logger.info(f"Completed: {map_path}")
    logger.info(f"Map metadata: mesh_count={mesh_count}, low_mesh={is_low_mesh}")
    logger.plain("")
    
    return {
        "success": True, 
        "error": None,
        "mesh_count": mesh_count,
        "is_low_mesh": is_low_mesh
    }


def update_scene_low_actor_status(map_path: str, is_low_actor: bool):
    """更新场景的low_actor状态到数据库"""
    try:
        # 从地图路径提取场景名 /Game/LaunchDir/Maps/MapName -> LaunchDir
        path_parts = map_path.strip('/').split('/')
        if len(path_parts) < 2 or path_parts[0] != 'Game':
            logger.warning(f"Invalid map path format: {map_path}")
            return
        
        launch_dir = path_parts[1]  # 启动目录名
        
        # 获取数据库路径
        script_dir = Path(__file__).parent.parent
        repo_root = script_dir.parent
        db_dir = repo_root / 'database'
        db_path = db_dir / 'scenes.db'
        json_path = db_dir / 'scenes.json'
        
        if not db_path.exists():
            logger.warning(f"Database not found: {db_path}")
            return
        
        # 更新SQLite数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # 通过launch_directory查找场景
            cursor.execute('SELECT scene_name FROM scenes WHERE launch_directory = ?', (launch_dir,))
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"Scene not found in database: {launch_dir}")
                return
            
            scene_name = row[0]
            
            # 更新low_actor状态
            cursor.execute('''
                UPDATE scenes SET low_actor = ?, last_updated = ?
                WHERE scene_name = ?
            ''', (1 if is_low_actor else 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), scene_name))
            
            conn.commit()
            logger.info(f"Updated database: {scene_name} low_actor={is_low_actor}")
            
            # 同步更新JSON文件
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if scene_name in data.get('scenes', {}):
                    data['scenes'][scene_name]['low_actor'] = is_low_actor
                    data['scenes'][scene_name]['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    
                    logger.info(f"Updated JSON database")
        finally:
            conn.close()
            
    except Exception as e:
        logger.warning(f"Failed to update database: {e}")


def main(argv=None) -> int:
    logger.info("Starting NavMesh bake job execution...")
    # logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")

    argv = list(argv) if argv is not None else sys.argv

    env_key = "UE_NAVMESH_MANIFEST"
    manifest_path = _resolve_manifest_path_from_env(env_key, argv)
    if not manifest_path:
        logger.error("No manifest path provided")
        logger.info(f"sys.argv: {sys.argv}")
        logger.info(f"Environment vars: {env_key}={os.environ.get(env_key)}")
        return 1

    logger.info(f"Manifest: {manifest_path}")

    try:
        manifest = _load_json(manifest_path)
    except Exception as e:
        logger.error(f"Failed to read manifest: {e}")
        return 1

    job_id = manifest.get("job_id", "unknown")
    job_type = manifest.get("job_type", "unknown")

    logger.info(f"Job ID: {job_id}")
    logger.info(f"Job Type: {job_type}")

    if job_type != "bake_navmesh":
        logger.error(f"Invalid job type '{job_type}', expected 'bake_navmesh'")
        return 1

    navmesh_config = manifest.get("navmesh_config", {})

    maps = navmesh_config.get("maps", [])

    scale_margin = navmesh_config.get("scale_margin", 1.2)
    min_scale = navmesh_config.get("min_scale", [20.0, 20.0, 5.0])
    max_scale = navmesh_config.get("max_scale", [500.0, 500.0, 50.0])

    agent_max_step_height = navmesh_config.get("agent_max_step_height", 50.0)
    agent_max_jump_height = navmesh_config.get("agent_max_jump_height", 200.0)

    if not maps:
        logger.error("No maps specified in navmesh_config")
        return 1

    logger.info(f"Scale margin: {scale_margin}")
    logger.info(f"Min scale: {min_scale}")
    logger.info(f"Max scale: {max_scale}")
    logger.info(f"Agent MaxStepHeight: {agent_max_step_height} cm")
    logger.info(f"Agent MaxJumpHeight: {agent_max_jump_height} cm")
    logger.info(f"Maps to process: {len(maps)}")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    from pre_process.add_navmesh_to_scene import NavMeshManager

    try:
        manager = NavMeshManager()
        total_maps = len(maps)
        success_count = 0
        failed_count = 0
        failed_maps = []

        logger.info("=" * 60)
        logger.info("Starting NavMesh Bake Process")
        logger.info("=" * 60)

        for i, map_path in enumerate(maps, 1):
            logger.info(f"[{i}/{total_maps}] Processing: {map_path}")
            
            result = process_single_map(map_path, manager, navmesh_config)
            
            if result["success"]:
                success_count += 1
            else:
                failed_count += 1
                failed_maps.append({"map": map_path, "error": result["error"]})
                # 如果是地图文件不存在，直接退出
                if "Map file not found" in result["error"]:
                    return 1

        logger.info("=" * 60)
        logger.info("NavMesh Bake Process Complete")
        logger.info("=" * 60)
        logger.info(f"Total maps: {total_maps}")
        logger.info(f"Success: {success_count}")
        logger.info(f"Failed: {failed_count}")

        if failed_maps:
            logger.info("Failed maps details:")
            for failed in failed_maps:
                logger.plain(f"  - {failed['map']}: {failed['error']}")

        logger.info("=" * 60)

        if failed_count > 0:
            logger.warning(f"{failed_count} map(s) failed")
            return 1
        else:
            logger.info("All maps processed successfully")
            return 0

    except Exception as e:
        logger.error(f"Failed to execute NavMesh bake job: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
