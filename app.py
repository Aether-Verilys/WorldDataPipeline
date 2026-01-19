import argparse
import json
import os
import platform
import sys
from pathlib import Path

script_dir = Path(__file__).parent
repo_root = script_dir  
ue_pipeline_dir = script_dir / 'ue_pipeline'
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ue_pipeline.python.bos.bos_client import initialize_bos
import sys as _sys
_sys.stderr.write("BOS client imported successfully\n")
_sys.stderr.flush()


def setup_bos_client():
    """
    设置全局BOS客户端
    在应用启动时调用一次，后续所有模块共享同一个客户端实例
    注意：部分命令（如 upload_scene）使用 bcecmd，不需要 BOS SDK
    """
    try:
        # 尝试从配置文件初始化
        bos_config_path = 'config/bos_config.json'
        full_path = repo_root / bos_config_path
        
        if full_path.exists():
            initialize_bos(config_file=str(full_path))
        else:
            # 如果没有配置文件，尝试从环境变量初始化
            initialize_bos()
    except ImportError as e:
        # BOS SDK未安装或有问题，某些功能（如 upload_scene）仍可工作
        _sys.stderr.write(f"警告: BOS SDK 初始化失败: {e}\n")
        _sys.stderr.write("提示: 使用 bcecmd 的命令（如 upload_scene）仍可正常工作\n")
        _sys.stderr.flush()
    except Exception as e:
        _sys.stderr.write(f"警告: BOS 客户端初始化失败: {e}\n")
        _sys.stderr.flush()


def setup_ue_config_env(system_type: str | None = None):
    """
    根据系统类型设置 UE_CONFIG_PATH 环境变量
    
    Args:
        system_type: 'windows' 或 'linux'，如果为 None 则自动检测，默认为 linux
    """
    config_dir = ue_pipeline_dir / 'config'
    
    if system_type is None:
        # 从环境变量读取，如果没有则自动检测
        system_type = os.environ.get('UE_SYSTEM_TYPE', '').lower()
        if not system_type:
            # 自动检测，默认为 linux
            detected_system = platform.system().lower()
            if detected_system == 'windows':
                system_type = 'windows'
            else:
                system_type = 'linux'  # 默认 linux
    
    if system_type == 'windows':
        config_file = config_dir / 'ue_config.json'
    else: 
        config_file = config_dir / 'linux_ue_config.json'
    
    # 设置环境变量
    if config_file.exists():
        os.environ['UE_CONFIG_PATH'] = str(config_file)
        print(f"[Config] Using {system_type} config: {config_file}")
    else:
        print(f"[Warning] Config file not found: {config_file}")
    
    return str(config_file)


