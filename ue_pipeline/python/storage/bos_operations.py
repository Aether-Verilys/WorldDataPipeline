#!/usr/bin/env python
"""
BOS统一操作管理器
根据配置文件中的 active_operation 执行对应的BOS操作：
- copy: 从源bucket复制场景到目标bucket
- upload: 上传本地已烘焙场景到BOS
- download: 从BOS下载场景到本地
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def load_config(config_path: str) -> dict:
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"✗ 加载配置文件失败: {e}")
        sys.exit(1)


def run_copy_operation(config: dict, dry_run: bool = False) -> int:
    """执行复制操作"""
    from bos_copy_scenes import BosSceneCopier
    
    op_config = config['operations']['copy']
    
    print("\n" + "="*70)
    print("BOS场景复制操作")
    print("="*70)
    print(f"源: bos:/{op_config['source_bucket']}/{op_config['source_prefix']}/")
    print(f"目标: bos:/{op_config['target_bucket']}/{op_config['target_prefix']}/")
    print(f"场景: {op_config.get('scenes', []) or '所有场景'}")
    print(f"模式: {'预览模式' if dry_run or op_config.get('dry_run') else '实际复制'}")
    print("="*70 + "\n")
    
    # 创建copier
    copier = BosSceneCopier(
        source_bucket=op_config['source_bucket'],
        source_prefix=op_config['source_prefix'],
        target_bucket=op_config['target_bucket'],
        target_prefix=op_config['target_prefix']
    )
    
    # 设置配置属性
    copier.target_content_folder = op_config.get('target_content_folder', 'Content')
    copier.fallback_markers = op_config.get('fallback_markers', ['Blueprints', 'Maps', 'Map', 'Textures'])
    copier.exclude_patterns = op_config.get('exclude_patterns', ['manifest', '*.url', '*.txt', '*.md'])
    copier.prefer_duplicated_scene_name = op_config.get('prefer_duplicated_scene_name', True)
    copier.skip_existing = op_config.get('skip_existing', True)
    
    # 获取场景列表
    scenes = op_config.get('scenes', [])
    
    if not scenes:
        # 如果没有指定场景，列出所有场景
        print("未指定场景，列出所有可用场景...")
        scenes = copier.list_scenes()
        
        if not scenes:
            print("✗ 未找到任何场景")
            return 1
        
        print(f"\n找到 {len(scenes)} 个场景:")
        for i, scene in enumerate(scenes, 1):
            print(f"  {i}. {scene}")
        
        return 0
    
    # 复制指定场景
    is_dry_run = dry_run or op_config.get('dry_run', False)
    failed_scenes = []
    
    for i, scene in enumerate(scenes, 1):
        print(f"\n[{i}/{len(scenes)}] 处理场景: {scene}")
        success = copier.copy_scene(scene, dry_run=is_dry_run)
        
        if not success:
            failed_scenes.append(scene)
    
    if failed_scenes:
        print(f"\n✗ {len(failed_scenes)} 个场景复制失败:")
        for scene in failed_scenes:
            print(f"  - {scene}")
        return 1
    else:
        print(f"\n✓ 所有场景复制成功")
        return 0


def run_upload_operation(config: dict, dry_run: bool = False) -> int:
    """执行上传操作"""
    from python.bos.upload_scenes import main as upload_main
    
    op_config = config['operations']['upload']
    
    print("\n" + "="*70)
    print("BOS场景上传操作")
    print("="*70)
    print(f"目标: bos:/{op_config['target_bucket']}/{op_config['target_prefix']}/")
    print(f"模式: {'预览模式' if dry_run or op_config.get('dry_run') else '实际上传'}")
    print("="*70 + "\n")
    
    # 准备命令行参数
    import os
    
    # 设置环境变量
    if 'ue_config_path' in op_config:
        os.environ['UE_CONFIG_PATH'] = op_config['ue_config_path']
    
    # 设置BOS凭证环境变量
    if 'credentials' in config:
        creds = config['credentials']
        os.environ['BCE_ACCESS_KEY_ID'] = creds.get('access_key_id', '')
        os.environ['BCE_SECRET_ACCESS_KEY'] = creds.get('secret_access_key', '')
        os.environ['BCE_ENDPOINT'] = creds.get('endpoint', 'bj.bcebos.com')
    
    # 构建命令行参数
    old_argv = sys.argv.copy()
    sys.argv = ['upload_scenes.py']
    
    if dry_run or op_config.get('dry_run'):
        sys.argv.append('--dry-run')
    
    if op_config.get('force_upload'):
        sys.argv.append('--force')
    
    if op_config.get('upload_only_baked'):
        sys.argv.append('--only-baked')
    
    try:
        result = upload_main()
        sys.argv = old_argv
        return result
    except Exception as e:
        print(f"✗ 上传失败: {e}")
        sys.argv = old_argv
        return 1


def run_download_operation(config: dict, dry_run: bool = False) -> int:
    """执行下载操作"""
    from bos_download_scene import BosSceneDownloader
    
    op_config = config['operations']['download']
    
    print("\n" + "="*70)
    print("BOS场景下载操作")
    print("="*70)
    print(f"源: bos:/{op_config['source_bucket']}/{op_config['source_prefix']}/")
    print(f"场景: {op_config.get('scenes', []) or '所有场景'}")
    print(f"模式: {'预览模式' if dry_run or op_config.get('dry_run') else '实际下载'}")
    print("="*70 + "\n")
    
    # 创建downloader
    downloader = BosSceneDownloader(
        source_bucket=op_config['source_bucket'],
        source_prefix=op_config['source_prefix'],
        local_content_path=op_config.get('local_content_path') or None
    )
    
    # 如果提供了UE配置路径，加载Content路径
    if op_config.get('ue_config_path') and not downloader.local_content_path:
        ue_config = load_config(op_config['ue_config_path'])
        project_path = ue_config.get('project_path')
        
        if project_path == "default":
            script_dir = Path(__file__).parent.parent
            project_path = str(script_dir / "ue_template" / "project" / "WorldData.uproject")
        
        if project_path:
            project_dir = Path(project_path).parent
            content_dir = project_dir / 'Content'
            if content_dir.exists():
                downloader.local_content_path = content_dir
                print(f"✓ 从UE配置中获取Content路径: {content_dir}")
    
    # 获取场景列表
    scenes = op_config.get('scenes', [])
    
    if not scenes:
        # 如果没有指定场景，列出所有场景
        print("未指定场景，列出所有可用场景...")
        scenes = downloader.list_available_scenes()
        
        if not scenes:
            print("✗ 未找到任何场景")
            return 1
        
        print(f"\n找到 {len(scenes)} 个场景:")
        for i, scene in enumerate(scenes, 1):
            print(f"  {i}. {scene}")
        
        return 0
    
    # 下载指定场景
    is_dry_run = dry_run or op_config.get('dry_run', False)
    failed_scenes = []
    
    for i, scene in enumerate(scenes, 1):
        print(f"\n[{i}/{len(scenes)}] 处理场景: {scene}")
        success = downloader.download_scene(
            scene_name=scene,
            dry_run=is_dry_run
        )
        
        if not success:
            failed_scenes.append(scene)
    
    if failed_scenes:
        print(f"\n✗ {len(failed_scenes)} 个场景下载失败:")
        for scene in failed_scenes:
            print(f"  - {scene}")
        return 1
    else:
        print(f"\n✓ 所有场景下载成功")
        return 0


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='BOS统一操作管理器 - 根据配置文件执行copy/upload/download操作',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
配置文件结构:
  {
    "active_operation": "copy|upload|download",
    "operations": {
      "copy": {...},
      "upload": {...},
      "download": {...}
    }
  }

示例:
  # 使用默认配置文件执行active_operation指定的操作
  python bos_manager.py
  
  # 使用自定义配置文件
  python bos_manager.py -c config/my_bos_config.json
  
  # 覆盖配置文件中的active_operation
  python bos_manager.py --operation download
  
  # 预览模式
  python bos_manager.py --dry-run
  
  # 列出可用操作
  python bos_manager.py --list-operations
        """
    )
    
    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config/bos_operations.json',
        help='配置文件路径（默认: config/bos_operations.json）'
    )
    
    parser.add_argument(
        '--operation',
        type=str,
        choices=['copy', 'upload', 'download'],
        help='要执行的操作（覆盖配置文件中的active_operation）'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式，不实际执行操作'
    )
    
    parser.add_argument(
        '--list-operations',
        action='store_true',
        help='列出配置文件中的所有操作'
    )
    
    args = parser.parse_args()
    
    # 加载配置文件
    config_path = Path(args.config)
    if not config_path.exists():
        # 尝试相对于脚本目录
        config_path = Path(__file__).parent / args.config
    
    if not config_path.exists():
        print(f"✗ 配置文件不存在: {args.config}")
        return 1
    
    config = load_config(str(config_path))
    
    # 列出操作
    if args.list_operations:
        print("\n可用操作:")
        for op_name, op_config in config.get('operations', {}).items():
            status = "✓" if op_config.get('enabled', True) else "✗"
            desc = op_config.get('description', '')
            print(f"  {status} {op_name}: {desc}")
        
        print(f"\n当前active_operation: {config.get('active_operation', '未设置')}")
        return 0
    
    # 确定要执行的操作
    operation = args.operation or config.get('active_operation')
    
    if not operation:
        print("✗ 未指定操作")
        print("  请在配置文件中设置 active_operation 或使用 --operation 参数")
        return 1
    
    if operation not in config.get('operations', {}):
        print(f"✗ 操作不存在: {operation}")
        print(f"  可用操作: {list(config.get('operations', {}).keys())}")
        return 1
    
    # 检查操作是否启用
    op_config = config['operations'][operation]
    if not op_config.get('enabled', True):
        print(f"✗ 操作已禁用: {operation}")
        print(f"  请在配置文件中将 operations.{operation}.enabled 设置为 true")
        return 1
    
    # 执行操作
    print(f"\n执行操作: {operation}")
    print(f"配置文件: {config_path}")
    
    if operation == 'copy':
        return run_copy_operation(config, args.dry_run)
    elif operation == 'upload':
        return run_upload_operation(config, args.dry_run)
    elif operation == 'download':
        return run_download_operation(config, args.dry_run)
    else:
        print(f"✗ 未知操作: {operation}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
