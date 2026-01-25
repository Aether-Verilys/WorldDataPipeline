"""
场景扫描命令行工具
扫描本地或BOS场景，记录场景结构到数据库
"""

import argparse
import sys
from pathlib import Path

# 添加模块路径
script_dir = Path(__file__).parent
repo_root = script_dir.parent.parent  # python/assets -> python -> ue_pipeline (repo_root should be WorldDataPipeline)
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ue_pipeline.python.assets.scene_scanner import SceneStructureScanner


def main():
    parser = argparse.ArgumentParser(
        description='扫描场景目录结构并生成数据库配置',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描本地目录（数据保存到 database/scenes.json 和 scenes.db）
  python scan_scenes.py D:/UE/Scenes
  
  # 扫描BOS目录
  python scan_scenes.py --bos --bucket world-data --prefix raw
  
  # 预览模式（不创建文件）
  python scan_scenes.py D:/UE/Scenes --dry-run
  
  # 使用自定义配置
  python scan_scenes.py D:/UE/Scenes --config config/scan_config.json
  
  # 自定义数据库目录
  python scan_scenes.py D:/UE/Scenes --database-dir D:/MyDatabase
  
  # BOS扫描示例
  python scan_scenes.py --bos --bucket world-data --prefix raw --bos-config config/bos_config.json
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
            parser.error("BOS模式需要 --bucket 和 --prefix 参数")
    else:
        if not args.directory:
            parser.error("本地模式需要提供目录路径")
        
        directory = Path(args.directory)
        if not directory.exists():
            print(f"错误: 目录不存在: {directory}")
            return 1
        
        if not directory.is_dir():
            print(f"错误: 不是一个目录: {directory}")
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
        scenes = scanner.scan_all_scenes(root_dir=Path(args.directory))
    
    return 0 if scenes else 1


if __name__ == '__main__':
    sys.exit(main())
