"""
统一的BOS客户端管理器
- 单例模式，全局共享一个BosClient实例
- 支持多种凭证配置方式
- 提供统一的BOS操作接口
"""

import os
import json
from pathlib import Path
from typing import Optional, List
from threading import Lock


class BosClientManager:
    """BOS客户端管理器（单例模式）"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化（只执行一次）"""
        if self._initialized:
            return
            
        self._bos_client = None
        self._access_key_id = None
        self._secret_access_key = None
        self._endpoint = "bj.bcebos.com"
        self._initialized = True
    
    def initialize(self, 
                   access_key_id: Optional[str] = None,
                   secret_access_key: Optional[str] = None,
                   endpoint: str = "bj.bcebos.com",
                   config_file: Optional[str] = None) -> 'BosClientManager':
        """
        初始化BOS客户端
        
        优先级：
        1. 直接传入的参数
        2. 配置文件
        3. 环境变量
        
        Args:
            access_key_id: Access Key ID
            secret_access_key: Secret Access Key
            endpoint: BOS endpoint
            config_file: BOS配置文件路径（JSON格式）
        
        Returns:
            self（支持链式调用）
        """
        # 优先级1: 直接传入的参数
        if access_key_id and secret_access_key:
            self._access_key_id = access_key_id
            self._secret_access_key = secret_access_key
            self._endpoint = endpoint
            print(f"✓ BOS凭证: 使用传入参数")
        
        # 优先级2: 从配置文件读取
        elif config_file:
            self._load_from_config_file(config_file)
        
        # 优先级3: 尝试自动查找配置文件
        elif self._try_auto_load_config():
            pass  # 已在 _try_auto_load_config 中加载
        
        # 优先级4: 从环境变量读取
        elif self._load_from_env():
            pass  # 已在 _load_from_env 中加载
        
        else:
            print("\n⚠ 警告: 未提供BOS凭证，BOS操作将不可用")
            print("请使用以下任一方式提供凭证：")
            print("  1. 创建配置文件: ue_pipeline/config/bos_config.json")
            print("  2. 设置环境变量: BCE_ACCESS_KEY_ID, BCE_SECRET_ACCESS_KEY")
            print("  3. 代码中调用: bos_manager.initialize(ak, sk)")
        
        # 创建客户端实例
        if self._access_key_id and self._secret_access_key:
            self._create_client()
        
        return self
    
    def _load_from_config_file(self, config_path: str) -> bool:
        """从配置文件加载凭证"""
        config_path_obj = Path(config_path)
        
        # 尝试多种路径解析
        if not config_path_obj.exists():
            # 相对于项目根目录
            config_path_obj = Path(__file__).parent.parent.parent / config_path
        
        if config_path_obj.exists():
            try:
                with open(config_path_obj, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self._access_key_id = config.get('access_key_id')
                    self._secret_access_key = config.get('secret_access_key')
                    self._endpoint = config.get('endpoint', 'bj.bcebos.com')
                    
                    if self._access_key_id and self._secret_access_key:
                        print(f"✓ BOS凭证: 从配置文件加载 ({config_path_obj})")
                        return True
            except Exception as e:
                print(f"✗ 读取配置文件失败: {e}")
        
        return False
    
    def _try_auto_load_config(self) -> bool:
        """尝试自动查找并加载配置文件"""
        # 常见的配置文件位置
        possible_paths = [
            "ue_pipeline/config/bos_config.json",
            "config/bos_config.json",
            Path(__file__).parent.parent / "config" / "bos_config.json",
        ]
        
        for path in possible_paths:
            if self._load_from_config_file(str(path)):
                return True
        
        return False
    
    def _load_from_env(self) -> bool:
        """从环境变量加载凭证"""
        ak = os.environ.get('BCE_ACCESS_KEY_ID') or os.environ.get('BOS_AK')
        sk = os.environ.get('BCE_SECRET_ACCESS_KEY') or os.environ.get('BOS_SK')
        endpoint = os.environ.get('BCE_ENDPOINT', 'bj.bcebos.com')
        
        if ak and sk:
            self._access_key_id = ak
            self._secret_access_key = sk
            self._endpoint = endpoint
            print(f"✓ BOS凭证: 从环境变量加载")
            return True
        
        return False
    
    def _create_client(self):
        """创建BOS客户端实例"""
        try:
            from baidubce.bce_client_configuration import BceClientConfiguration
            from baidubce.auth.bce_credentials import BceCredentials
            from baidubce.services.bos.bos_client import BosClient
            
            config = BceClientConfiguration(
                credentials=BceCredentials(self._access_key_id, self._secret_access_key),
                endpoint=self._endpoint
            )
            
            # 设置超时和缓冲区（参考run.py的最佳实践）
            config.connection_timeout_in_mills = 60 * 1000  # 60秒
            config.send_buf_size = 1024 * 1024  # 1MB
            config.recv_buf_size = 10 * 1024 * 1024  # 10MB
            
            self._bos_client = BosClient(config)
            print(f"✓ BOS客户端初始化成功: {self._endpoint}")
            
        except ImportError:
            raise ImportError(
                "未安装 bce-python-sdk，请运行: pip install bce-python-sdk"
            )
        except Exception as e:
            print(f"✗ BOS客户端初始化失败: {e}")
            raise
    
    @property
    def client(self):
        """获取BOS客户端实例"""
        if self._bos_client is None:
            raise RuntimeError(
                "BOS客户端未初始化，请先调用 initialize() 方法或提供有效凭证"
            )
        return self._bos_client
    
    @property
    def is_available(self) -> bool:
        """检查BOS客户端是否可用"""
        return self._bos_client is not None
    
    # ========== 便捷的BOS操作方法 ==========
    
    def download(self, bucket_name: str, object_key: str, file_name: str):
        """下载对象到文件"""
        dir_name = os.path.dirname(file_name)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self.client.get_object_to_file(bucket_name, object_key, file_name)
    
    def upload(self, bucket_name: str, object_key: str, file_name: str):
        """上传文件到BOS"""
        self.client.put_object_from_file(bucket_name, object_key, file_name)
    
    def delete(self, bucket_name: str, object_key: str | List[str], max_batch: int = 1000):
        """删除对象（支持单个或批量）"""
        if isinstance(object_key, str):
            self.client.delete_object(bucket_name, object_key)
        else:
            for i in range(0, len(object_key), max_batch):
                batch = object_key[i : i + max_batch]
                self.client.delete_multiple_objects(bucket_name, batch)
    
    def list_objects(self, bucket_name: str, prefix: Optional[str] = None) -> List[str]:
        """列出对象"""
        return [o.key for o in self.client.list_all_objects(bucket_name, prefix=prefix)]
    
    def exists(self, bucket_name: str, prefix: str) -> bool:
        """检查对象是否存在"""
        try:
            response = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=prefix.rstrip('/') + '/',
                max_keys=1
            )
            return len(response.contents) > 0
        except Exception:
            return False
    
    def test_connection(self, bucket: str) -> tuple[bool, str]:
        """测试BOS连接和权限"""
        if not self.is_available:
            return False, "BOS客户端未初始化"
        
        try:
            self.client.list_objects(bucket_name=bucket, max_keys=1)
            return True, f"连接成功，可访问 bucket: {bucket}"
        except Exception as e:
            error_msg = str(e)
            if "Access Denied" in error_msg:
                return False, f"权限被拒绝，请检查AK/SK和bucket权限"
            elif "NoSuchBucket" in error_msg:
                return False, f"Bucket不存在: {bucket}"
            else:
                return False, f"连接失败: {error_msg}"


