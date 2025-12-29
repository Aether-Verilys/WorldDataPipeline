"""
BOS管理器使用示例
演示如何使用BosManager进行场景上传、下载和状态同步
"""

from pathlib import Path
import sys

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ue_pipeline.python.scene_registry import SceneRegistry
from python.bos import BosManager, MockBosManager


def example_upload_scene():
    """示例1: 上传场景到BOS并注册到数据库"""
    print("=" * 60)
    print("示例1: 上传场景并注册")
    print("=" * 60)
    
    # 使用模拟模式
    bos_manager = MockBosManager()
    registry = SceneRegistry("scenes/scene_registry.db")
    
    scene_name = "TestScene_001"
    local_path = Path("D:/UE_Cache/TestScene_001")
    bos_path = "baked/TestScene_001/"
    
    print(f"\n处理场景: {scene_name}")
    
    # 上传到BOS
    print(f"  1) 上传到BOS...")
    success = bos_manager.upload_scene(
        bucket="world-data",
        local_path=local_path,
        bos_path=bos_path
    )
    
    if success:
        print(f"     ✓ 上传成功")
        
        # 注册到数据库
        print(f"  2) 注册到数据库...")
        registry.add_scene(
            scene_name=scene_name,
            bos_baked_path=f"bos://world-data/{bos_path}",
            content_hash="test_hash_123",
            local_path=str(local_path),
            bos_exists=True,
            metadata={"upload_date": "2025-12-29"}
        )
        print(f"     ✓ 注册成功")
    
    print()


def example_download_scene():
    """示例2: 从BOS下载场景"""
    print("=" * 60)
    print("示例2: 检查状态并下载")
    print("=" * 60)
    
    registry = SceneRegistry("scenes/scene_registry.db")
    bos_manager = MockBosManager(existing_scenes=["Seaside_Town"])
    
    scene_name = "Seaside_Town"
    scene = registry.get_scene(scene_name)
    
    if scene and scene['bos_exists']:
        print(f"\n场景 '{scene_name}' 在BOS中存在")
        print(f"  BOS路径: {scene['bos_baked_path']}")
        
        # 下载场景
        print(f"\n  开始下载...")
        local_path = Path(f"D:/UE_Cache/{scene_name}")
        
        success = bos_manager.download_scene(
            bucket="world-data",
            scene_path=f"baked/{scene_name}/",
            local_path=local_path
        )
        
        if success:
            print(f"  ✓ 下载完成: {local_path}")
    
    print()


def example_sync_status():
    """示例3: 同步BOS状态"""
    print("=" * 60)
    print("示例3: 同步BOS状态")
    print("=" * 60)
    
    registry = SceneRegistry("scenes/scene_registry.db")
    
    # 模拟：只有部分场景存在
    existing_scenes = ["Seaside_Town", "ModularScifiStation"]
    bos_manager = MockBosManager(existing_scenes=existing_scenes)
    
    print(f"\n开始同步...")
    stats = bos_manager.sync_scenes_status(
        registry=registry,
        bucket="world-data",
        prefix="baked/"
    )
    
    print(f"\n同步结果:")
    print(f"  验证存在: {stats['verified']} 个")
    print(f"  发现丢失: {stats['missing']} 个")
    print(f"  状态更新: {stats['updated']} 个")
    
    # 列出丢失的场景
    missing = registry.list_missing_scenes()
    if missing:
        print(f"\n⚠ 丢失的场景:")
        for scene in missing:
            print(f"  - {scene['scene_name']}")
    
    print()


def example_real_usage():
    """真实环境使用示例代码"""
    print("=" * 60)
    print("真实环境使用")
    print("=" * 60)
    
    print("""
# 1. 创建真实BOS管理器
from python.bos import BosManager
from scene_registry import SceneRegistry

bos_manager = BosManager(
    access_key_id="your_access_key_id",
    secret_access_key="your_secret_access_key",
    endpoint="bj.bcebos.com"
)
registry = SceneRegistry()

# 2. 上传场景
bos_manager.upload_scene(
    bucket="world-data",
    local_path=Path("D:/UE_Cache/Seaside_Town"),
    bos_path="baked/Seaside_Town/"
)

# 注册到数据库
registry.add_scene(
    scene_name="Seaside_Town",
    bos_baked_path="bos://world-data/baked/Seaside_Town/",
    bos_exists=True
)

# 3. 下载场景
bos_manager.download_scene(
    bucket="world-data",
    scene_path="baked/Seaside_Town/",
    local_path=Path("D:/UE_Cache/Seaside_Town")
)

# 4. 同步状态
stats = bos_manager.sync_scenes_status(
    registry=registry,
    bucket="world-data"
)

# 或使用命令行工具
# python ue_pipeline/sync_bos_status.py --ak xxx --sk xxx
""")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("BOS管理器使用示例")
    print("=" * 60 + "\n")
    
    example_upload_scene()
    example_download_scene()
    example_sync_status()
    example_real_usage()
    
    print("=" * 60)
    print("完成！")
    print("=" * 60)
