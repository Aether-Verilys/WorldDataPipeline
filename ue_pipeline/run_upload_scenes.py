"""
场景上传工具 - 上传指定场景到BOS

使用方法:
    # 交互式输入场景名（推荐）
    python run_upload_scenes.py
    或 python app.py upload_scene
    
    # 直接指定场景名
    python run_upload_scenes.py --scene LevelPrototyping
    
    # 模拟运行
    python run_upload_scenes.py --scene LevelPrototyping --dry-run

配置:
    - 上传配置在 ue_pipeline/config/bos.json 的 operations.upload 中
    - 场景自动从 project_path/Content/{scene_name} 查找
    - 上传到 bos://{target_bucket}/{target_prefix}/{scene_name}

要求:
    1. 需要先安装并登录 bcecmd (pip install bcecmd && bcecmd login)
    2. 场景文件在 UE 项目的 Content/{scene_name} 目录下
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Add repo root to path
script_dir = Path(__file__).parent
repo_root = script_dir.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def list_available_scenes(project_path: str = None, show_details: bool = False) -> list:
    """
    列出项目中可用的场景
    
    Args:
        project_path: UE项目路径（可选）
        show_details: 是否显示详细信息（文件数量、大小等）
    
    Returns:
        场景名称列表
    """
    # 确定项目路径
    if project_path:
        p = Path(project_path)
        if p.suffix == '.uproject':
            p = p.parent
        content_dir = p / 'Content'
    else:
        # 从 ue_config.json 读取
        ue_config_path = os.environ.get('UE_CONFIG_PATH', 'ue_pipeline/config/ue_config.json')
        try:
            config_file = Path(ue_config_path)
            if not config_file.exists():
                config_file = repo_root / ue_config_path
            
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    ue_config = json.load(f)
                    config_project = ue_config.get('project_path', '')
                    
                    if config_project == 'default':
                        config_project = str(repo_root / 'ue_template' / 'project' / 'WorldData.uproject')
                    
                    if config_project:
                        p = Path(config_project)
                        if p.suffix == '.uproject':
                            p = p.parent
                        content_dir = p / 'Content'
                    else:
                        content_dir = repo_root / 'ue_template' / 'project' / 'Content'
            else:
                content_dir = repo_root / 'ue_template' / 'project' / 'Content'
        except Exception:
            content_dir = repo_root / 'ue_template' / 'project' / 'Content'
    
    if not content_dir.exists():
        print(f"✗ Content 目录不存在: {content_dir}")
        return []
    
    # 扫描 Content 目录下的文件夹
    scenes = []
    excluded_dirs = {'__ExternalActors__', '__ExternalObjects__', 'Collections', 'Developers'}
    
    for item in content_dir.iterdir():
        if item.is_dir() and item.name not in excluded_dirs:
            # 检查是否包含 .umap 文件（地图文件）
            has_maps = any(item.rglob('*.umap'))
            if has_maps:
                scene_info = {'name': item.name, 'path': item}
                
                if show_details:
                    # 统计文件信息
                    files = list(item.rglob('*'))
                    file_list = [f for f in files if f.is_file()]
                    scene_info['file_count'] = len(file_list)
                    scene_info['total_size'] = sum(f.stat().st_size for f in file_list)
                
                scenes.append(scene_info)
    
    return scenes


def check_scene_in_database(scene_name: str, db_path: str = "database/scene_registry.db") -> dict:
    """
    检查场景是否在数据库中
    
    Args:
        scene_name: 场景名称
        db_path: 数据库路径
    
    Returns:
        数据库中的场景信息字典，如果不存在则返回 None
    """
    try:
        # 尝试导入数据库模块
        db_file = repo_root / db_path
        if not db_file.exists():
            return None
        
        import sqlite3
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        
        # 查询场景信息
        cursor.execute("""
            SELECT scene_name, bos_baked_path, bos_exists, is_downloaded, 
                   file_count, total_size_bytes, last_updated
            FROM scenes
            WHERE scene_name = ?
        """, (scene_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'scene_name': row[0],
                'bos_baked_path': row[1],
                'bos_exists': bool(row[2]),
                'is_downloaded': bool(row[3]),
                'file_count': row[4],
                'total_size_bytes': row[5],
                'last_updated': row[6]
            }
        return None
    except Exception:
        return None


def run_bcecmd_upload(local_path: Path, bucket: str, prefix: str, scene_name: str, 
                     dry_run: bool = False) -> bool:
    """
    使用 bcecmd 上传整个场景目录到BOS
    
    Args:
        local_path: 本地场景路径 (如 F:/UE_Project/Content/Game/Base)
        bucket: BOS bucket名称 (如 world-data)
        prefix: BOS路径前缀 (如 renders/baked)
        scene_name: 场景名称 (如 Base)
        dry_run: 仅显示命令，不执行
    
    Returns:
        是否成功
    """
    # 构建BOS路径: bos://bucket/prefix/scene_name
    bos_path = f"bos://{bucket}/{prefix.strip('/')}/{scene_name}"
    
    # 构建 bcecmd 命令
    # bcecmd bos cp <source> <target> --recursive -y
    cmd = [
        'bcecmd',
        'bos',
        'cp',
        str(local_path),
        bos_path,
        '--recursive',
        '-y'  # 自动确认
    ]
    
    print(f"\n{'[模拟模式] ' if dry_run else ''}执行命令:")
    print(f"  {' '.join(cmd)}")
    print(f"\n将上传:")
    print(f"  本地路径: {local_path}")
    print(f"  BOS路径:  {bos_path}")
    
    if dry_run:
        print(f"\n[模拟模式] 跳过实际上传")
        return True
    
    try:
        # 执行命令
        print(f"\n开始上传...")
        result = subprocess.run(
            cmd,
            capture_output=False,  # 直接显示输出
            text=True
        )
        
        if result.returncode == 0:
            print(f"\n✓ 上传成功!")
            return True
        else:
            print(f"\n✗ 上传失败，退出码: {result.returncode}")
            return False
            
    except FileNotFoundError:
        print(f"\n✗ 错误: 未找到 bcecmd 命令")
        print(f"  请确保已安装 bcecmd 并配置在 PATH 中")
        print(f"\n安装方法:")
        print(f"  1. 下载: pip install bcecmd")
        print(f"  2. 登录: bcecmd login")
        return False
    except Exception as e:
        print(f"\n✗ 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_scene_path(scene_name: str, project_path: str = None) -> Path:
    """
    查找场景的本地路径
    
    优先级:
    1. 如果提供了 project_path，在 project_path/Content/{scene_name} 查找
    2. 在环境变量 UE_PROJECT_PATH 指定的路径查找
    3. 在 ue_config.json 中的 project_path 查找
    4. 在当前目录的 ue_template/project 查找
    
    Args:
        scene_name: 场景名称
        project_path: UE项目路径（可选）
    
    Returns:
        场景路径
    """
    search_paths = []
    
    # 优先级1: 命令行指定的项目路径
    if project_path:
        p = Path(project_path)
        if p.suffix == '.uproject':
            p = p.parent
        search_paths.append(p / 'Content' / scene_name)
    
    # 优先级2: 环境变量
    env_project = os.environ.get('UE_PROJECT_PATH')
    if env_project:
        p = Path(env_project)
        if p.suffix == '.uproject':
            p = p.parent
        search_paths.append(p / 'Content' / scene_name)
    
    # 优先级3: 从 ue_config.json 读取
    ue_config_path = os.environ.get('UE_CONFIG_PATH', 'ue_pipeline/config/ue_config.json')
    try:
        config_file = Path(ue_config_path)
        if not config_file.exists():
            config_file = repo_root / ue_config_path
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                ue_config = json.load(f)
                config_project = ue_config.get('project_path', '')
                
                # 处理 "default" 值 - 使用 ue_template 项目
                if config_project == 'default':
                    config_project = str(repo_root / 'ue_template' / 'project' / 'WorldData.uproject')
                
                if config_project:
                    p = Path(config_project)
                    if p.suffix == '.uproject':
                        p = p.parent
                    search_paths.append(p / 'Content' / scene_name)
    except Exception:
        pass
    
    # 优先级4: 默认模板路径
    default_project = repo_root / 'ue_template' / 'project'
    search_paths.append(default_project / 'Content' / scene_name)
    
    # 查找第一个存在的路径
    for path in search_paths:
        if path.exists():
            return path
    
    # 未找到，返回第一个路径（让后续检查报错）
    return search_paths[0] if search_paths else Path(f"Content/{scene_name}")


def load_bos_config(config_path: str = None) -> dict:
    """
    从 bos.json 加载配置
    
    Args:
        config_path: 配置文件路径，默认为 ue_pipeline/config/bos.json
    
    Returns:
        配置字典
    """
    if config_path is None:
        config_path = 'ue_pipeline/config/bos.json'
    
    # 尝试多种路径解析方式
    paths_to_try = [
        Path(config_path),  # 相对于当前目录
        repo_root / config_path,  # 相对于仓库根目录
        script_dir / 'config' / 'bos.json',  # 相对于脚本的config目录
        Path(config_path).absolute()  # 绝对路径
    ]
    
    for path in paths_to_try:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"警告: 读取配置文件失败 {path}: {e}")
                continue
    
    print(f"✗ 错误: 配置文件不存在: {config_path}")
    print(f"   尝试的路径: {[str(p) for p in paths_to_try]}")
    return None


def upload_scene_with_config(scene_name: str = None, dry_run: bool = False, 
                             local_path_override: str = None) -> int:
    """
    使用 bos.json 配置上传场景（供 app.py 调用）
    
    Args:
        scene_name: 场景名称（如果为None则交互式输入）
        dry_run: 是否模拟运行
        local_path_override: 覆盖本地路径
    
    Returns:
        退出码 (0=成功, 1=失败)
    """
    print("\n" + "=" * 60)
    print("场景上传工具")
    print("=" * 60)
    
    # 加载 bos.json 配置
    bos_config = load_bos_config()
    if bos_config is None:
        return 1
    
    # 获取 upload 配置
    upload_config = bos_config.get('operations', {}).get('upload', {})
    
    if not upload_config.get('enabled', True):
        print(f"\n✗ 错误: upload 操作在 bos.json 中被禁用")
        print(f"   请在 bos.json 中设置 operations.upload.enabled = true")
        return 1
    
    # 读取配置参数
    bucket = upload_config.get('target_bucket', 'world-data')
    prefix = upload_config.get('target_prefix', 'baked')
    
    # 如果没有指定场景名，交互式输入
    if scene_name is None:
        print(f"\n配置信息:")
        print(f"  BOS Bucket: {bucket}")
        print(f"  BOS Prefix: {prefix}")
        
        # 列出可用场景
        print(f"\n正在扫描可用场景...")
        scenes = list_available_scenes(show_details=True)
        
        if scenes:
            print(f"\n找到 {len(scenes)} 个可用场景:")
            print(f"\n{'序号':<6} {'场景名称':<30} {'文件数':<10} {'大小':<15} {'数据库':<10}")
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
        else:
            print("\n未找到任何场景")
        
        print(f"\n请输入要上传的场景名称（例如: LevelPrototyping）")
        print(f"提示: 场景应该在 Content/{{场景名}} 目录下")
        
        try:
            scene_name = input("\n场景名称: ").strip()
            if not scene_name:
                print("\n✗ 错误: 场景名称不能为空")
                return 1
        except (KeyboardInterrupt, EOFError):
            print("\n\n已取消上传")
            return 1
    
    # 合并 dry_run 配置
    config_dry_run = upload_config.get('dry_run', False)
    final_dry_run = dry_run or config_dry_run
    
    print(f"\n上传配置:")
    print(f"  场景名称: {scene_name}")
    print(f"  BOS Bucket: {bucket}")
    print(f"  BOS Prefix: {prefix}")
    if final_dry_run:
        print(f"  模式: 模拟运行 (dry-run)")
    
    # 确定本地路径
    if local_path_override:
        local_path = Path(local_path_override)
    else:
        # 自动查找场景路径（不传递 project_path，让函数自动从 ue_config.json 读取）
        local_path = find_scene_path(scene_name)
    
    # 检查本地路径
    if not local_path.exists():
        print(f"\n✗ 错误: 场景路径不存在")
        print(f"  路径: {local_path}")
        print(f"\n请确认:")
        print(f"  1. 场景名称是否正确: {scene_name}")
        print(f"  2. 场景文件在 Content/{scene_name} 目录下")
        print(f"  3. ue_config.json 中的 project_path 设置正确")
        print(f"  4. 或使用 --local-path 直接指定场景路径")
        return 1
    
    # 统计文件
    files = list(local_path.rglob('*'))
    file_list = [f for f in files if f.is_file()]
    total_size = sum(f.stat().st_size for f in file_list)
    
    print(f"\n场景信息:")
    print(f"  本地路径: {local_path}")
    print(f"  文件数: {len(file_list)}")
    print(f"  总大小: {total_size / 1024 / 1024:.2f} MB")
    
    # 上传到BOS
    success = run_bcecmd_upload(
        local_path=local_path,
        bucket=bucket,
        prefix=prefix,
        scene_name=scene_name,
        dry_run=final_dry_run
    )
    
    if success:
        print(f"\n✓ 完成!")
        return 0
    else:
        print(f"\n✗ 上传失败")
        return 1


def main():
    """命令行入口（支持直接调用）"""
    parser = argparse.ArgumentParser(
        description="上传指定场景到BOS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出可用场景
  python run_upload_scenes.py --list
  
  # 交互式输入场景名（推荐）
  python run_upload_scenes.py
  
  # 直接指定场景名
  python run_upload_scenes.py --scene LevelPrototyping
  
  # 模拟运行
  python run_upload_scenes.py --scene LevelPrototyping --dry-run
  
  # 覆盖本地路径
  python run_upload_scenes.py --scene MyScene --local-path "F:/UE/Content/Game/MyScene"

配置:
  上传配置在 ue_pipeline/config/bos.json 的 operations.upload 中
  - target_bucket: BOS bucket名称
  - target_prefix: BOS路径前缀
  - dry_run: 是否模拟运行

环境变量:
  UE_PROJECT_PATH  - UE项目路径（.uproject 文件或项目目录）
  UE_CONFIG_PATH   - UE配置文件路径（默认: ue_pipeline/config/ue_config.json）
        """
    )
    
    parser.add_argument('--list', '-l', action='store_true',
                       help='列出所有可用场景')
    parser.add_argument('--scene',
                       help='场景名称（如 LevelPrototyping）。不指定则交互式输入')
    parser.add_argument('--local-path',
                       help='直接指定本地场景路径（覆盖自动查找）')
    parser.add_argument('--dry-run', action='store_true',
                       help='仅显示命令，不实际上传')
    
    args = parser.parse_args()
    
    # 如果是列出场景
    if args.list:
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
    
    # 使用配置文件方式
    return upload_scene_with_config(
        scene_name=args.scene,
        dry_run=args.dry_run,
        local_path_override=args.local_path
    )


if __name__ == '__main__':
    sys.exit(main())
