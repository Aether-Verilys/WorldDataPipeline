from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def resolve_manifest_path(env_value: Optional[str], argv: List[str]) -> Optional[str]:
    """Resolve manifest path from env value or argv.

    Accepts:
    - env_value: the value of an environment variable (already looked up)
    - argv: full argv list (may include script path)

    Supported argv forms:
    - --manifest=PATH
    - --manifest PATH
    """
    if env_value:
        return env_value

    for i, arg in enumerate(argv):
        if isinstance(arg, str) and arg.startswith("--manifest="):
            return arg.split("=", 1)[1]
        if arg == "--manifest" and i + 1 < len(argv):
            return argv[i + 1]

    return None


def resolve_manifest_path_from_env(env_key: str, argv: List[str]) -> Optional[str]:
    """Resolve manifest path using an env var key plus argv fallback."""
    return resolve_manifest_path(os.environ.get(env_key), argv)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object")
    return obj
