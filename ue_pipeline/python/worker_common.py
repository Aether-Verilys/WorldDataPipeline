from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def resolve_manifest_path(env_value: Optional[str], argv: List[str]) -> Optional[str]:
    if env_value:
        return env_value

    for i, arg in enumerate(argv):
        if isinstance(arg, str) and arg.startswith("--manifest="):
            return arg.split("=", 1)[1]
        if arg == "--manifest" and i + 1 < len(argv):
            return argv[i + 1]

    return None


def resolve_manifest_path_from_env(env_key: str, argv: List[str]) -> Optional[str]:
    return resolve_manifest_path(os.environ.get(env_key), argv)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object")
    return obj


def auto_append_date_to_output_dirs(manifest: Dict[str, Any], date_format: str = "%Y-%m-%d") -> Dict[str, Any]:
    """
    Examples:
        "output" -> "output/2026-01-22"
        "output_base_dir": "output" -> "output_base_dir": "output/2026-01-22"
        "output/2026-01-22" -> "output/2026-01-22" (no change)
    """
    today = datetime.now().strftime(date_format)
    
    def append_date_if_needed(path: str) -> str:
        """Append date to path if not already present."""
        if not path or not isinstance(path, str):
            return path
        
        # Normalize path separators
        normalized = path.replace('\\', '/')
        
        # Check if path already ends with a date pattern (YYYY-MM-DD or similar)
        import re
        date_pattern = r'/\d{4}-\d{2}-\d{2}$'
        if re.search(date_pattern, normalized):
            return path  # Already has date suffix
        
        # Append date
        return f"{normalized.rstrip('/')}/{today}"
    
    def process_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively process dictionary."""
        result = {}
        for key, value in d.items():
            if isinstance(value, dict):
                result[key] = process_dict(value)
            elif isinstance(value, str):
                # Check if this is an output directory key
                key_lower = key.lower()
                if ('output' in key_lower and 'dir' in key_lower) or key_lower.endswith('_dir'):
                    result[key] = append_date_if_needed(value)
                else:
                    result[key] = value
            else:
                result[key] = value
        return result
    
    return process_dict(manifest)

