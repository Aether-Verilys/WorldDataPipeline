#!/usr/bin/env python3

import argparse
import os
import platform
import sys
from pathlib import Path

# Setup path to ensure imports work
script_dir = Path(__file__).parent
repo_root = script_dir  # Now at project root
ue_pipeline_dir = script_dir / 'ue_pipeline'
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def setup_ue_config_env(system_type: str | None = None):
    """
    根据系统类型设置 UE_CONFIG_PATH 环境变量
    
    Args:
        system_type: 'windows' 或 'linux'，如果为 None 则自动检测，默认为 linux
    """
    config_dir = ue_pipeline_dir / 'config'
    
    # 确定系统类型
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
    
    # 选择配置文件
    if system_type == 'windows':
        config_file = config_dir / 'ue_config.json'
    else:  # linux 或其他系统
        config_file = config_dir / 'linux_ue_config.json'
    
    # 设置环境变量
    if config_file.exists():
        os.environ['UE_CONFIG_PATH'] = str(config_file)
        print(f"[Config] Using {system_type} config: {config_file}")
    else:
        print(f"[Warning] Config file not found: {config_file}")
    
    return str(config_file)


def main():
    parser = argparse.ArgumentParser(
        description='UE Pipeline Unified Entry Point',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Global option for system type
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
    
    # Command: bake_navmesh
    parser_bake = subparsers.add_parser(
        'bake_navmesh',
        help='Bake navigation mesh for scenes'
    )
    parser_bake.add_argument(
        '--manifest',
        type=str,
        required=True,
        help='Path to the job manifest JSON file'
    )
    
    # Command: create_sequence
    parser_create_seq = subparsers.add_parser(
        'create_sequence',
        help='Create level sequences'
    )
    parser_create_seq.add_argument(
        '--manifest',
        type=str,
        required=True,
        help='Path to the job manifest JSON file'
    )
    
    # Command: export
    parser_export = subparsers.add_parser(
        'export',
        help='Export camera/data from sequences'
    )
    parser_export.add_argument(
        '--manifest',
        type=str,
        required=True,
        help='Path to the job manifest JSON file'
    )
    
    # Command: render
    parser_render = subparsers.add_parser(
        'render',
        help='Render sequences (headless mode)'
    )
    parser_render.add_argument(
        '--manifest',
        type=str,
        required=True,
        help='Path to the job manifest JSON file'
    )
    parser_render.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (show what would be done without executing)'
    )
    
    # Command: upload_scenes
    parser_upload = subparsers.add_parser(
        'upload_scenes',
        help='Upload baked scenes to BOS'
    )
    # upload_scenes reads from ue_config.json by default, no manifest needed
    
    args = parser.parse_args()
    
    # Setup UE config based on system type
    setup_ue_config_env(args.system)
    
    # Dispatch to the appropriate module
    if args.command == 'bake_navmesh':
        from ue_pipeline.run_bake_navmesh import main as bake_main
        # Pass manifest path as positional argument
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
    
    elif args.command == 'upload_scenes':
        from ue_pipeline.run_upload_scenes import main as upload_main
        sys.argv = ['run_upload_scenes.py']
        return upload_main()
    
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
