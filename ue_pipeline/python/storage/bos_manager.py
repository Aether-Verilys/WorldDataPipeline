"""
BOS管理器 - 负责BOS操作和状态同步
"""
from typing import Dict, List
from pathlib import Path


class BosManager:
    """BOS操作管理器"""
    
    def __init__(self, access_key_id: str = None, secret_access_key: str = None,
                 endpoint: str = "bj.bcebos.com"):
        """
        初始化BOS管理器
        
        Args:
            access_key_id: BOS访问密钥ID（可选，用于真实BOS操作）
            secret_access_key: BOS访问密钥
            endpoint: BOS端点
        """
        self.endpoint = endpoint
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self._bos_client = None
    
    @property
    def bos_client(self):
        """懒加载BOS客户端"""
        if self._bos_client is None and self.access_key_id:
            try:
                from baidubce.bce_client_configuration import BceClientConfiguration
                from baidubce.auth.bce_credentials import BceCredentials
                from baidubce.services.bos.bos_client import BosClient
                
                # 创建配置 - 按照官方文档示例
                config = BceClientConfiguration(
                    credentials=BceCredentials(self.access_key_id, self.secret_access_key),
                    endpoint=self.endpoint
                )
                
                # 设置超时和缓冲区
                config.connection_timeout_in_mills = 60 * 1000  # 60秒
                config.send_buf_size = 1024 * 1024  # 1MB
                config.recv_buf_size = 10 * 1024 * 1024  # 10MB
                
                self._bos_client = BosClient(config)
                print(f"✓ BOS客户端初始化成功: {self.endpoint}")
            except ImportError:
                raise ImportError(
                    "未安装 bce-python-sdk，请运行: pip install bce-python-sdk"
                )
        return self._bos_client
    
    def test_connection(self, bucket: str) -> tuple[bool, str]:
        """测试BOS连接和权限
        
        Returns:
            (success, message)
        """
        if not self.bos_client:
            return False, "BOS客户端未初始化"
        
        try:
            # 尝试列出bucket（测试读权限）
            self.bos_client.list_objects(bucket_name=bucket, max_keys=1)
            return True, "连接成功，有读权限"
        except Exception as e:
            error_msg = str(e)
            if "Access Denied" in error_msg:
                return False, f"权限被拒绝，请检查：\n  1. AK/SK是否正确\n  2. 是否有 {bucket} 的访问权限\n  3. Bucket是否存在"
            elif "NoSuchBucket" in error_msg:
                return False, f"Bucket不存在: {bucket}"
            else:
                return False, f"连接失败: {error_msg}"
    
    def check_scene_exists(self, bucket: str, scene_path: str) -> bool:
        """
        检查场景在BOS中是否存在
        
        Args:
            bucket: BOS bucket名称
            scene_path: 场景路径（如 "baked/Seaside_Town/"）
        
        Returns:
            是否存在
        """
        if not self.bos_client:
            raise ValueError("需要提供BOS凭证才能检查场景状态")
        
        try:
            response = self.bos_client.list_objects(
                bucket_name=bucket,
                prefix=scene_path.rstrip('/') + '/',
                max_keys=1
            )
            return len(response.contents) > 0
        except Exception as e:
            print(f"检查场景 {scene_path} 时出错: {e}")
            return False
    
    def sync_scenes_status(self, registry, bucket: str = "world-data", 
                          prefix: str = "baked/") -> Dict:
        """
        同步所有场景的BOS状态到数据库
        
        Args:
            registry: SceneRegistry实例
            bucket: BOS bucket名称
            prefix: 场景前缀路径
        
        Returns:
            同步统计结果
        """
        stats = {
            'verified': 0,      # 验证存在的场景数
            'missing': 0,       # 发现丢失的场景数
            'updated': 0,       # 状态更新的场景数
            'errors': []        # 错误列表
        }
        
        # 获取数据库中的所有场景
        scenes = registry.list_scenes()
        
        print(f"\n开始同步 {len(scenes)} 个场景的BOS状态...")
        
        for scene in scenes:
            scene_name = scene['scene_name']
            old_status = scene['bos_exists']
            
            try:
                # 从bos_baked_path提取路径
                bos_path = scene['bos_baked_path']
                if bos_path.startswith('bos://'):
                    # "bos://world-data/baked/Seaside_Town/" -> "baked/Seaside_Town/"
                    path_parts = bos_path.replace('bos://', '').split('/', 1)
                    if len(path_parts) > 1:
                        object_prefix = path_parts[1].rstrip('/')
                    else:
                        object_prefix = f"{prefix}{scene_name}"
                else:
                    object_prefix = f"{prefix}{scene_name}"
                
                # 检查BOS中是否存在
                exists = self.check_scene_exists(bucket, object_prefix)
                
                # 更新状态
                if exists != old_status:
                    registry.mark_scene_bos_status(scene_name, exists)
                    stats['updated'] += 1
                    
                    if not exists:
                        stats['missing'] += 1
                        print(f"  ⚠ {scene_name}: 在BOS中已丢失")
                    else:
                        print(f"  ✓ {scene_name}: 已恢复")
                else:
                    if exists:
                        registry.mark_scene_bos_status(scene_name, True)  # 更新验证时间
                        stats['verified'] += 1
                        print(f"  ✓ {scene_name}: 存在")
                    else:
                        stats['missing'] += 1
                        print(f"  ⚠ {scene_name}: 丢失（状态未变）")
                
            except Exception as e:
                stats['errors'].append({
                    'scene': scene_name,
                    'error': str(e)
                })
                print(f"  ✗ {scene_name}: 检查失败 - {e}")
        
        return stats
    
    def download_scene(self, bucket: str, scene_path: str, local_path: Path) -> bool:
        """
        从BOS下载场景
        
        Args:
            bucket: BOS bucket名称
            scene_path: 场景在BOS中的路径
            local_path: 本地保存路径
        
        Returns:
            是否成功
        """
        if not self.bos_client:
            raise ValueError("需要提供BOS凭证才能下载场景")
        
        try:
            # 确保本地目录存在
            local_path.mkdir(parents=True, exist_ok=True)
            
            # 列出所有对象
            marker = None
            while True:
                response = self.bos_client.list_objects(
                    bucket_name=bucket,
                    prefix=scene_path,
                    marker=marker
                )
                
                for obj in response.contents:
                    object_key = obj.key
                    # 计算本地文件路径
                    relative_path = object_key.replace(scene_path, '', 1).lstrip('/')
                    if not relative_path:
                        continue
                    
                    local_file = local_path / relative_path
                    local_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 下载文件
                    print(f"  下载: {object_key}")
                    self.bos_client.get_object_to_file(bucket, object_key, str(local_file))
                
                # 检查是否还有更多对象
                if response.is_truncated:
                    marker = response.next_marker
                else:
                    break
            
            return True
            
        except Exception as e:
            print(f"下载场景失败: {e}")
            return False
    
    def upload_scene(self, bucket: str, local_path: Path, bos_path: str, skip_patterns: list = None) -> bool:
        """
        上传场景到BOS（使用 bcecmd 命令行工具）
        
        Args:
            bucket: BOS bucket名称
            local_path: 本地场景路径
            bos_path: BOS目标路径（如 "baked/Seaside_Town/"）
            skip_patterns: 跳过的文件模式列表（如 ['.url', '.ini']）
        
        Returns:
            是否成功
        """
        import subprocess
        
        if skip_patterns is None:
            skip_patterns = ['.url', '.ini', 'Thumbs.db', '.DS_Store']
        
        try:
            # 先收集所有需要上传的文件
            files_to_upload = []
            total_size = 0
            
            for file_path in local_path.rglob('*'):
                if file_path.is_file():
                    # 检查是否跳过
                    should_skip = any(file_path.name.endswith(pattern) or pattern in file_path.name 
                                     for pattern in skip_patterns)
                    if not should_skip:
                        files_to_upload.append(file_path)
                        total_size += file_path.stat().st_size
            
            print(f"\n待上传: {len(files_to_upload)} 个文件, 总大小: {total_size / 1024 / 1024:.2f} MB\n")
            
            uploaded = 0
            uploaded_size = 0
            failed = 0
            
            # 使用 bcecmd 上传文件
            for file_path in files_to_upload:
                # 计算相对路径
                relative_path = file_path.relative_to(local_path)
                object_key = f"{bos_path.rstrip('/')}/{relative_path.as_posix()}"
                bos_url = f"bos://{bucket}/{object_key}"
                file_size = file_path.stat().st_size
                
                try:
                    # 显示进度
                    size_mb = file_size / 1024 / 1024
                    print(f"  [{uploaded}/{len(files_to_upload)}] 上传: {file_path.name} ({size_mb:.2f} MB)")
                    
                    # 使用 bcecmd 上传
                    cmd = ['bcecmd', 'bos', 'cp', str(file_path), bos_url, '-y']
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='ignore'
                    )
                    
                    if result.returncode == 0:
                        uploaded += 1
                        uploaded_size += file_size
                    else:
                        failed += 1
                        error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
                        print(f"  ✗ 上传失败: {error_msg[:100]}")
                        
                except Exception as e:
                    failed += 1
                    print(f"  ✗ 上传失败 {file_path.name}: {e}")
            
            print(f"\n上传完成:")
            print(f"  成功: {uploaded} 个文件 ({uploaded_size / 1024 / 1024:.2f} MB)")
            if failed > 0:
                print(f"  失败: {failed} 个文件")
            
            return uploaded > 0
            
        except Exception as e:
            print(f"上传场景失败: {e}")
            import traceback
            traceback.print_exc()
            return False
