import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scene_registry import SceneRegistry, calculate_directory_hash
from bos import BosManager


def load_ue_config(config_path: str = "ue_pipeline/config/ue_config.json") -> dict:
    # 尝试多种路径解析方式
    paths_to_try = [
        Path(config_path),  # 相对于当前目录
        Path(__file__).parent.parent.parent / config_path,  # 相对于脚本位置
        Path(config_path).absolute()  # 绝对路径
    ]
    
    for path in paths_to_try:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    print(f"✗ 错误: 配置文件不存在: {config_path}")
    print(f"   尝试的路径: {[str(p) for p in paths_to_try]}")
    sys.exit(1)


def get_bos_credentials(config_path: str = "ue_pipeline/config/bos_config.json"):
    """
    获取BOS凭证
    优先级：
    1. bos_config.json 配置文件
    2. 环境变量 BCE_ACCESS_KEY_ID, BCE_SECRET_ACCESS_KEY
    3. 环境变量 BOS_AK, BOS_SK
    """
    ak = None
    sk = None
    endpoint = "bj.bcebos.com"
    
    # 尝试多种路径解析方式
    config_path_obj = Path(config_path)
    if not config_path_obj.exists():
        # 尝试相对于脚本位置
        config_path_obj = Path(__file__).parent.parent.parent / config_path
    
    # 优先级1: 从配置文件读取
    if config_path_obj.exists():
        try:
            with open(config_path_obj, 'r', encoding='utf-8') as f:
                bos_config = json.load(f)
                ak = bos_config.get('access_key_id')
                sk = bos_config.get('secret_access_key')
                endpoint = bos_config.get('endpoint', 'bj.bcebos.com')
                
                if ak and sk:
                    print(f"✓ 从配置文件读取BOS凭证: {config_path_obj}")
                    return ak, sk, endpoint
        except Exception as e:
            print(f"警告: 读取配置文件失败: {e}")
    
    # 优先级2: 从环境变量读取
    ak = os.environ.get('BCE_ACCESS_KEY_ID') or os.environ.get('BOS_AK')
    sk = os.environ.get('BCE_SECRET_ACCESS_KEY') or os.environ.get('BOS_SK')
    endpoint = os.environ.get('BCE_ENDPOINT', 'bj.bcebos.com')
    
    if ak and sk:
        print(f"✓ 从环境变量读取BOS凭证")
        return ak, sk, endpoint
    
    # 未找到凭证
    print("\n错误: 未找到BOS凭证信息")
    print("\n请使用以下任一方式提供凭证：")
    print("\n方式1 - 配置文件（推荐）:")
    print(f"  编辑配置文件: {config_path}")
    print("  填写 access_key_id 和 secret_access_key")
    print("\n方式2 - 环境变量:")
    print("  Windows PowerShell:")
    print("    $env:BCE_ACCESS_KEY_ID=\"your_access_key\"")
    print("    $env:BCE_SECRET_ACCESS_KEY=\"your_secret_key\"")
    print("\n  Windows CMD:")
    print("    set BCE_ACCESS_KEY_ID=your_access_key")
    print("    set BCE_SECRET_ACCESS_KEY=your_secret_key")
    print("\n  Linux/Mac:")
    print("    export BCE_ACCESS_KEY_ID=your_access_key")
    print("    export BCE_SECRET_ACCESS_KEY=your_secret_key")
    sys.exit(1)


def find_baked_scenes(ue_config: dict) -> list:
    """
    查找所有已烘焙NavMesh的场景
    
    Returns:
        list: [(scene_name, scene_config), ...]
    """
    baked_scenes = []
    
    scenes = ue_config.get('scenes', {})
    for scene_name, scene_config in scenes.items():
        maps = scene_config.get('maps', [])
        
        # 检查是否有任何地图已烘焙NavMesh
        has_baked = False
        for map_info in maps:
            if map_info.get('navmesh_baked', False):
                has_baked = True
                break
        
        if has_baked:
            baked_scenes.append((scene_name, scene_config))
    
    return baked_scenes


def get_scene_local_path(ue_config: dict, scene_name: str) -> Path:
    """
    根据配置获取场景的本地路径
    
    假设场景在 UE 项目的 Content 目录下
    例如: D:/UE_Projects/WorldProject/Content/Seaside_Town
    """
    project_path = ue_config.get('project_path', '')
    if not project_path:
        print(f"✗ 错误: ue_config.json 中未配置 project_path")
        sys.exit(1)
    
    # 从 .uproject 路径获取项目目录
    project_dir = Path(project_path).parent
    content_dir = project_dir / "Content" / scene_name
    
    return content_dir