# ========== 全局单例访问 ==========

# 全局BOS客户端管理器实例
_global_bos_manager = BosClientManager()


def get_bos_manager() -> BosClientManager:
    """获取全局BOS客户端管理器实例"""
    return _global_bos_manager


def initialize_bos(access_key_id: Optional[str] = None,
                  secret_access_key: Optional[str] = None,
                  endpoint: str = "bj.bcebos.com",
                  config_file: Optional[str] = None) -> BosClientManager:
    """
    初始化全局BOS客户端
    
    这是推荐的初始化方式，在应用入口处调用一次即可
    """
    return _global_bos_manager.initialize(
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        endpoint=endpoint,
        config_file=config_file
    )


# ========== 便捷函数（兼容旧代码） ==========

def bos_download(bucket_name: str, object_key: str, file_name: str):
    """便捷函数：下载对象"""
    return get_bos_manager().download(bucket_name, object_key, file_name)


def bos_upload(bucket_name: str, object_key: str, file_name: str):
    """便捷函数：上传对象"""
    return get_bos_manager().upload(bucket_name, object_key, file_name)


def bos_delete(bucket_name: str, object_key: str | List[str], max_batch: int = 1000):
    """便捷函数：删除对象"""
    return get_bos_manager().delete(bucket_name, object_key, max_batch)


def bos_list(bucket_name: str, prefix: Optional[str] = None) -> List[str]:
    """便捷函数：列出对象"""
    return get_bos_manager().list_objects(bucket_name, prefix)


def bos_exists(bucket_name: str, prefix: str) -> bool:
    """便捷函数：检查对象是否存在"""
    return get_bos_manager().exists(bucket_name, prefix)
