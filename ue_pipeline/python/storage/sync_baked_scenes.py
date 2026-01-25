"""
从 BOS 同步已烘焙场景到数据库
扫描 BOS baked/ 目录，将找到的场景添加到数据库并标记为已烘焙
"""

import subprocess
import json
import sys
from pathlib import Path

# 添加路径以便导入 scene_registry
sys.path.insert(0, str(Path(__file__).parent / 'python'))

from scene_registry import SceneRegistry


def list_bos_scenes(bucket: str, prefix: str = "baked/") -> list:
    """
    使用 bcecmd 列出 BOS 中的场景（仅扫描一级目录）
    
    Args:
        bucket: BOS bucket 名称
        prefix: 前缀路径，默认 "baked/"
    
    Returns:
        场景名称列表
    """
    print(f"正在扫描 BOS: bos://{bucket}/{prefix}")
    
    try:
        # 使用 bcecmd 列出目录
        bos_path = f"bos://{bucket}/{prefix}"
        cmd = ['bcecmd', 'bos', 'ls', bos_path]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode != 0:
            print(f"✗ 列出 BOS 文件失败")
            print(f"  错误: {result.stderr}")
            return []
        
        # 解析输出，提取场景名称（一级目录）
        scenes = set()
        lines = result.stdout.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('Total') or line.startswith('bos://'):
                continue
            
            # bcecmd ls 输出格式: 目录通常以 / 结尾
            # 例如: PRE  Seaside_Town/ 或 baked/Seaside_Town/
            # 提取最后一个路径部分
            if line.endswith('/'):
                # 移除末尾的 /
                path = line.rstrip('/')
                # 只取最后一段作为场景名
                scene_name = path.split('/')[-1]
                # 去除可能的前缀（如 "PRE  "）
                scene_name = scene_name.split()[-1] if scene_name else ''
                if scene_name:
                    scenes.add(scene_name)
        
        return sorted(list(scenes))
        
    except FileNotFoundError:
        print("✗ 未找到 bcecmd 命令")
        print("  请确保已安装 bcecmd 并配置在 PATH 中")
        return []
    except Exception as e:
        print(f"✗ 扫描 BOS 失败: {e}")
        return []


def sync_baked_scenes_to_db(bucket: str = "world-data", prefix: str = "baked/", db_path: str = "database/scene_registry.db"):
    """
    同步 BOS 中的 baked 场景到数据库
    
    Args:
        bucket: BOS bucket 名称
        prefix: BOS 前缀路径，默认 "baked/"
        db_path: 数据库路径
    """
    print("\n" + "=" * 60)
    print("同步 BOS 已烘焙场景到数据库")
    print("=" * 60)
    
    # 连接数据库
    registry = SceneRegistry(db_path)
    
    # 扫描 BOS
    scenes = list_bos_scenes(bucket, prefix)
    
    if not scenes:
        print("\n✗ 未在 BOS 中找到任何场景")
        print("  请检查:")
        print("  1. bcecmd 是否已登录")
        print("  2. BOS bucket 中是否有 baked/ 目录")
        return
    
    print(f"\n找到 {len(scenes)} 个已烘焙场景:")
    for scene in scenes:
        print(f"  - {scene}")
    
    # 更新数据库
    print(f"\n正在更新数据库: {db_path}")
    
    added_count = 0
    updated_count = 0
    
    for scene_name in scenes:
        # 检查场景是否已存在
        existing_scene = registry.get_scene(scene_name)
        
        # BOS 路径（已烘焙）
        bos_baked_path = f"bos://{bucket}/{prefix}{scene_name}/"
        
        if existing_scene is None:
            # 添加新场景
            registry.add_scene(
                scene_name=scene_name,
                bos_baked_path=bos_baked_path,
                content_hash="",  # 从 BOS 同步的场景暂时没有 hash
                bos_exists=True
            )
            print(f"  ✓ 添加场景: {scene_name}")
            added_count += 1
        else:
            # 更新现有场景的 BOS 状态
            registry.add_scene(
                scene_name=scene_name,
                bos_baked_path=bos_baked_path,
                bos_exists=True
            )
            print(f"  ✓ 更新场景: {scene_name} -> BOS 存在")
            updated_count += 1
    
    # 打印统计信息
    print("\n" + "=" * 60)
    print("同步完成")
    print("=" * 60)
    print(f"新增场景: {added_count}")
    print(f"更新场景: {updated_count}")
    print(f"总计: {len(scenes)} 个场景")
    
    # 显示数据库统计
    print("\n数据库统计:")
    stats = registry.get_statistics()
    print(f"  总场景数: {stats['scenes']['total']}")
    print(f"  已下载场景: {stats['scenes']['downloaded']}")
    print(f"  总地图数: {stats['maps']['total']}")
    print(f"  已烘焙 NavMesh: {stats['maps']['navmesh_baked']}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='从 BOS 同步已烘焙场景到数据库',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认配置
  python sync_baked_scenes.py
  
  # 指定 bucket 和数据库路径
  python sync_baked_scenes.py --bucket my-bucket --db scenes/my_registry.db
        """
    )
    
    parser.add_argument('--bucket', '-b',
                       default='world-data',
                       help='BOS bucket 名称 (默认: world-data)')
    parser.add_argument('--db',
                       default='database/scene_registry.db',
                       help='数据库路径 (默认: database/scene_registry.db)')
    
    args = parser.parse_args()
    
    sync_baked_scenes_to_db(bucket=args.bucket, db_path=args.db)


if __name__ == "__main__":
    main()
