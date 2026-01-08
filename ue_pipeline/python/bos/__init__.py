"""BOS模块 - 百度云对象存储管理"""

from .bos_client import (
    BosClientManager,
    get_bos_manager,
    initialize_bos,
    bos_download,
    bos_upload,
    bos_delete,
    bos_list,
    bos_exists,
)
from .bos_manager import BosManager, MockBosManager
from .upload_scenes import main as upload_scenes_main
from .download_scene import BosSceneDownloader
from .copy_scenes import BosSceneCopier

__all__ = [
    # 新的统一BOS客户端
    'BosClientManager',
    'get_bos_manager',
    'initialize_bos',
    'bos_download',
    'bos_upload',
    'bos_delete',
    'bos_list',
    'bos_exists',
    # 旧的BOS管理器（保持向后兼容）
    'BosManager', 
    'MockBosManager',
    # BOS操作类
    'BosSceneDownloader',
    'BosSceneCopier',
    'upload_scenes_main',
]
