from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from .logger import logger
from .job_utils import build_output_directory


def parse_rendering_config(manifest: dict, framerate: int = 0) -> Tuple[str, str, str, str, int]:
    """Extract rendering-related configuration values from a manifest.

    Returns: (base_output_path, project_path, map_path, sequence_path, framerate)
    Raises ValueError on missing required fields.
    """
    rendering_cfg = manifest.get("rendering", {})
    ue_cfg = manifest.get("ue_config", {})

    base_output_path = rendering_cfg.get("output_path") or ue_cfg.get("output_base_dir")
    if base_output_path == "default":
        repo_root = Path(__file__).parent.parent.parent
        base_output_path = str(repo_root / "output")
        logger.info(f"Using default base_output_path: {base_output_path}")

    project_path = ue_cfg.get("project_path")
    if project_path == "default":
        repo_root = Path(__file__).parent.parent.parent
        project_path = str(repo_root / "ue_template" / "project" / "WorldData.uproject")

    map_path = manifest.get("map")
    sequence_path = manifest.get("sequence")

    if framerate == 0:
        fr = rendering_cfg.get("framerate")
        if fr:
            framerate = fr
            logger.info(f"Using framerate from rendering config: {framerate}")
        else:
            framerate = 30
            logger.info(f"No framerate in config, using default: {framerate} fps")

    if not all([base_output_path, project_path, map_path, sequence_path]):
        raise ValueError("Config missing required fields (output_path (or ue_config.output_base_dir), project_path, map, or sequence)")

    return base_output_path, project_path, map_path, sequence_path, framerate


def get_output_dir_from_manifest(manifest: dict, sequence_path: str, subdirectory: str | None = None) -> Path:
    """Return absolute output directory Path for a sequence using shared job_utils builder."""
    # build_output_directory already normalizes and returns absolute path
    output = build_output_directory(manifest, sequence_path, subdirectory)
    return Path(output)