def main():
    setup_bos_client()
    
    parser = argparse.ArgumentParser(
        description='UE Pipeline Unified Entry Point',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--system',
        type=str,
        choices=['windows', 'linux'],
        default=None,
        help='System type (default: auto-detect, fallback to linux)'
    )
    
    subparsers = parser.add_subparsers(
        dest='command',
        help='Available commands',
        required=True
    )
    
    parser_bake = subparsers.add_parser(
        'bake_navmesh',
        help='Bake navigation mesh for scenes'
    )
    parser_bake.add_argument(
        '--manifest',
        type=str,
        default='config/job_config.json',
        help='Path to the job manifest JSON file (default: config/job_config.json)'
    )
    
    parser_create_seq = subparsers.add_parser(
        'create_sequence',
        help='Create level sequences'
    )
    parser_create_seq.add_argument(
        '--manifest',
        type=str,
        default='config/job_config.json',
        help='Path to the job manifest JSON file (default: config/job_config.json)'
    )
    
    parser_export = subparsers.add_parser(
        'export',
        help='Export camera/data from sequences'
    )
    parser_export.add_argument(
        '--manifest',
        type=str,
        default='config/job_config.json',
        help='Path to the job manifest JSON file (default: config/job_config.json)'
    )
    
    parser_render = subparsers.add_parser(
        'render',
        help='Render sequences (headless mode)'
    )
    parser_render.add_argument(
        '--manifest',
        type=str,
        default='config/job_config.json',
        help='Path to the job manifest JSON file (default: config/job_config.json)'
    )
    parser_render.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (show what would be done without executing)'
    )
    
    parser_upload = subparsers.add_parser(
        'upload_scene',
        help='Upload a scene to BOS (interactive or specify --scene)'
    )
    parser_upload.add_argument(
        '--list', '-l',
        action='store_true',
        help='List all available scenes in the project'
    )
    parser_upload.add_argument(
        '--scene',
        type=str,
        help='Scene name to upload (e.g., LevelPrototyping). If not provided, will prompt for input'
    )
    parser_upload.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (show what would be done without executing)'
    )
    parser_upload.add_argument(
        '--local-path',
        type=str,
        help='Override local scene path (default: from project_path/Content/{scene})'
    )

    parser_download = subparsers.add_parser(
        'download_scene',
        help='Download scene from BOS to local Content folder'
    )
    parser_download.add_argument(
        '--scene',
        type=str,
        required=False,
        help='Scene name to download (if not provided, will list available scenes)'
    )
    parser_download.add_argument(
        '--list',
        action='store_true',
        help='List all available scenes in BOS'
    )
    parser_download.add_argument(
        '--search',
        type=str,
        help='Search for scenes containing this string'
    )
    
    parser_copy = subparsers.add_parser(
        'copy_scene',
        help='Copy scene from source BOS bucket to target bucket'
    )
    parser_copy.add_argument(
        '--scene',
        type=str,
        nargs='+',
        help='Scene name(s) to copy (if not provided, will list available scenes)'
    )
    parser_copy.add_argument(
        '--list',
        action='store_true',
        help='List all available scenes in source bucket'
    )
    parser_copy.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (show what would be done without executing)'
    )
    
    args = parser.parse_args()
    
    setup_ue_config_env(args.system)
    
    # Dispatch to the appropriate module
    if args.command == 'bake_navmesh':
        from ue_pipeline.run_bake_navmesh import main as bake_main
        sys.argv = ['run_bake_navmesh.py', args.manifest]
        return bake_main()
    
    elif args.command == 'create_sequence':
        from ue_pipeline.run_create_sequence_job import main as create_seq_main
        sys.argv = ['run_create_sequence_job.py', args.manifest]
        return create_seq_main()
    
    elif args.command == 'export':
        from ue_pipeline.run_export_job import main as export_main
        sys.argv = ['run_export_job.py', args.manifest]
        return export_main()
    
    elif args.command == 'render':
        from ue_pipeline.run_render_job_headless import main as render_main
        if args.dry_run:
            sys.argv = ['run_render_job_headless.py', args.manifest, '--dry-run']
        else:
            sys.argv = ['run_render_job_headless.py', args.manifest]
        return render_main()
    
    elif args.command == 'upload_scene':
        # 如果是列出场景，直接调用 main 函数
        if args.list:
            from ue_pipeline.upload_scene import list_available_scenes, check_scene_in_database
            
            print("\n" + "=" * 80)
            print("可用场景列表")
            print("=" * 80)
            
            scenes = list_available_scenes(show_details=True)
            
            if scenes:
                print(f"\n找到 {len(scenes)} 个场景:\n")
                print(f"{'序号':<6} {'场景名称':<30} {'文件数':<10} {'大小':<15} {'数据库':<10}")
                print("-" * 80)
                
                for i, scene in enumerate(scenes, 1):
                    size_mb = scene['total_size'] / 1024 / 1024
                    
                    # 检查数据库
                    db_info = check_scene_in_database(scene['name'])
                    if db_info:
                        if db_info['bos_exists']:
                            db_status = "已上传"
                        else:
                            db_status = "未上传"
                    else:
                        db_status = "-"
                    
                    print(f"{i:<6} {scene['name']:<30} {scene['file_count']:<10} {size_mb:>10.2f} MB   {db_status:<10}")
                
                print(f"\n提示: 使用 --scene <场景名> 上传指定场景")
            else:
                print("\n未找到任何场景")
            
            return 0
        else:
            from ue_pipeline.upload_scene import upload_scene_with_config
            return upload_scene_with_config(
                scene_name=args.scene,
                dry_run=args.dry_run,
                local_path_override=args.local_path
            )
    
    elif args.command == 'download_scene':
        from ue_pipeline.python.bos.download_scene import BosSceneDownloader
        from pathlib import Path
        
        # 加载 bos.json 配置
        bos_config_path = Path(__file__).parent / 'ue_pipeline' / 'config' / 'bos.json'
        if bos_config_path.exists():
            with open(bos_config_path, 'r', encoding='utf-8') as f:
                bos_config = json.load(f)
                download_config = bos_config.get('operations', {}).get('download', {})
        else:
            download_config = {}
        
        # 初始化下载器，传入配置
        downloader = BosSceneDownloader(
            source_bucket=download_config.get('source_bucket'),
            source_prefix=download_config.get('source_prefix'),
            ue_config_path=download_config.get('ue_config_path')
        )
        
        if args.list:
            # 列出所有可用场景
            print("\n" + "=" * 80)
            print("BOS 可用场景列表")
            print("=" * 80)
            
            print(f"\n配置信息:")
            print(f"  BOS Bucket: {downloader.source_bucket}")
            print(f"  BOS Prefix: {downloader.source_prefix}")
            
            print(f"\n正在扫描 BOS 中的场景...")
            scenes = downloader.list_available_scenes()
            
            if scenes:
                print(f"\n找到 {len(scenes)} 个场景:\n")
                for i, scene in enumerate(scenes, 1):
                    print(f"  {i}. {scene}")
                
                print(f"\n提示: 使用 --scene <场景名> 下载指定场景")
            else:
                print("\n未找到任何场景")
            return 0
        
        elif args.search:
            # 搜索场景
            scenes = downloader.list_available_scenes()
            matching = [s for s in scenes if args.search.lower() in s.lower()]
            if matching:
                print(f"\n找到 {len(matching)} 个匹配场景:")
                for i, scene in enumerate(matching, 1):
                    print(f"  {i}. {scene}")
            else:
                print(f"未找到包含 '{args.search}' 的场景")
            return 0
        
        elif args.scene:
            # 下载指定场景
            success = downloader.download_scene(args.scene)
            return 0 if success else 1
        
        else:
            # 交互式模式
            success = downloader.download_scene(interactive=True)
            return 0 if success else 1
    
    elif args.command == 'copy_scene':
        from ue_pipeline.python.bos.copy_scenes import BosSceneCopier
        
        copier = BosSceneCopier()
        
        if args.list:
            # 列出所有可用场景
            scenes = copier.list_scenes()
            if scenes:
                print(f"\n找到 {len(scenes)} 个源场景:")
                for i, scene in enumerate(scenes, 1):
                    print(f"  {i}. {scene}")
            else:
                print("未找到任何场景")
            return 0
        
        elif args.scene:
            # 复制指定场景
            failed_scenes = []
            for scene_name in args.scene:
                print(f"\n正在复制场景: {scene_name}")
                success = copier.process_scene(scene_name, dry_run=args.dry_run)
                if not success:
                    failed_scenes.append(scene_name)
            
            if failed_scenes:
                print(f"\n✗ {len(failed_scenes)} 个场景复制失败:")
                for scene in failed_scenes:
                    print(f"  - {scene}")
                return 1
            else:
                print(f"\n✓ 所有场景复制成功")
                return 0
        
        else:
            # 无参数，显示帮助
            print("用法: python app.py copy_scene [--scene SCENE_NAME [...] | --list] [--dry-run]")
            print("\n示例:")
            print("  python app.py copy_scene --list")
            print("  python app.py copy_scene --scene Seaside_Town")
            print("  python app.py copy_scene --scene Scene1 Scene2 Scene3")
            print("  python app.py copy_scene --scene Seaside_Town --dry-run")
            return 0
    
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
