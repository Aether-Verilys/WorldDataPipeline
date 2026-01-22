import os
import json
import sys
from pathlib import Path
from ue_pipeline.python.logger import logger
from ue_pipeline.python.worker_common import auto_append_date_to_output_dirs

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
    
    # Handle "default" value - use ue_template project
    if project == "default":
        # Root is 3 levels up from this file (ue_pipeline/python/job_utils.py)
        repo_root = Path(__file__).parent.parent.parent
        project = str(repo_root / "ue_template" / "project" / "WorldData.uproject")
        ue_config['project_path'] = project
        logger.info(f"Using default project: {project}")
    
    # Handle optional output_base_dir
    output_base_dir = ue_config.get('output_base_dir')
    if output_base_dir == "default":
        repo_root = Path(__file__).parent.parent.parent
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
        repo_root = Path(__file__).parent.parent.parent
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
        repo_root = Path(__file__).parent.parent.parent
        merged_ue_config['project_path'] = str(repo_root / "ue_template" / "project" / "WorldData.uproject")
    
    # 处理 output_base_dir 的 "default" 值或相对路径
    output_base_dir = merged_ue_config.get('output_base_dir')
    if output_base_dir == "default":
        repo_root = Path(__file__).parent.parent.parent
        merged_ue_config['output_base_dir'] = str(repo_root / "output")
    elif output_base_dir and not os.path.isabs(output_base_dir):
        # 相对路径转换为绝对路径（相对于项目根目录）
        repo_root = Path(__file__).parent.parent.parent
        merged_ue_config['output_base_dir'] = str(repo_root / output_base_dir)
        logger.info(f"Resolved relative output_base_dir to: {merged_ue_config['output_base_dir']}")
    
    # 将合并后的 ue_config 写回 manifest
    manifest['ue_config'] = merged_ue_config
    
    return manifest


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
