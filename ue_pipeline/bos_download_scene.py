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
            self.source_bucket = config.get('target_bucket', 'world-data')  # 使用之前的target作为这里的source
            self.source_prefix = config.get('target_prefix', 'raw').strip('/')
            self.local_content_path = Path(config.get('local_content_path', '')) if config.get('local_content_path') else None
        else:
            self.source_bucket = source_bucket or 'world-data'
            self.source_prefix = (source_prefix or 'raw').strip('/')
            self.local_content_path = Path(local_content_path) if local_content_path else None
        
        # 如果提供了UE配置文件，从中提取Content路径
        if ue_config_path and not self.local_content_path:
            ue_config = self.load_config(ue_config_path)
            project_path = ue_config.get('project_path')
            if project_path:
                # 从.uproject路径推导Content目录
                project_dir = Path(project_path).parent
                content_dir = project_dir / 'Content'
                if content_dir.exists():
                    self.local_content_path = content_dir
                    print(f"✓ 从UE配置中获取Content路径: {content_dir}")
        
        # 如果还是没有路径，尝试使用默认的ue_config.json
        if not self.local_content_path:
            default_ue_config = Path(__file__).parent / 'config' / 'ue_config.json'
            if default_ue_config.exists():
                ue_config = self.load_config(str(default_ue_config))
                project_path = ue_config.get('project_path')
                if project_path:
                    project_dir = Path(project_path).parent
                    content_dir = project_dir / 'Content'
                    if content_dir.exists():
                        self.local_content_path = content_dir
                        print(f"✓ 从默认UE配置中获取Content路径: {content_dir}")
    
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
        列出BOS中可用的场景
        
        Returns:
            场景名称列表
        """
        bos_path = f"bos:/{self.source_bucket}/{self.source_prefix}/"
        
        try:
            cmd = ['bcecmd', 'bos', 'ls', bos_path, '-a']
            print(f"执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                print(f"✗ 列出场景失败: {result.stderr}")
                return []
            
            # 解析输出
            scenes = []
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
                    scenes.append(scene_name)
            
            return scenes
            
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
    
    def download_scene(self, scene_name: str, target_path: Optional[Path] = None, 
                      dry_run: bool = False) -> bool:
        """
        下载场景到本地Content目录
        
        Args:
            scene_name: 场景名称
            target_path: 目标Content路径，如果不指定则使用配置的路径
            dry_run: 是否只预览
            
        Returns:
            是否成功
        """
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
        
        # 构建BOS源路径，尝试带PRE前缀和不带前缀两种情况
        source_path_no_prefix = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/Content/"
        source_path_with_prefix = f"bos:/{self.source_bucket}/{self.source_prefix}/PRE  {scene_name}/Content/"
        
        # 先检查哪个路径存在
        source_path = None
        for test_path in [source_path_no_prefix, source_path_with_prefix]:
            check_cmd = ['bcecmd', 'bos', 'ls', test_path]
            check_result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            if check_result.returncode == 0:
                source_path = test_path
                break
        
        if not source_path:
            print(f"✗ 未找到场景: {scene_name}")
            print(f"  尝试过的路径:")
            print(f"    - {source_path_no_prefix}")
            print(f"    - {source_path_with_prefix}")
            return False
        
        print(f"\n{'='*70}")
        print(f"下载场景: {scene_name}")
        print(f"{'='*70}")
        print(f"源路径: {source_path}")
        print(f"目标路径: {content_path}")
        
        if dry_run:
            print(f"[预览模式] 将执行下载")
            return True
        
        try:
            # 获取详细文件列表
            check_cmd = ['bcecmd', 'bos', 'ls', source_path, '-r']
            check_result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            # 统计文件数量
            lines = [l.strip() for l in check_result.stdout.strip().split('\n') 
                    if l.strip() and not l.startswith('TOTAL')]
            file_count = len(lines)
            
            if file_count == 0:
                print(f"✗ 源路径为空")
                return False
            
            print(f"✓ 源路径包含 {file_count} 个对象")
            
            # 使用 bcecmd 下载
            # 注意：bcecmd下载时需要指定本地路径
            target_str = str(content_path.absolute()).replace('\\', '/')
            cmd = ['bcecmd', 'bos', 'cp', source_path, target_str, '-r', '-y']
            
            print(f"\n执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                print(f"✗ 下载失败: {result.stderr}")
                return False
            
            print(f"✓ 下载成功")
            if result.stdout:
                print(result.stdout)
            
            return True
            
        except Exception as e:
            print(f"✗ 下载失败: {e}")
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
    
    # 如果既没有--list也没有--scene也没有--search，显示帮助
    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
