"""BOS and scene storage modules."""

try:
    from .bos_client import initialize_bos, BosClientManager
    from .bos_manager import BosManager
    from .bos_uploader import BosUploader
    HAS_BOS = True
except ImportError:
    HAS_BOS = False
    initialize_bos = None
    BosClientManager = None
    BosManager = None
    BosUploader = None

__all__ = [
    "initialize_bos",
    "BosClientManager",
    "BosManager",
    "BosUploader",
    "HAS_BOS",
]
