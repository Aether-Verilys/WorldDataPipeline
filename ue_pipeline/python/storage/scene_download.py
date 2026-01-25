#!/usr/bin/env python
"""
BOS场景下载工具
从 bos://world-data/raw/场景名/Content/ 下载到本地UE工程的Content目录
"""

import subprocess
import sys
import json
import argparse
from pathlib import Path
from typing import Optional


class BosSceneDownloader:
    """BOS场景下载器"""
    
    def __init__(self, config_path: Optional[str] = None,
                 ue_config_path: Optional[str] = None,
                 source_bucket: Optional[str] = None,
                 source_prefix: Optional[str] = None,
                 local_content_path: Optional[str] = None):
        """
        初始化BOS场景下载器
        
        Args:
            config_path: BOS配置文件路径
            ue_config_path: UE配置文件路径（用于获取本地Content路径）
            source_bucket: 源bucket名称
            source_prefix: 源路径前缀（raw）
            local_content_path: 本地Content目录路径
        """
        # 如果提供了配置文件，从配置文件加载
        if config_path:
            config = self.load_config(config_path)
            self.source_bucket = config.get('source_bucket', 'world-data')
            self.source_prefix = config.get('source_prefix', 'raw').strip('/')
            self.local_content_path = Path(config.get('local_content_path', '')) if config.get('local_content_path') else None
            self.configured_scenes = config.get('scenes', [])  # 从配置读取场景列表
            
            # 如果配置文件中指定了 ue_config_path，使用它来获取 Content 路径
            if not self.local_content_path and config.get('ue_config_path'):
                ue_config_path = config.get('ue_config_path')
                # 相对路径转绝对路径
                if not Path(ue_config_path).is_absolute():
                    config_dir = Path(config_path).parent.parent  # 从 ue_pipeline/config 向上到工作区根目录
                    ue_config_path = str(config_dir / ue_config_path)
                # 不再在这里设置 ue_config_path 参数，而是在下面统一处理
                if not ue_config_path:  # 避免覆盖外部传入的参数
                    ue_config_path = ue_config_path
        else:
            self.source_bucket = source_bucket or 'world-data'
            self.source_prefix = (source_prefix or 'raw').strip('/')
            self.local_content_path = Path(local_content_path) if local_content_path else None
            self.configured_scenes = []
        
        # 如果提供了UE配置文件，从中提取Content路径
        if ue_config_path and not self.local_content_path:
            ue_config = self.load_config(ue_config_path)
            project_path = ue_config.get('project_path')
            
            # Handle "default" value - use ue_template project
            if project_path == "default":
                # 从当前文件向上找到工作区根目录
                script_dir = Path(__file__).resolve().parent  # .../ue_pipeline/python/bos
                workspace_root = script_dir.parent.parent.parent  # D:\WorldDataPipeline
                project_path = str(workspace_root / "ue_template" / "project" / "WorldData.uproject")
                print(f"✓ 使用默认项目路径: {project_path}")
            
            if project_path:
                # 从.uproject路径推导Content目录
                project_dir = Path(project_path).parent
                content_dir = project_dir / 'Content'
                if content_dir.exists():
                    self.local_content_path = content_dir
                    print(f"✓ 从UE配置中获取Content路径: {content_dir}")
        
        # 如果还是没有路径，尝试使用默认的ue_config.json
        if not self.local_content_path and not ue_config_path:
            # 从当前文件路径向上找到 ue_pipeline/config/ue_config.json
            script_dir = Path(__file__).resolve().parent  # .../ue_pipeline/python/bos
            default_ue_config = script_dir.parent.parent / 'config' / 'ue_config.json'  # .../ue_pipeline/config/ue_config.json
            
            if default_ue_config.exists():
                ue_config = self.load_config(str(default_ue_config))
                project_path = ue_config.get('project_path')
                
                # Handle "default" value - use ue_template project
                if project_path == "default":
                    # 从 ue_pipeline 向上找到工作区根目录，然后找 ue_template
                    workspace_root = script_dir.parent.parent.parent  # D:\WorldDataPipeline
                    project_path = str(workspace_root / "ue_template" / "project" / "WorldData.uproject")
                    print(f"✓ 使用默认项目路径: {project_path}")
                
                if project_path:
                    project_dir = Path(project_path).parent
                    content_dir = project_dir / 'Content'
                    if content_dir.exists():
                        self.local_content_path = content_dir
                        print(f"✓ 从默认UE配置中获取Content路径: {content_dir}")
                    else:
                        print(f"✗ Content目录不存在: {content_dir}")
                else:
                    print(f"✗ UE配置中未找到project_path")
            else:
                print(f"✗ 未找到默认UE配置: {default_ue_config}")
    
    def load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"✗ 加载配置文件失败: {e}")
            return {}
    
    def list_available_scenes(self) -> list:
        """
        列出BOS中可用的场景（只扫描一级目录，不递归）
        
        Returns:
            场景名称列表 ['scene1', 'scene2', ...]
        """
        bos_path = f"bos:/{self.source_bucket}/{self.source_prefix}/"
        
        try:
            cmd = ['bcecmd', 'bos', 'ls', bos_path, '-a']
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=10  # 快速超时
            )
            
            if result.returncode != 0:
                print(f"✗ 列出场景失败: {result.stderr}")
                return []
            
            # 解析输出，获取场景名称（只扫描一级目录）
            scene_names = []
            lines = result.stdout.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('TOTAL'):
                    continue
                
                if line.endswith('/'):
                    scene_name = line.rstrip('/')
                    # 去掉 "PRE  " 前缀（5个字符）
                    if scene_name.startswith('PRE  '):
                        scene_name = scene_name[5:]
                    scene_names.append(scene_name)
            
            return scene_names
            
        except subprocess.TimeoutExpired:
            print("✗ 列出场景超时")
            return []
        except FileNotFoundError:
            print("✗ 未找到 bcecmd 命令")
            return []
        except Exception as e:
            print(f"✗ 列出场景失败: {e}")
            return []
    
    def search_scene(self, scene_name: str) -> bool:
        """
        搜索场景，如果不存在则显示首字母相同的场景
        
        Args:
            scene_name: 场景名称
            
        Returns:
            场景是否存在
        """
        # 获取所有场景
        all_scenes = self.list_available_scenes()
        
        if not all_scenes:
            print("✗ 无法获取场景列表")
            return False
        
        # 检查场景是否存在（不区分大小写）
        scene_exists = any(s.lower() == scene_name.lower() for s in all_scenes)
        
        if scene_exists:
            # 找到精确匹配
            matched_scene = next(s for s in all_scenes if s.lower() == scene_name.lower())
            print(f"\n✓ 找到场景: {matched_scene}")
            return True
        else:
            # 没找到，显示首字母相同的场景
            print(f"\n✗ 未找到场景: {scene_name}")
            
            # 获取首字母
            first_letter = scene_name[0].upper() if scene_name else ''
            
            if first_letter:
                # 筛选首字母相同的场景
                similar_scenes = [s for s in all_scenes if s[0].upper() == first_letter]
                
                if similar_scenes:
                    print(f"\n以 '{first_letter}' 开头的场景:")
                    for i, scene in enumerate(similar_scenes, 1):
                        print(f"  {i}. {scene}")
                else:
                    print(f"\n没有以 '{first_letter}' 开头的场景")
            
            return False
    
    def download_scene(self, scene_name: str = None, target_path: Optional[Path] = None, 
                      dry_run: bool = False, interactive: bool = False) -> bool:
        """
        下载场景到本地Content目录
        
        Args:
            scene_name: 场景名称（如果为None且interactive=True，则交互式选择）
            target_path: 目标Content路径，如果不指定则使用配置的路径
            dry_run: 是否只预览
            interactive: 是否交互式模式
            
        Returns:
            是否成功
        """
        # 如果是交互式模式且没有指定场景名
        if interactive and scene_name is None:
            print("\n" + "=" * 80)
            print("BOS 场景下载工具")
            print("=" * 80)
            
            print(f"\n配置信息:")
            print(f"  BOS Bucket: {self.source_bucket}")
            print(f"  BOS Prefix: {self.source_prefix}")
            print(f"  本地目录: {self.local_content_path or '未配置'}")
            
            # 列出可用场景（只列出目录名，不统计文件）
            print(f"\n正在扫描 BOS 中的场景...")
            scenes = self.list_available_scenes()
            
            if scenes:
                print(f"\n找到 {len(scenes)} 个可用场景:\n")
                for i, scene_name in enumerate(scenes, 1):
                    print(f"  {i}. {scene_name}")
            else:
                print("\n未找到任何场景")
                return False
            
            print(f"\n请输入要下载的场景名称")
            
            try:
                scene_name = input("\n场景名称: ").strip()
                if not scene_name:
                    print("\n✗ 错误: 场景名称不能为空")
                    return False
            except (KeyboardInterrupt, EOFError):
                print("\n\n已取消下载")
                return False
        
        if not scene_name:
            print("✗ 未指定场景名称")
            return False
        
        # 确定目标路径
        if target_path:
            content_path = Path(target_path)
        elif self.local_content_path:
            content_path = self.local_content_path
        else:
            print("✗ 未指定本地Content目录路径")
            return False
        
        # 确保目标目录存在
        if not content_path.exists():
            print(f"✗ 本地Content目录不存在: {content_path}")
            return False
        
        # 构建BOS源路径：下载整个场景文件夹
        # bos:/world-data/raw/Hong_Kong_Street/ 下载到 Content/Hong_Kong_Street/
        source_path = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/"
        
        # 目标路径应该是 Content 目录（bcecmd 会自动创建场景文件夹）
        target_scene_path = content_path / scene_name
        
        print(f"\n{'='*70}")
        print(f"下载场景: {scene_name}")
        print(f"{'='*70}")
        print(f"源路径: {source_path}")
        print(f"目标路径: {target_scene_path}")
        
        if dry_run:
            print(f"[预览模式] 将执行下载")
            return True
        
        try:
            # 检查源路径是否存在
            check_cmd = ['bcecmd', 'bos', 'ls', source_path]
            check_result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if check_result.returncode != 0:
                print(f"✗ 源路径不存在: {source_path}")
                return False
            
            # 获取详细文件列表统计
            check_cmd = ['bcecmd', 'bos', 'ls', source_path, '-r']
            check_result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=30
            )
            
            # 统计文件数量
            lines = [l.strip() for l in check_result.stdout.strip().split('\n') 
                    if l.strip() and not l.startswith('TOTAL')]
            file_count = len(lines)
            
            if file_count == 0:
                print(f"✗ 源路径为空")
                return False
            
            print(f"✓ 源路径包含 {file_count} 个对象")
            
            # 使用 bcecmd 下载整个场景文件夹（显示进度）
            # bcecmd bos cp bos:/bucket/prefix/scene/ local/Content/scene/ -r -y
            target_str = str(target_scene_path.absolute()).replace('\\', '/')
            cmd = ['bcecmd', 'bos', 'cp', source_path, target_str, '-r', '-y']
            
            print(f"\n执行命令: {' '.join(cmd)}")
            print(f"\n开始下载...\n")
            
            # 不捕获输出，让进度条直接显示在终端
            result = subprocess.run(cmd)
            
            if result.returncode != 0:
                print(f"\n✗ 下载失败")
                return False
            
            print(f"\n✓ 下载成功")
            
            return True
            
        except KeyboardInterrupt:
            print(f"\n\n✗ 用户取消下载")
            return False
        except Exception as e:
            print(f"\n✗ 下载失败: {e}")
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='BOS场景下载工具 - 从world-data/raw下载场景到本地Content目录',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出可用场景
  python bos_download_scene.py --list
  
  # 搜索场景（如果不存在则显示首字母相同的场景）
  python bos_download_scene.py --search "Modular_Sci-Fi_Hospital"
  
  # 下载指定场景（自动使用ue_config.json中的Content目录）
  python bos_download_scene.py --scene "3D_Scanned_Canyon"
  
  # 下载到指定Content目录
  python bos_download_scene.py --scene "3D_Scanned_Canyon" --target "D:/MyProject/Content"
  
  # 使用自定义BOS配置文件
  python bos_download_scene.py -c config/bos_copy_config.json --scene "3D_Scanned_Canyon"
  
  # 预览模式
  python bos_download_scene.py --scene "3D_Scanned_Canyon" --dry-run
        """
    )
    
    parser.add_argument(
        '-c', '--config',
        type=str,
        help='配置文件路径'
    )
    
    parser.add_argument(
        '--scene',
        type=str,
        help='要下载的场景名称'
    )
    
    parser.add_argument(
        '--target',
        type=str,
        help='本地Content目录路径'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='列出BOS中可用的场景'
    )
    
    parser.add_argument(
        '--search',
        type=str,
        help='搜索场景，如果不存在则显示首字母相同的场景'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式，不实际下载'
    )
    
    parser.add_argument(
        '--source-bucket',
        help='源bucket名称（默认: world-data）'
    )
    
    parser.add_argument(
        '--source-prefix',
        help='源路径前缀（默认: raw）'
    )
    
    args = parser.parse_args()
    
    # 创建下载器
    # 计算默认UE配置路径（相对于脚本所在目录）
    default_ue_config = Path(__file__).parent / 'config' / 'ue_config.json'
    
    downloader = BosSceneDownloader(
        config_path=args.config,
        ue_config_path=str(default_ue_config) if default_ue_config.exists() and not args.config else None,
        source_bucket=args.source_bucket,
        source_prefix=args.source_prefix,
        local_content_path=args.target
    )
    
    # 列出场景
    if args.list:
        print("列出可用场景...")
        scenes = downloader.list_available_scenes()
        
        if not scenes:
            print("✗ 未找到任何场景")
            return 1
        
        print(f"\n✓ 找到 {len(scenes)} 个场景:")
        for i, scene in enumerate(scenes, 1):
            print(f"  {i}. {scene}")
        
        return 0
    
    # 搜索场景
    if args.search:
        exists = downloader.search_scene(args.search)
        return 0 if exists else 1
    
    # 下载场景
    if args.scene:
        success = downloader.download_scene(
            scene_name=args.scene,
            target_path=Path(args.target) if args.target else None,
            dry_run=args.dry_run
        )
        
        return 0 if success else 1
    
    # 如果配置文件中指定了场景列表，批量下载
    if downloader.configured_scenes:
        print(f"\n从配置文件读取到 {len(downloader.configured_scenes)} 个场景")
        
        failed_scenes = []
        for i, scene in enumerate(downloader.configured_scenes, 1):
            print(f"\n[{i}/{len(downloader.configured_scenes)}] 处理场景: {scene}")
            success = downloader.download_scene(
                scene_name=scene,
                target_path=Path(args.target) if args.target else None,
                dry_run=args.dry_run
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
    
    # 如果既没有--list也没有--scene也没有--search，显示帮助
    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