def upload_scene_to_bos(scene_name: str,
                       scene_config: dict,
                       local_path: Path,
                       bos_manager: BosManager,
                       registry: SceneRegistry,
                       bucket: str = "world-data",
                       dry_run: bool = False) -> bool:
    """上传场景到BOS并更新数据库"""
    
    print("\n" + "=" * 60)
    print(f"场景: {scene_name}")
    print("=" * 60)
    
    # 检查本地路径
    if not local_path.exists():
        print(f"✗ 本地路径不存在: {local_path}")
        print(f"  请确认场景文件在 Content/{scene_name} 目录下")
        return False
    
    print(f"本地路径: {local_path}")
    
    # 统计文件信息
    files = list(local_path.rglob('*'))
    file_list = [f for f in files if f.is_file()]
    file_count = len(file_list)
    total_size = sum(f.stat().st_size for f in file_list)
    
    print(f"文件数量: {file_count}")
    print(f"总大小: {total_size / 1024 / 1024:.2f} MB")
    
    # 计算哈希值
    print(f"计算内容哈希...")
    content_hash = calculate_directory_hash(
        local_path,
        extensions=['.umap', '.uasset', '.uexp', '.ubulk']
    )
    print(f"哈希值: {content_hash[:16]}...")
    
    # BOS路径
    bos_path = f"baked/{scene_name}/"
    bos_full_path = f"bos://{bucket}/{bos_path}"
    
    print(f"BOS路径: {bos_full_path}")
    
    if dry_run:
        print(f"\n[模拟模式] 跳过实际上传")
    else:
        # 上传到BOS
        print(f"\n开始上传...")
        success = bos_manager.upload_scene(
            bucket=bucket,
            local_path=local_path,
            bos_path=bos_path
        )
        
        if not success:
            print(f"✗ 上传失败")
            return False
        
        print(f"✓ 上传完成")
    
    # 更新数据库
    print(f"\n更新数据库...")
    registry.add_scene(
        scene_name=scene_name,
        bos_baked_path=bos_full_path,
        content_hash=content_hash,
        local_path=str(local_path),
        bos_exists=True,
        is_downloaded=True,  # 本地有完整场景文件
        metadata={
            "upload_source": "batch_upload",
            "navmesh_baked": True
        }
    )
    
    registry.update_scene_stats(scene_name, file_count, total_size)
    
    # 更新地图记录
    maps = scene_config.get('maps', [])
    for map_info in maps:
        map_name = map_info.get('name')
        map_path = map_info.get('path', '')
        navmesh_baked = map_info.get('navmesh_baked', False)
        
        if map_name:
            # 添加地图记录
            registry.add_map(
                scene_name=scene_name,
                map_name=map_name,
                map_path=map_path
            )
            
            # 如果已烘焙NavMesh，更新状态
            if navmesh_baked:
                # 使用场景哈希作为NavMesh哈希（简化处理）
                registry.update_navmesh_status(
                    scene_name=scene_name,
                    map_name=map_name,
                    navmesh_hash=content_hash,
                    auto_scale=map_info.get('navmesh_auto_scale', False)
                )
    
    print(f"✓ 数据库已更新（场景 + {len(maps)} 个地图）")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="从配置文件批量上传已烘焙场景到BOS",
        epilog="""
  
环境变量:
  BCE_ACCESS_KEY_ID      - BOS访问密钥ID
  BCE_SECRET_ACCESS_KEY  - BOS访问密钥
  BCE_ENDPOINT          - BOS端点（默认: bj.bcebos.com）
        """
    )
    
    parser.add_argument("--config", default="ue_pipeline/config/ue_config.json",
                       help="UE配置文件路径（默认: ue_pipeline/config/ue_config.json）")
    parser.add_argument("--bos-config", default="ue_pipeline/config/bos_config.json",
                       help="BOS配置文件路径（默认: ue_pipeline/config/bos_config.json）")
    parser.add_argument("--bucket", default="world-data",
                       help="BOS bucket名称（默认: world-data）")
    parser.add_argument("--db", default="database/scene_registry.db",
                       help="数据库路径（默认: database/scene_registry.db）")
    parser.add_argument("--dry-run", action="store_true",
                       help="仅模拟运行，不实际上传")
    parser.add_argument("--scene", help="仅上传指定场景（可选）")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("批量上传已烘焙场景到BOS")
    print("=" * 60)
    
    # 加载配置
    print(f"\n加载配置: {args.config}")
    ue_config = load_ue_config(args.config)
    
    # 查找已烘焙的场景
    baked_scenes = find_baked_scenes(ue_config)
    
    if not baked_scenes:
        print("\n✗ 未找到已烘焙NavMesh的场景")
        print("  请确保 ue_config.json 中的场景有 navmesh_baked=true")
        return 1
    
    print(f"\n找到 {len(baked_scenes)} 个已烘焙场景:")
    for scene_name, _ in baked_scenes:
        print(f"  - {scene_name}")
    
    # 如果指定了场景，过滤
    if args.scene:
        baked_scenes = [(name, cfg) for name, cfg in baked_scenes if name == args.scene]
        if not baked_scenes:
            print(f"\n✗ 场景 '{args.scene}' 未找到或未烘焙NavMesh")
            return 1
        print(f"\n仅上传指定场景: {args.scene}")
    
    # 创建BOS管理器
    if args.dry_run:
        # 模拟模式不需要真实管理器
        bos_manager = None
        print("\n使用模拟模式")
    else:
        # 使用 bcecmd，不需要凭证
        print(f"\n使用 bcecmd 上传到 BOS")
        bos_manager = BosManager()
    
    # 创建注册表
    registry = SceneRegistry(args.db)
    
    # 上传每个场景
    success_count = 0
    fail_count = 0
    
    for scene_name, scene_config in baked_scenes:
        # 获取本地路径
        local_path = get_scene_local_path(ue_config, scene_name)
        
        # 上传场景
        if upload_scene_to_bos(
            scene_name=scene_name,
            scene_config=scene_config,
            local_path=local_path,
            bos_manager=bos_manager,
            registry=registry,
            bucket=args.bucket,
            dry_run=args.dry_run
        ):
            success_count += 1
        else:
            fail_count += 1
    
    # 打印总结
    print("\n" + "=" * 60)
    print("上传完成")
    print("=" * 60)
    print(f"成功: {success_count} 个")
    print(f"失败: {fail_count} 个")
    
    if fail_count > 0:
        print(f"\n⚠ 有 {fail_count} 个场景上传失败，请检查日志")
        return 1
    
    print(f"\n✓ 所有场景已成功上传并更新到数据库")
    return 0


if __name__ == "__main__":
    sys.exit(main())
