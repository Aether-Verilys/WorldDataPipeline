#!/usr/bin/env python
"""
BOS场景复制工具
从 bos://baidu-download-new/UE4场景/ 复制场景到 bos://world-data/raw/
按照copy脚本规则处理路径
"""

import subprocess
import sys
import json
import re
from pathlib import Path
from typing import List, Tuple, Optional


class BosSceneCopier:
    """BOS场景复制器"""
    
    def __init__(self, config_path: Optional[str] = None, 
                 source_bucket: Optional[str] = None, 
                 source_prefix: Optional[str] = None,
                 target_bucket: Optional[str] = None,
                 target_prefix: Optional[str] = None):
        """
        初始化BOS场景复制器
        
        Args:
            config_path: 配置文件路径（如果提供，将覆盖其他参数）
            source_bucket: 源bucket名称
            source_prefix: 源路径前缀
            target_bucket: 目标bucket名称  
            target_prefix: 目标路径前缀
        """
        # 如果提供了配置文件，从配置文件加载
        if config_path:
            config = self.load_config(config_path)
            self.source_bucket = config.get('source_bucket', 'baidu-download-new')
            self.source_prefix = config.get('source_prefix', 'UE4场景').strip('/')
            self.target_bucket = config.get('target_bucket', 'world-data')
            self.target_prefix = config.get('target_prefix', 'raw').strip('/')
            self.target_content_folder = config.get('target_content_folder', 'Content')
            self.fallback_markers = config.get('fallback_markers', ['Blueprints', 'Maps', 'Map', 'Textures'])
            self.exclude_patterns = config.get('exclude_patterns', ['manifest', '*.url', '*.txt', '*.md'])
            self.prefer_duplicated_scene_name = config.get('prefer_duplicated_scene_name', True)
            self.skip_existing = config.get('skip_existing', True)
        else:
            # 使用命令行参数或默认值
            self.source_bucket = source_bucket or 'baidu-download-new'
            self.source_prefix = (source_prefix or 'UE4场景').strip('/')
            self.target_bucket = target_bucket or 'world-data'
            self.target_prefix = (target_prefix or 'raw').strip('/')
            self.target_content_folder = 'Content'
            self.fallback_markers = ['Blueprints', 'Maps', 'Map', 'Textures']
            self.exclude_patterns = ['manifest', '*.url', '*.txt', '*.md']
            self.prefer_duplicated_scene_name = True
            self.skip_existing = True
    
    def load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] 加载配置文件失败: {e}")
            print(f"  使用默认配置")
            return {}
    
    def should_exclude_content_dir(self, dir_name: str) -> bool:
        """检查Content子目录是否应该被排除
        
        Args:
            dir_name: 目录名称
            
        Returns:
            是否应该排除
        """
        import fnmatch
        
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(dir_name, pattern) or fnmatch.fnmatch(dir_name.lower(), pattern.lower()):
                return True
        
        # 排除文件类型（包含扩展名）
        if '.' in dir_name and not dir_name.startswith('.'):
            # 如果看起来像文件而不是目录
            ext = dir_name.rsplit('.', 1)[-1].lower()
            # UE资产目录通常不包含这些扩展名
            exclude_exts = ['url', 'txt', 'md', 'pdf', 'doc', 'docx', 'zip', 'rar', '7z']
            if ext in exclude_exts:
                return True
        
        return False
        
    def list_scenes(self) -> List[str]:
        """
        列出源BOS中的所有场景
        
        Returns:
            场景名称列表
        """
        bos_path = f"bos:/{self.source_bucket}/{self.source_prefix}/"
        
        try:
            # 使用 -a 参数尝试列出所有对象（bcecmd默认只列出1000个）
            cmd = ['bcecmd', 'bos', 'ls', bos_path, '-a']
            print(f"执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                print(f"[ERROR] 列出场景失败: {result.stderr}")
                return []
            
            # 解析输出，提取场景目录名称
            scenes = []
            lines = result.stdout.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('TOTAL'):
                    continue
                
                # bcecmd ls 输出格式通常是：目录以 / 结尾
                # 示例输出: Nordic Harbour/
                if line.endswith('/'):
                    scene_name = line.rstrip('/')
                    # 去除 "PRE  " 前缀（PRE加两个空格）
                    if scene_name.startswith('PRE  '):
                        scene_name = scene_name[5:]  # 去掉前5个字符 "PRE  "
                    scenes.append(scene_name)
            
            return scenes
            
        except FileNotFoundError:
            print("[ERROR] 未找到 bcecmd 命令")
            print("  请确保已安装 bcecmd 并配置在 PATH 中")
            return []
        except Exception as e:
            print(f"[ERROR] 列出场景失败: {e}")
            return []
    
    def parse_scene_structure(self, scene_name: str) -> List[Tuple[str, str]]:
        """
        解析场景内部结构，找到需要复制的Content目录
        
        Args:
            scene_name: 场景名称，如 "Nordic Harbour"
            
        Returns:
            [(源路径, 目标路径), ...] 元组列表
        """
        # 构建场景路径
        scene_path = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/"
        
        try:
            cmd = ['bcecmd', 'bos', 'ls', scene_path, '-r']
            print(f"\n扫描场景结构: {scene_name}")
            print(f"执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                print(f"[ERROR] 扫描失败: {result.stderr}")
                return []
            
            # 策略1: 查找Content目录
            # 策略2: 如果没有Content，查找Blueprints/Maps/Map/Textures，复制其上级目录
            
            copy_mappings = []
            lines = result.stdout.strip().split('\n')
            
            # 找到所有 /Content/ 后的一级子目录
            content_pattern = re.compile(r'/Content/([^/]+)/?')
            # 备选标记目录（从配置读取，不区分大小写）
            markers_str = '|'.join(re.escape(m) for m in self.fallback_markers)
            fallback_patterns = re.compile(f'/({markers_str})/', re.IGNORECASE)
            
            found_content_dirs = {}  # {content_subdir: full_source_path}
            found_fallback_dirs = {}  # {parent_dir: full_source_path}
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('TOTAL'):
                    continue
                
                # bcecmd ls -r 输出格式：日期 时间 大小 存储类型 路径
                # 示例: 2025-01-03 15:35:57  5523151  STANDARD  Content/CanyonScans/Environment/Cliffs_Sandy/
                # 需要提取最后的路径部分
                parts = line.split()
                if len(parts) >= 4:
                    # 最后一部分是路径，前面可能是日期、时间、大小、存储类型
                    # 查找路径部分（通常包含 / 或以已知目录开头）
                    path_part = parts[-1]
                    
                    # 如果路径部分不包含斜杠且不是目录标记，尝试重新组合
                    # （处理路径中包含空格的情况）
                    if '/' not in path_part and len(parts) > 4:
                        # 可能路径中包含空格，从STANDARD后面开始重新组合
                        for i, part in enumerate(parts):
                            if part in ['STANDARD', 'ARCHIVE', 'COLD', 'STANDARD_IA']:
                                path_part = ' '.join(parts[i+1:])
                                break
                    
                    rel_path = path_part
                else:
                    # 如果格式不符合预期，使用整行
                    rel_path = line
                
                # 移除可能的前缀（bcecmd输出可能包含完整路径）
                if f"{self.source_prefix}/{scene_name}/" in rel_path:
                    # 提取相对路径
                    rel_path = rel_path.split(f"{self.source_prefix}/{scene_name}/", 1)[-1]
                
                # 确保路径以 / 开头，便于统一匹配
                if not rel_path.startswith('/'):
                    rel_path = '/' + rel_path
                
                # 策略1: 查找 /Content/ 位置
                if '/Content/' in rel_path:
                    # 匹配 Content 后的第一级目录
                    match = content_pattern.search(rel_path)
                    if match:
                        content_subdir = match.group(1)
                        
                        # 过滤掉非UE资产目录
                        if self.should_exclude_content_dir(content_subdir):
                            continue
                        
                        # 只记录每个子目录的第一次出现（最短路径）
                        if content_subdir not in found_content_dirs:
                            # 从bcecmd ls -r的输出中，我们知道了文件的完整相对路径
                            # 例如：/Venice/3DScanne0871f9868a47V1/data/Content/KSS_Software/xxx.uasset
                            # 我们需要找到实际BOS中Content子目录的位置
                            
                            # 策略：从文件路径直接提取Content子目录的完整路径
                            search_pattern = f"/Content/{content_subdir}/"
                            
                            # 在当前行的相对路径中提取完整路径
                            # rel_path = /Venice/3DScanne0871f9868a47V1/data/Content/KSS_Software/xxx
                            # 提取到Content/子目录为止的路径
                            content_index = rel_path.find(search_pattern)
                            if content_index >= 0:
                                # 提取Content之前的完整路径（去掉开头的/）
                                full_path_before_content = rel_path[1:content_index].strip('/')
                                
                                # 构建完整源路径
                                if full_path_before_content:
                                    full_source_path = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/{full_path_before_content}/Content/{content_subdir}/"
                                else:
                                    full_source_path = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/Content/{content_subdir}/"
                                
                                print(f"    [调试] 从文件路径提取: {full_source_path}")
                                
                                # 直接使用提取的路径，因为我们从bcecmd ls -r的输出中已经确认文件存在
                                # 不需要再次验证（bcecmd ls可能不递归显示所有内容）
                                found_content_dirs[content_subdir] = full_source_path
                                print(f"    [调试] 已记录Content子目录: {content_subdir}")
                            else:
                                print(f"    [警告] 无法从路径中提取Content位置: {rel_path}")
                
                # 策略2: 查找备选目录（仅在没有Content时使用）
                else:
                    match = fallback_patterns.search(rel_path)
                    if match:
                        # 找到标记目录的位置
                        marker_dir = match.group(1)
                        marker_index = rel_path.find(f'/{marker_dir}/')
                        
                        # 提取上级目录（marker目录的父目录）
                        path_before_marker = rel_path[:marker_index]
                        
                        # 找到最后一个 / 之后的部分作为父目录名
                        if '/' in path_before_marker:
                            parent_dir = path_before_marker.rsplit('/', 1)[-1]
                            full_path_to_parent = path_before_marker
                        else:
                            # 如果没有上级，使用整个路径
                            parent_dir = path_before_marker if path_before_marker else scene_name
                            full_path_to_parent = path_before_marker
                        
                        if parent_dir:
                            # 只保留最外层（路径最短）的父目录
                            if parent_dir not in found_fallback_dirs:
                                # 构建完整源路径
                                if full_path_to_parent:
                                    full_source_path = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/{full_path_to_parent}/"
                                else:
                                    full_source_path = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/"
                                found_fallback_dirs[parent_dir] = (full_source_path, marker_dir)
                            else:
                                # 如果已存在，比较路径长度，保留较短的（更外层的）
                                existing_path, existing_marker = found_fallback_dirs[parent_dir]
                                if full_path_to_parent:
                                    new_path = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/{full_path_to_parent}/"
                                else:
                                    new_path = f"bos:/{self.source_bucket}/{self.source_prefix}/{scene_name}/"
                                
                                # 路径越短，层级越外
                                if len(new_path) < len(existing_path):
                                    found_fallback_dirs[parent_dir] = (new_path, marker_dir)
            
            # 优先使用Content目录
            if found_content_dirs:
                print(f"[OK] 找到 {len(found_content_dirs)} 个Content子目录: {', '.join(sorted(found_content_dirs.keys()))}")
                
                # 使用场景名作为目标目录名（空格替换为下划线）
                safe_scene_name = scene_name.replace(' ', '_')
                
                # 找到Content目录的父路径，从父级开始复制
                # 从第一个路径推断Content目录位置
                first_path = list(found_content_dirs.values())[0]
                # 提取到Content为止的路径
                # bos:/bucket/prefix/scene/xxx/Content/yyy/ -> bos:/bucket/prefix/scene/xxx/Content/
                content_parent_path = first_path.rsplit('/Content/', 1)[0] + '/Content/'
                
                # 目标路径：raw/场景名/Content/
                target_path = f"bos:/{self.target_bucket}/{self.target_prefix}/{safe_scene_name}/Content/"
                
                copy_mappings.append((content_parent_path, target_path))
                print(f"  → 从Content父级复制到: {safe_scene_name}/Content/")
            
            # 如果没有Content，使用备选方案
            elif found_fallback_dirs:
                print(f"[INFO] 未找到Content目录，使用备选方案")
                print(f"  找到 {len(found_fallback_dirs)} 个包含资产目录的父目录:")
                
                # 使用场景名作为目标目录名（空格替换为下划线）
                safe_scene_name = scene_name.replace(' ', '_')
                
                # 如果有多个父目录，找到它们的共同父目录
                if len(found_fallback_dirs) > 1:
                    print(f"  检测到多个资产父目录，查找共同父目录")
                    
                    # 收集所有路径
                    all_paths = []
                    for parent_dir, (source_path, marker) in found_fallback_dirs.items():
                        print(f"    - {parent_dir}/ (检测到: {marker})")
                        all_paths.append(source_path)
                    
                    # 找到最短的共同前缀路径
                    # 例如: bos:/bucket/prefix/scene/City/C1/ 和 bos:/bucket/prefix/scene/City/C2/
                    # 共同前缀: bos:/bucket/prefix/scene/City/
                    common_prefix = all_paths[0]
                    for path in all_paths[1:]:
                        # 找到两个路径的共同部分
                        while not path.startswith(common_prefix):
                            # 回退到上一级目录
                            common_prefix = common_prefix.rsplit('/', 2)[0] + '/'
                    
                    # 提取共同父目录的名称
                    # bos:/bucket/prefix/scene/City/ -> City
                    common_parent_name = common_prefix.rstrip('/').rsplit('/', 1)[-1]
                    
                    print(f"  → 找到共同父目录: {common_parent_name}/")
                    
                    # 复制共同父目录
                    target_path = f"bos:/{self.target_bucket}/{self.target_prefix}/{safe_scene_name}/Content/{common_parent_name}/"
                    copy_mappings.append((common_prefix, target_path))
                    print(f"  → 将共同父目录复制到: {safe_scene_name}/Content/{common_parent_name}/")
                    
                else:
                    # 只有一个父目录
                    for parent_dir, (source_path, marker) in found_fallback_dirs.items():
                        print(f"    - {parent_dir}/ (检测到: {marker})")
                        target_path = f"bos:/{self.target_bucket}/{self.target_prefix}/{safe_scene_name}/Content/{parent_dir}/"
                        copy_mappings.append((source_path, target_path))
                        print(f"  → 将父目录复制到Content下: {safe_scene_name}/Content/{parent_dir}/")
            
            else:
                markers_list = ', '.join(self.fallback_markers)
                print(f"[WARN] 未找到Content目录或资产目录（{markers_list}）")
            
            return copy_mappings
            
        except Exception as e:
            print(f"[ERROR] 解析场景结构失败: {e}")
            return []
    
    def copy_directory(self, source_path: str, target_path: str, dry_run: bool = False, skip_validation: bool = False) -> bool:
        """
        复制BOS目录
        
        Args:
            source_path: 源路径 (bos://bucket/path/)
            target_path: 目标路径 (bos://bucket/path/)
            dry_run: 是否只预览不实际复制
            skip_validation: 是否跳过源路径验证（当路径从bcecmd ls -r提取时应跳过）
            
        Returns:
            是否成功
        """
        if dry_run:
            print(f"  [预览] {source_path} -> {target_path}")
            return True
        
        try:
            # 如果配置了跳过已存在，先检查目标路径
            if self.skip_existing:
                check_target_cmd = ['bcecmd', 'bos', 'ls', target_path, '-r']
                check_target_result = subprocess.run(
                    check_target_cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                
                if check_target_result.returncode == 0:
                    # 目标路径存在，检查是否有文件
                    target_lines = [l.strip() for l in check_target_result.stdout.strip().split('\n') if l.strip() and not l.startswith('TOTAL')]
                    if len(target_lines) > 0:
                        print(f"[SKIP] 目标路径已存在 ({len(target_lines)} 个对象)，跳过复制")
                        return True
            
            # 只有在未跳过验证时才检查源路径
            if not skip_validation:
                # 先检查源路径是否存在内容
                check_cmd = ['bcecmd', 'bos', 'ls', source_path, '-r']
                check_result = subprocess.run(
                    check_cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                
                if check_result.returncode != 0:
                    print(f"[ERROR] 源路径不存在或无法访问: {source_path}")
                    print(f"  错误: {check_result.stderr}")
                    return False
                
                # 统计文件数量
                lines = [l.strip() for l in check_result.stdout.strip().split('\n') if l.strip() and not l.startswith('TOTAL')]
                file_count = len(lines)
                
                if file_count == 0:
                    print(f"[WARN] 源路径为空，没有文件可复制: {source_path}")
                    return False
                
                print(f"  源路径包含 {file_count} 个对象")
            else:
                print(f"  跳过源路径验证（路径已从递归列表中提取）")
            
            # 使用 bcecmd bos cp 递归复制
            cmd = ['bcecmd', 'bos', 'cp', source_path, target_path, '-r', '-y']
            print(f"\n复制: {source_path}")
            print(f"  -> {target_path}")
            print(f"执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                print(f"[ERROR] 复制失败: {result.stderr}")
                return False
            
            print(f"[OK] 复制成功")
            if result.stdout:
                print(result.stdout)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 复制失败: {e}")
            return False
    
    def process_scene(self, scene_name: str, dry_run: bool = False) -> bool:
        """
        处理单个场景的复制
        
        Args:
            scene_name: 场景名称
            dry_run: 是否只预览不实际复制
            
        Returns:
            是否成功
        """
        print(f"\n{'='*70}")
        print(f"处理场景: {scene_name}")
        print(f"{'='*70}")
        
        # 解析场景结构
        copy_mappings = self.parse_scene_structure(scene_name)
        
        if not copy_mappings:
            print(f"[WARN] 场景 {scene_name} 没有需要复制的内容")
            return False
        
        # 执行复制
        success_count = 0
        for source_path, target_path in copy_mappings:
            # Content目录是从bcecmd ls -r提取的，跳过源路径验证
            if self.copy_directory(source_path, target_path, dry_run, skip_validation=True):
                success_count += 1
        
        print(f"\n{'='*70}")
        print(f"场景 {scene_name}: 成功 {success_count}/{len(copy_mappings)}")
        print(f"{'='*70}")
        
        return success_count == len(copy_mappings)
    
    def process_all_scenes(self, dry_run: bool = False, specific_scenes: Optional[List[str]] = None):
        """
        处理所有场景或指定场景
        
        Args:
            dry_run: 是否只预览不实际复制
            specific_scenes: 指定要处理的场景名称列表，None表示处理所有场景
        """
        print(f"# BOS场景复制工具")
        print(f"#")
        print(f"# 源: bos:/{self.source_bucket}/{self.source_prefix}/")
        print(f"# 目标: bos:/{self.target_bucket}/{self.target_prefix}/")
        print(f"# 模式: {'预览模式' if dry_run else '实际复制模式'}")
        
        # 列出场景
        if specific_scenes:
            scenes = specific_scenes
            print(f"处理指定的 {len(scenes)} 个场景")
        else:
            print("列出所有场景...")
            scenes = self.list_scenes()
            
            if not scenes:
                print("[ERROR] 未找到任何场景")
                return
            
            print(f"[OK] 找到 {len(scenes)} 个场景:")
            for i, scene in enumerate(scenes, 1):
                print(f"  {i}. {scene}")
        
        # 处理每个场景
        success_count = 0
        failed_scenes = []
        
        for scene_name in scenes:
            try:
                if self.process_scene(scene_name, dry_run):
                    success_count += 1
                else:
                    failed_scenes.append(scene_name)
            except KeyboardInterrupt:
                print("\n\n用户中断")
                break
            except Exception as e:
                print(f"\n[ERROR] 处理场景 {scene_name} 时出错: {e}")
                failed_scenes.append(scene_name)
        
        # 总结
        print(f"\n\n{'#'*70}")
        print(f"# 处理完成")
        print(f"#")
        print(f"# 总计: {len(scenes)} 个场景")
        print(f"# 成功: {success_count}")
        print(f"# 失败: {len(failed_scenes)}")
        if failed_scenes:
            print(f"#")
            print(f"# 失败的场景:")
            for scene in failed_scenes:
                print(f"#   - {scene}")
        print(f"{'#'*70}\n")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='BOS场景复制工具 - 从UE4场景复制到world-data/raw',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用配置文件
  python bos_copy_scenes.py -c config/bos_copy_config.json --dry-run
  
  # 预览所有场景的复制操作（不实际复制）
  python bos_copy_scenes.py --dry-run
  
  # 复制所有场景
  python bos_copy_scenes.py
  
  # 只复制指定的场景
  python bos_copy_scenes.py --scenes "Nordic Harbour" "Seaside Town"
  
  # 预览指定场景
  python bos_copy_scenes.py --dry-run --scenes "Nordic Harbour"
  
路径规则:
  策略1（优先）: 查找 /Content/ 目录，将其后的第一级目录复制到 raw/Content/ 下
  策略2（备选）: 如果没有Content，查找 Blueprints/Maps/Map/Textures 目录，
              将其上级目录复制到 raw/Content/ 下
  
  示例:
    AAA/sea/san/Content/abc/ -> raw/Content/abc/
    Nordic Harbour/Nordic Harbour/Content/NordicHarbour/ -> raw/Content/NordicHarbour/
    MyScene/Assets/Blueprints/BP1 -> raw/Content/Assets/
    SomeScene/Data/Maps/Level1 -> raw/Content/Data/
        """
    )
    
    parser.add_argument(
        '-c', '--config',
        type=str,
        help='配置文件路径（如果指定，将优先使用配置文件中的设置）'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式，只显示将要执行的操作，不实际复制'
    )
    
    parser.add_argument(
        '--scenes',
        nargs='+',
        help='指定要处理的场景名称，不指定则处理所有场景'
    )
    
    parser.add_argument(
        '--source-bucket',
        help='源bucket名称（默认: baidu-download-new，或从配置文件读取）'
    )
    
    parser.add_argument(
        '--source-prefix',
        help='源路径前缀（默认: UE4场景，或从配置文件读取）'
    )
    
    parser.add_argument(
        '--target-bucket',
        help='目标bucket名称（默认: world-data，或从配置文件读取）'
    )
    
    parser.add_argument(
        '--target-prefix',
        help='目标路径前缀（默认: raw，或从配置文件读取）'
    )
    
    args = parser.parse_args()
    
    # 创建复制器
    if args.config:
        # 使用配置文件
        copier = BosSceneCopier(config_path=args.config)
    else:
        # 使用命令行参数或默认值
        copier = BosSceneCopier(
            source_bucket=args.source_bucket,
            source_prefix=args.source_prefix,
            target_bucket=args.target_bucket,
            target_prefix=args.target_prefix
        )
    
    # 处理场景
    copier.process_all_scenes(
        dry_run=args.dry_run,
        specific_scenes=args.scenes
    )


if __name__ == '__main__':
    main()
