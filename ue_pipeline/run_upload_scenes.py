"""
上传已烘焙场景到BOS
从 ue_config.json 读取配置，上传所有 navmesh_baked=true 的场景
"""

import sys
from pathlib import Path

# 直接调用 python/bos/upload_scenes.py
sys.path.insert(0, str(Path(__file__).parent))

from python.bos.upload_scenes import main

if __name__ == "__main__":
    sys.exit(main())
