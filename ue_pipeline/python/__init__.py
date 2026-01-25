"""
UE Pipeline Python Package
Utilities and workers for Unreal Engine automation.
"""

__version__ = "1.0.0"

# Re-export commonly used modules for convenient imports
from . import core
from . import assets
from . import sequence
from . import storage

# Direct exports of most commonly used items
from .core import logger
from .core.job_utils import resolve_manifest_path_from_env, auto_append_date_to_output_dirs

__all__ = [
    "core",
    "assets",
    "sequence",
    "storage",
    "logger",
    "resolve_manifest_path_from_env",
    "auto_append_date_to_output_dirs",
]
