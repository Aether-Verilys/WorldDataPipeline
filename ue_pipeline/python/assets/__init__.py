"""Asset management modules."""

from .scene_registry import SceneRegistry, calculate_directory_hash
from .scene_scanner import (
    scan_local_scene_folders,
    scan_scene_maps,
    scan_local_sequences,
)

try:
    from .asset_manager import (
        ensure_directory_exists,
        create_level_sequence,
        save_asset,
        save_current_level,
    )
except ImportError:
    pass

__all__ = [
    "SceneRegistry",
    "calculate_directory_hash",
    "scan_local_scene_folders",
    "scan_scene_maps",
    "scan_local_sequences",
    "ensure_directory_exists",
    "create_level_sequence",
    "save_asset",
    "save_current_level",
]
