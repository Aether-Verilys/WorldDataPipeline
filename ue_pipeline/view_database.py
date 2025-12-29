"""
查看数据库中的场景信息
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'python'))

from scene_registry import SceneRegistry


def main():
    registry = SceneRegistry('database/scene_registry.db')
    scenes = registry.list_scenes()
    
    print('\n数据库中的场景:')
    print('=' * 80)
    
    if not scenes:
        print('数据库为空')
        return
    
    for s in scenes:
        print(f"场景名: {s['scene_name']}")
        print(f"  BOS路径: {s['bos_baked_path']}")
        print(f"  本地路径: {s['local_path'] or '无'}")
        print(f"  BOS存在: {'是' if s['bos_exists'] else '否'}")
        print(f"  已下载: {'是' if s['downloaded_at'] else '否'}")
        print(f"  内容哈希: {s['content_hash'] or '无'}")
        print(f"  文件数: {s['file_count']}")
        size_mb = s['total_size_bytes'] / 1024 / 1024 if s['total_size_bytes'] else 0
        print(f"  大小: {size_mb:.2f} MB")
        print(f"  最后验证: {s['bos_last_verified'] or '从未'}")
        print(f"  下载时间: {s['downloaded_at'] or '从未'}")
        print(f"  最后更新: {s['last_updated']}")
        print()
    
    print('=' * 80)
    print(f"共 {len(scenes)} 个场景")
    
    # 地图信息
    print('\n数据库中的地图:')
    print('=' * 80)
    maps = registry.list_maps()
    
    if not maps:
        print('暂无地图记录')
    else:
        for m in maps:
            print(f"场景: {m['scene_name']} / 地图: {m['map_name']}")
            print(f"  地图路径: {m['map_path']}")
            print(f"  NavMesh已烘焙: {'是' if m['navmesh_baked'] else '否'}")
            if m['navmesh_baked']:
                print(f"  NavMesh哈希: {m['navmesh_hash']}")
                print(f"  烘焙时间: {m['navmesh_baked_at']}")
            print()
        print('=' * 80)
        print(f"共 {len(maps)} 个地图")


if __name__ == '__main__':
    main()
