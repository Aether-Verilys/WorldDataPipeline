import os
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from .logger import logger


# ============================================================================
# Manifest Path Resolution
# ============================================================================

def resolve_manifest_path(env_value: Optional[str], argv: List[str]) -> Optional[str]:
    """Resolve manifest path from environment variable or command-line arguments.
    
    Args:
        env_value: Value from environment variable
        argv: Command-line arguments list
    
    Returns:
        Manifest path if found, None otherwise
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
    """Resolve manifest path from environment variable by key.
    
    Args:
        env_key: Environment variable name (e.g., 'UE_MANIFEST_PATH')
        argv: Command-line arguments list
    
    Returns:
        Manifest path if found, None otherwise
    """
    return resolve_manifest_path(os.environ.get(env_key), argv)


# ============================================================================
# Date Auto-Append Utility
# ============================================================================

def auto_append_date_to_output_dirs(manifest: Dict[str, Any], date_format: str = "%Y-%m-%d") -> Dict[str, Any]:
    """Automatically append current date to output directory paths in manifest.
    
    Examples:
        "output" -> "output/2026-01-22"
        "output_base_dir": "output" -> "output_base_dir": "output/2026-01-22"
        "output/2026-01-22" -> "output/2026-01-22" (no change)
    
    Args:
        manifest: Manifest dictionary
        date_format: Date format string (default: "%Y-%m-%d")
    
    Returns:
        Modified manifest with dates appended to output directories
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


# ============================================================================
# Manifest Loading
# ============================================================================

def load_manifest(manifest_path: str) -> dict:
    if not os.path.exists(manifest_path):
        logger.error(f"Manifest file not found: {manifest_path}")
        sys.exit(1)
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        # Automatically append current date to output directories
        manifest = auto_append_date_to_output_dirs(manifest)
        
        return manifest
    except Exception as e:
        logger.error(f"Cannot parse manifest: {e}")
        sys.exit(1)

def validate_manifest_type(manifest: dict, expected_type: str) -> str:
    job_id = manifest.get('job_id', 'unknown')
    job_type = manifest.get('job_type', 'unknown')
    
    if job_type != expected_type:
        logger.error(f"Invalid job type '{job_type}', expected '{expected_type}'")
        sys.exit(1)
    
    return job_id

def load_default_ue_config() -> dict:
    # This utility is in ue_pipeline/python/job_utils.py
    # Config is in ue_pipeline/config/ue_config.json
    script_dir = Path(__file__).parent.parent
    env_config_path = os.environ.get('UE_CONFIG_PATH')
    config_path = Path(env_config_path) if env_config_path else (script_dir / 'config' / 'ue_config.json')
    
    if not config_path.exists():
        logger.warning(f"UE config file not found: {config_path}")
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load UE config: {e}")
        return {}

def get_ue_config(manifest: dict) -> dict:
    # Load default config first
    default_config = load_default_ue_config()
    
    # Merge with manifest config (manifest overrides default)
    manifest_config = manifest.get('ue_config', {})
    ue_config = {**default_config, **manifest_config}
    
    if not ue_config:
        logger.error("No ue_config found in manifest or default config file")
        sys.exit(1)
    
    # Resolve Editor path
    editor_cmd = ue_config.get('editor_cmd')
    if not editor_cmd:
        logger.error("Missing 'editor_cmd' in ue_config")
        sys.exit(1)
    
    # Resolve Project path
    project = ue_config.get('project_path')
    if not project:
        logger.error("Missing 'project_path' in ue_config")
        sys.exit(1)
    
    # Handle optional output_base_dir
    output_base_dir = ue_config.get('output_base_dir')
    if output_base_dir == "default":
        repo_root = Path(__file__).parent.parent.parent.parent
        output_base_dir = str(repo_root / "output")
        ue_config['output_base_dir'] = output_base_dir
        logger.info(f"Using default output directory: {output_base_dir}")
        
    return ue_config

def validate_paths(ue_config: dict, worker_scripts: list = None):
    editor_cmd = ue_config.get('editor_cmd')
    project = ue_config.get('project_path')
    
    if not os.path.exists(editor_cmd):
        logger.error(f"UE Editor not found at: {editor_cmd}")
        sys.exit(1)
    
    if not os.path.exists(project):
        logger.error(f"Project not found at: {project}")
        sys.exit(1)
    
    if worker_scripts:
        for script in worker_scripts:
            if not os.path.exists(script):
                logger.error(f"Worker script not found at: {script}")
                sys.exit(1)

def save_manifest(manifest: dict, manifest_path: str):
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.info(f"Manifest file updated: {manifest_path}")
    except Exception as e:
        logger.warning(f"Failed to update manifest file: {e}")


def deep_merge(base: dict, override: dict) -> dict:
    """
    深度合并两个字典，override 中的值会覆盖 base 中的值
    
    Args:
        base: 基础配置字典
        override: 覆盖配置字典
    
    Returns:
        合并后的配置字典
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # 递归合并嵌套字典
            result[key] = deep_merge(result[key], value)
        else:
            # 直接覆盖
            result[key] = value
    
    return result


def load_template(template_path: str) -> dict:
    """
    加载模板配置文件
    
    Args:
        template_path: 模板文件路径（相对或绝对路径）
    
    Returns:
        模板配置字典
    """
    # 如果是相对路径，从项目根目录解析
    if not os.path.isabs(template_path):
        # job_utils.py is in ue_pipeline/python/core/, so we need 4 parents to reach repo root
        repo_root = Path(__file__).parent.parent.parent.parent
        template_path = str(repo_root / template_path)
    
    if not os.path.exists(template_path):
        logger.warning(f"Template file not found: {template_path}")
        return {}
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template = json.load(f)
        logger.info(f"Loaded template: {template_path}")
        return template
    except Exception as e:
        logger.warning(f"Failed to load template: {e}")
        return {}


def merge_configs(manifest: dict) -> dict:
    """
    合并manifest中的各种配置来源，优先级从低到高：
    1. 模板配置文件（如果指定了 template 字段）
    2. 默认的 ue_config.json
    3. manifest 中的 ue_config
    4. manifest 中的其他配置字段
    
    支持的配置覆盖：
    - ue_config: 引擎和项目路径配置
    - map/maps: 地图配置  
    - sequence_config: 序列配置
    - navmesh_config: 导航网格配置
    - rendering: 渲染配置
    
    Args:
        manifest: 作业清单字典
    
    Returns:
        完整合并后的manifest
    """
    # 0. 如果指定了模板，先加载模板作为基础
    template_path = manifest.get('template', '')
    if template_path:
        template = load_template(template_path)
        # 深度合并：模板作为基础，manifest 覆盖模板
        manifest = deep_merge(template, manifest)
        # 移除 template 字段，避免递归
        manifest.pop('template', None)
        logger.info(f"Applied template configuration from: {template_path}")
    
    # 1. 加载默认 UE 配置
    default_ue_config = load_default_ue_config()
    
    # 2. 合并 manifest 中的 ue_config（如果有）
    manifest_ue_config = manifest.get('ue_config', {})
    merged_ue_config = deep_merge(default_ue_config, manifest_ue_config)
    
    # 处理 project_path 的 "default" 值
    project_path = merged_ue_config.get('project_path')
    if project_path == "default":
        repo_root = Path(__file__).parent.parent.parent.parent
        merged_ue_config['project_path'] = str(repo_root / "ue_template" / "project" / "WorldData.uproject")
    
    # 处理 output_base_dir 的 "default" 值或相对路径
    output_base_dir = merged_ue_config.get('output_base_dir')
    if output_base_dir == "default":
        repo_root = Path(__file__).parent.parent.parent.parent
        merged_ue_config['output_base_dir'] = str(repo_root / "output")
    elif output_base_dir and not os.path.isabs(output_base_dir):
        # 相对路径转换为绝对路径（相对于项目根目录）
        repo_root = Path(__file__).parent.parent.parent.parent
        merged_ue_config['output_base_dir'] = str(repo_root / output_base_dir)
        logger.info(f"Resolved relative output_base_dir to: {merged_ue_config['output_base_dir']}")
    
    # 将合并后的 ue_config 写回 manifest
    manifest['ue_config'] = merged_ue_config
    
    return manifest


def extract_map_name(map_path: str) -> str:
    """Extract map name from map asset path.
    
    Examples:
        /Game/SecretBase/Map/Level_Day -> Level_Day
        /Game/Hong_Kong_Street/Maps/MainLevel -> MainLevel
    
    Args:
        map_path: UE asset path to the map
    
    Returns:
        Map name (last component of path), or "Unknown" if empty
    """
    if not map_path:
        return "Unknown"
    return map_path.split("/")[-1]


def derive_output_dir_from_map(map_path: str) -> str:
    """Derive output directory from map path.
    
    Derives the sequence output directory based on map location.
    Places sequences in a /Sequence folder at the scene root level.
    
    Examples:
        /Game/SecretBase/Map/Level_Day -> /Game/SecretBase/Sequence
        /Game/Hong_Kong_Street/Maps/MainLevel -> /Game/Hong_Kong_Street/Sequence
    
    Args:
        map_path: UE asset path to the map
    
    Returns:
        Output directory path, or None if derivation fails
    """
    if not map_path:
        return None
    
    parts = map_path.split('/')
    if len(parts) < 3:  # Need at least /Game/SceneName/...
        return None
    
    # Find scene root directory (typically first level after /Game/)
    # /Game/SecretBase/Map -> /Game/SecretBase
    scene_root = '/'.join(parts[:3])
    
    output_dir = f"{scene_root}/Sequence"
    
    return output_dir


def extract_scene_folder_from_sequence_path(sequence_path: str) -> str:
    """
    从序列路径中提取场景文件夹名称
    
    Sequence path format: /Game/SceneName/Sequence/SequenceName
    Returns: SceneName (the folder between /Game/ and /Sequence/)
    
    Examples:
        /Game/Hong_Kong_Street/Sequence/Demo001 -> Hong_Kong_Street
        /Game/JapaneseVilliage/Sequence/JapaneseVilliage001 -> JapaneseVilliage
    
    Args:
        sequence_path: UE asset path to the sequence
        
    Returns:
        Scene folder name, or "UnknownScene" if extraction fails
    """
    if not sequence_path:
        return "UnknownScene"
    
    # Split path: /Game/Hong_Kong_Street/Sequence/Demo001
    # -> ['', 'Game', 'Hong_Kong_Street', 'Sequence', 'Demo001']
    path_parts = sequence_path.split("/")
    
    if len(path_parts) >= 4:
        # Get the scene folder (third element after split, index 2)
        # This is the folder between /Game/ and /Sequence/
        return path_parts[2]
    elif len(path_parts) >= 3:
        # Fallback: use third part if structure is shorter
        return path_parts[2]
    else:
        # Last resort
        return path_parts[-1] if path_parts else "UnknownScene"


def build_output_directory(manifest: dict, sequence_path: str, subdirectory: Optional[str] = None) -> str:
    """
    构建统一的输出目录路径，供序列创建、相机导出、渲染共用
    
    输出格式: output_base_dir/场景名/序列名[/subdirectory]
    例如: D:/WorldDataPipeline/output/2026-01-25/LevelPrototyping/test_011/render
    
    注意: manifest中的ue_config.output_base_dir已经通过auto_append_date_to_output_dirs自动添加了日期
    
    Args:
        manifest: 包含ue_config的manifest字典
        sequence_path: UE序列路径，如 /Game/LevelPrototyping/Sequence/test_011
        subdirectory: 可选的子目录名，如 "render", "camera", "Sequence"
        
    Returns:
        绝对路径，使用系统路径分隔符
    """
    ue_config = manifest.get("ue_config", {})
    output_base = ue_config.get("output_base_dir", "output")
    
    # Handle "default" value
    if output_base == "default":
        repo_root = Path(__file__).parent.parent.parent.parent
        output_base = str(repo_root / "output")
    
    # Ensure output_base is absolute path
    if not os.path.isabs(output_base):
        repo_root = Path(__file__).parent.parent.parent.parent
        output_base = str(repo_root / output_base)
    
    # Extract scene folder and sequence name
    scene_folder = extract_scene_folder_from_sequence_path(sequence_path)
    sequence_name = sequence_path.split("/")[-1] if sequence_path else "UnknownSequence"
    
    # Build path: output_base/scene_folder/sequence_name[/subdirectory]
    if subdirectory:
        output_dir = os.path.join(output_base, scene_folder, sequence_name, subdirectory)
    else:
        output_dir = os.path.join(output_base, scene_folder, sequence_name)
    
    # Convert to absolute path and normalize
    output_dir = os.path.abspath(output_dir)
    
    return output_dir
