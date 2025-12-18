import unreal
from typing import List, Optional
import gc

def discover_level_sequences(directory: str = "/Game/CameraController/2025-12-04") -> List[str]:
    """
    Discover all Level Sequence assets in a directory (non-recursive)
    
    Args:
        directory: The directory path to search for level sequences
        
    Returns:
        List of level sequence asset paths
    """
    if not unreal.EditorAssetLibrary.does_directory_exist(directory):
        unreal.log_warning(f"[Rendering] 目录不存在: {directory}")
        return []
    
    assets = unreal.EditorAssetLibrary.list_assets(directory, recursive=False, include_folder=False)
    sequences = []
    
    for asset_path in assets:
        asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        if not asset_data:
            continue
        
        # Check if it's a LevelSequence
        if asset_data.asset_class_path.asset_name == "LevelSequence":
            sequences.append(asset_path)
            unreal.log(f"[Rendering] 发现序列: {asset_path}")
    
    return sorted(sequences)


def optimize_render_config_for_memory(config: unreal.MoviePipelinePrimaryConfig) -> None:
    """
    优化渲染配置以减少内存使用，防止长序列渲染时内存耗尽
    
    Args:
        config: Movie Pipeline config to optimize
    """
    settings = config.get_all_settings()
    
    for setting in settings:
        # 优化抗锯齿设置 - 减少内存占用
        if isinstance(setting, unreal.MoviePipelineAntiAliasingSetting):
            # 使用较低的空间采样数
            if hasattr(setting, 'spatial_sample_count'):
                original = setting.spatial_sample_count
                setting.spatial_sample_count = min(original, 2)  # 限制最大为2
                unreal.log(f"[Rendering] 优化空间采样: {original} -> {setting.spatial_sample_count}")
            
            # 使用较低的时间采样数
            if hasattr(setting, 'temporal_sample_count'):
                original = setting.temporal_sample_count
                setting.temporal_sample_count = min(original, 2)  # 限制最大为2
                unreal.log(f"[Rendering] 优化时间采样: {original} -> {setting.temporal_sample_count}")
        
        # 优化延迟渲染设置
        if isinstance(setting, unreal.MoviePipelineDeferredPassBase):
            # 禁用不必要的渲染通道
            if hasattr(setting, 'disable_multisample_effects'):
                setting.disable_multisample_effects = True
                unreal.log("[Rendering] 禁用多重采样效果以节省内存")
        
        # 优化输出设置
        if isinstance(setting, unreal.MoviePipelineOutputSetting):
            # 确保每帧后刷新磁盘缓存
            if hasattr(setting, 'flush_disk_writes_per_shot'):
                setting.flush_disk_writes_per_shot = True
                unreal.log("[Rendering] 启用每镜头刷新磁盘写入")
    
    unreal.log("[Rendering] 渲染配置已优化以减少内存使用")


def log_output_settings(config: unreal.MoviePipelinePrimaryConfig, context: str) -> None:
    """Log output settings to help diagnose file naming issues."""
    try:
        settings = config.get_all_settings()
        unreal.log(f"[Rendering] {context} settings total: {len(settings)}")
        for idx, setting in enumerate(settings):
            try:
                class_name = setting.get_class().get_name()
            except Exception:
                class_name = type(setting).__name__
            if isinstance(setting, unreal.MoviePipelineOutputSetting):
                directory = getattr(setting, "output_directory", None)
                directory_path = getattr(directory, "path", "") if directory else ""
                file_format = getattr(setting, "file_name_format", "")
                extension = getattr(setting, "output_file_extension", "")
                ensure_unique = getattr(setting, "ensure_unique_filenames", None)
                overrides = getattr(setting, "file_name_format_overrides", None)
                unreal.log(
                    f"[Rendering] {context} OutputSetting[{idx}] class={class_name} dir='{directory_path}' fmt='{file_format}' ext='{extension}' unique={ensure_unique}"
                )
                if overrides:
                    unreal.log(f"[Rendering] {context} OutputSetting overrides: {overrides}")
            else:
                unreal.log(f"[Rendering] {context} Setting[{idx}] class={class_name}")
    except Exception as exc:
        unreal.log_warning(f"[Rendering] {context} Failed to inspect settings: {exc}")


def create_render_job(
    sequence_path: str,
    config_path: str = "/Game/CameraController/Pending_MoviePipelinePrimaryConfig",
    output_directory: Optional[str] = None,
    map_path: Optional[str] = None
) -> Optional[unreal.MoviePipelineExecutorJob]:
    """
    Create a Movie Pipeline render job for a level sequence
    
    Args:
        sequence_path: Path to the level sequence asset
        config_path: Path to the Movie Pipeline config preset
        output_directory: Custom output directory (None = use default)
        map_path: Path to the map to use (None = auto-detect or use first map in /Game/Maps)
        
    Returns:
        MoviePipelineExecutorJob or None if failed
    """
    unreal.log(f"[Rendering] 尝试加载序列: {sequence_path}")
    sequence = unreal.load_asset(sequence_path)
    if not sequence:
        unreal.log_error(f"[Rendering] 无法加载序列: {sequence_path}")
        # 列出该目录下所有 Level Sequence
        try:
            parent_dir = "/".join(sequence_path.split("/")[:-1])
            unreal.log_error(f"[Rendering] 列出目录: {parent_dir}")
            assets = unreal.EditorAssetLibrary.list_assets(parent_dir, recursive=False, include_folder=False)
            for asset_path in assets:
                asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
                if asset_data and asset_data.asset_class_path.asset_name == "LevelSequence":
                    unreal.log_error(f"[Rendering] 目录下存在序列: {asset_path}")
        except Exception as e:
            unreal.log_error(f"[Rendering] 列目录失败: {e}")
        return None
    
    unreal.log(f"[Rendering] 尝试加载配置: {config_path}")
    config = unreal.load_asset(config_path)
    if not config:
        unreal.log_error(f"[Rendering] 无法加载配置: {config_path}")
        return None
    log_output_settings(config, "Preset before job")
    
    # Determine map path
    if map_path:
        # Use specified map
        target_map = map_path
        unreal.log(f"[Rendering] 使用指定地图: {target_map}")
    else:
        # Try to get map from sequence's outer
        try:
            outer_path = sequence.get_outer().get_path_name()
            # Check if it's a valid world/map
            if "/Game/Maps" in outer_path or outer_path.startswith("/Game/") and "World" in str(type(sequence.get_outer())):
                target_map = outer_path
                unreal.log(f"[Rendering] 从序列检测到地图: {target_map}")
            else:
                raise Exception("Not a valid map path")
        except:
            # Fall back to first map in /Game/Maps
            import level_launcher
            maps = level_launcher.discover_map_assets()
            if maps:
                target_map = maps[0]
                unreal.log(f"[Rendering] 使用默认地图: {target_map}")
            else:
                unreal.log_error("[Rendering] 无法找到任何地图")
                return None
    
    # Create job
    job = unreal.MoviePipelineExecutorJob()
    job.sequence = unreal.SoftObjectPath(sequence_path)
    job.map = unreal.SoftObjectPath(target_map)
    job.job_name = sequence.get_name()
    
    # Set config
    job.set_configuration(config)
    log_output_settings(job.get_configuration(), "Job initial config")
    
    # 优化配置以防止内存泄漏
    optimize_render_config_for_memory(job.get_configuration())
    
    # Always check and set file name format in output settings
    settings = job.get_configuration().get_all_settings()
    
    # First, check if we have MP4 encoder
    has_mp4_encoder = False
    for setting in settings:
        if type(setting).__name__ == "MoviePipelineMP4EncoderOutput":
            has_mp4_encoder = True
            unreal.log("[Rendering] Detected MP4 encoder in pipeline")
            break
    
    for setting in settings:
        if isinstance(setting, unreal.MoviePipelineOutputSetting):
            # Set output directory if specified
            if output_directory:
                setting.output_directory = unreal.DirectoryPath(output_directory)
                unreal.log(f"[Rendering] Output directory set: {output_directory}")
            
            # Always ensure file name format is set
            current_format = getattr(setting, "file_name_format", "")
            unreal.log(f"[Rendering] Current file_name_format: '{current_format}'")
            
            if not current_format or current_format.strip() == "":
                setting.file_name_format = "{sequence_name}"
                unreal.log("[Rendering] ✓ File name format set to: {sequence_name}")
            else:
                unreal.log(f"[Rendering] File name format preserved: {current_format}")
            
            # Check file_name_format_overrides - this is where MP4 naming issues occur
            format_overrides = getattr(setting, "file_name_format_overrides", None)
            
            # CRITICAL FIX: Clear file_name_format_overrides if it exists
            # In UE5, empty overrides for MP4 cause the output file to have no name
            # The file_name_format itself should handle the naming, not the overrides
            if format_overrides:
                unreal.log_warning(f"[Rendering] Found file_name_format_overrides: {format_overrides}")
                unreal.log_warning("[Rendering] Clearing overrides to prevent MP4 naming issues")
                try:
                    # Try to clear the overrides map
                    if hasattr(setting, "set_editor_property"):
                        setting.set_editor_property("file_name_format_overrides", {})
                        unreal.log("[Rendering] ✓✓ FIXED: Cleared file_name_format_overrides")
                    else:
                        setting.file_name_format_overrides = {}
                        unreal.log("[Rendering] ✓✓ FIXED: Set file_name_format_overrides to empty dict")
                except Exception as e:
                    unreal.log_error(f"[Rendering] Failed to clear overrides: {e}")
            else:
                unreal.log("[Rendering] No file_name_format_overrides found (good)")
            
            ensure_unique = getattr(setting, "ensure_unique_filenames", None)
            unreal.log(f"[Rendering] Ensure unique filenames: {ensure_unique}")
            break
    
    unreal.log(f"[Rendering] 创建渲染任务: {job.job_name} -> {target_map}")
    log_output_settings(job.get_configuration(), "Job after adjustments")
    return job


def render_sequences_remote(
    sequence_paths: List[str],
    config_path: str = "/Game/CameraController/Pending_MoviePipelinePrimaryConfig",
    output_directory: Optional[str] = None,
    map_path: Optional[str] = None
) -> bool:
    """
    Render multiple level sequences using Movie Render Queue (Remote)
    
    Args:
        sequence_paths: List of level sequence asset paths to render
        config_path: Path to the Movie Pipeline config preset
        output_directory: Custom output directory (None = use project's default)
        map_path: Path to the map to use for all sequences (None = auto-detect)
        
    Returns:
        True if render queue started successfully
    """
    if not sequence_paths:
        unreal.log_warning("[Rendering] 没有序列需要渲染")
        return False
    
    # Get Movie Pipeline Queue Subsystem
    # Try multiple possible class names for different UE versions
    subsystem = None
    try:
        subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    except AttributeError:
        try:
            subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineEditorSubsystem)
        except AttributeError:
            try:
                subsystem_class = unreal.load_class(None, "/Script/MovieRenderPipelineCore.MoviePipelineQueueSubsystem")
                if subsystem_class:
                    subsystem = unreal.get_editor_subsystem(subsystem_class)
            except:
                pass
    
    if not subsystem:
        unreal.log_error("[Rendering] 无法获取 MoviePipelineQueueSubsystem")
        unreal.log_error("[Rendering] 确保 Movie Render Queue 插件已启用")
        return False
    
    # Get the queue
    queue = subsystem.get_queue()
    if not queue:
        unreal.log_error("[Rendering] 无法获取渲染队列")
        return False
    
    # Clear existing jobs
    queue.delete_all_jobs()
    unreal.log("[Rendering] 清空现有渲染队列")
    
    # Add jobs for each sequence
    for sequence_path in sequence_paths:
        job = create_render_job(sequence_path, config_path, output_directory, map_path)
        if job:
            queue.allocate_new_job(type(job))
            new_job = queue.get_jobs()[-1]
            new_job.sequence = job.sequence
            new_job.map = job.map
            new_job.job_name = job.job_name
            new_job.set_configuration(job.get_configuration())
            log_output_settings(new_job.get_configuration(), "Queue job config")
            unreal.log(f"[Rendering] ✓ 添加到队列: {job.job_name}")
        
        # 强制垃圾回收，释放临时对象
        gc.collect()
    
    # Check if we have jobs
    jobs = queue.get_jobs()
    if not jobs:
        unreal.log_error("[Rendering] 队列中没有有效任务")
        return False
    
    unreal.log(f"[Rendering] ========================================")
    unreal.log(f"[Rendering] 准备渲染 {len(jobs)} 个序列")
    unreal.log(f"[Rendering] 配置: {config_path}")
    if map_path:
        unreal.log(f"[Rendering] 使用地图: {map_path}")
    if output_directory:
        unreal.log(f"[Rendering] 输出目录: {output_directory}")
    unreal.log(f"[Rendering] ========================================")
    
    # Render using new process executor (true remote rendering)
    executor = subsystem.render_queue_with_executor(unreal.MoviePipelineNewProcessExecutor)
    if not executor:
        unreal.log_error("[Rendering] 无法启动渲染执行器")
        return False
    
    unreal.log("[Rendering] ▶ 开始远程渲染...")
    return True


def render_directory_remote(
    directory: str = "/Game/CameraController/2025-12-04",
    config_path: str = "/Game/CameraController/Pending_MoviePipelinePrimaryConfig",
    output_directory: Optional[str] = None,
    map_path: Optional[str] = None
) -> bool:
    """
    Discover and render all level sequences in a directory
    
    Args:
        directory: Directory containing level sequences
        config_path: Path to the Movie Pipeline config preset
        output_directory: Custom output directory (None = use default)
        map_path: Path to the map to use (None = use first map in /Game/Maps)
        
    Returns:
        True if render started successfully
    """
    unreal.log(f"[Rendering] 扫描目录: {directory}")
    
    # Discover sequences
    sequences = discover_level_sequences(directory)
    if not sequences:
        unreal.log_warning(f"[Rendering] 在 {directory} 中未找到任何序列")
        return False
    
    unreal.log(f"[Rendering] 找到 {len(sequences)} 个序列")
    
    # Render them
    return render_sequences_remote(sequences, config_path, output_directory, map_path)


# Convenience function for quick testing
def render_today_sequences(
    config_path: str = "/Game/CameraController/Pending_MoviePipelinePrimaryConfig",
    map_path: Optional[str] = None
) -> bool:
    """
    Render all sequences from today's date directory
    Uses format: /Game/CameraController/YYYY-MM-DD
    
    Args:
        config_path: Path to the Movie Pipeline config preset
        map_path: Path to the map to use (None = use first map in /Game/Maps)
    """
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    directory = f"/Game/CameraController/{today}"
    
    return render_directory_remote(directory, config_path, map_path=map_path)


# ==============================================================================
# Manifest-driven API
# ==============================================================================

def render_sequence_from_manifest(manifest: dict) -> dict:
    """
    Render sequence based on job manifest
    
    Args:
        manifest: job manifest dict containing:
            - sequence: sequence asset path
            - map: map asset path
            - render: render config with enabled, output_format, resolution, preset, output_path
            - frame_range: start_frame, end_frame (optional, uses sequence defaults if not specified)
    
    Returns:
        dict with render results
    """
    import unreal
    
    sequence_path = manifest.get("sequence")
    map_path = manifest.get("map")
    # Support both "rendering" (new format) and "render" (old format)
    render_config = manifest.get("rendering", manifest.get("render", {}))
    
    if not sequence_path:
        raise ValueError("Manifest missing 'sequence' field")
    
    if not render_config.get("enabled", True):
        unreal.log("[Rendering] Render disabled in manifest, skipping")
        return {"status": "skipped", "reason": "render disabled"}
    
    # Get render config
    config_path = render_config.get("preset", "/Game/CameraController/Pending_MoviePipelinePrimaryConfig")
    output_directory = render_config.get("output_path")
    
    if not output_directory:
        # Use job_utils to compute default path
        try:
            import job_utils
            paths = job_utils.get_output_paths(manifest)
            output_directory = paths.get("render_output_dir")
        except:
            pass
    
    unreal.log(f"[Rendering] Rendering sequence: {sequence_path}")
    unreal.log(f"[Rendering] Map: {map_path}")
    unreal.log(f"[Rendering] Config: {config_path}")
    unreal.log(f"[Rendering] Output: {output_directory}")
    
    # Ensure output directory exists and convert to absolute path
    if output_directory:
        import os
        # If relative path, make it relative to current working directory
        if not os.path.isabs(output_directory):
            abs_output = os.path.abspath(output_directory)
            unreal.log(f"[Rendering] Converting relative path to absolute: {abs_output}")
            output_directory = abs_output
        else:
            abs_output = output_directory
        
        try:
            os.makedirs(abs_output, exist_ok=True)
            unreal.log(f"[Rendering] Output directory ready: {abs_output}")
        except Exception as e:
            unreal.log_warning(f"[Rendering] Failed to create output directory: {e}")
    
    # Create render job
    job = create_render_job(
        sequence_path=sequence_path,
        config_path=config_path,
        output_directory=output_directory,
        map_path=map_path
    )
    
    if not job:
        raise RuntimeError(f"Failed to create render job for {sequence_path}")
    
    # Get Movie Pipeline Queue Subsystem
    # Try multiple possible class names for different UE versions
    subsystem = None
    try:
        subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    except AttributeError:
        try:
            # UE5 may use different class name
            subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineEditorSubsystem)
        except AttributeError:
            # Try loading by class path
            try:
                subsystem_class = unreal.load_class(None, "/Script/MovieRenderPipelineCore.MoviePipelineQueueSubsystem")
                if subsystem_class:
                    subsystem = unreal.get_editor_subsystem(subsystem_class)
            except:
                pass
    
    if not subsystem:
        unreal.log_error("[Rendering] Cannot get MoviePipelineQueueSubsystem")
        unreal.log_error("[Rendering] Make sure Movie Render Queue plugin is enabled")
        raise RuntimeError("Cannot get MoviePipelineQueueSubsystem - check if Movie Render Queue plugin is enabled")
    
    # Get queue and add job
    queue = subsystem.get_queue()
    # Clear existing jobs and add ours
    queue.delete_all_jobs()
    
    # 强制垃圾回收
    gc.collect()
    
    new_job = queue.allocate_new_job(type(job))
    new_job.sequence = job.sequence
    new_job.map = job.map
    new_job.job_name = job.job_name
    new_job.set_configuration(job.get_configuration())
    log_output_settings(new_job.get_configuration(), "Queue job config (manifest)")
    
    unreal.log(f"[Rendering] Job added to queue: {job.job_name}")
    
    # 最终垃圾回收
    gc.collect()
    
    # Start render with remote executor
    unreal.log(f"[Rendering] Job added to queue: {job.job_name}")
    
    # Start render with remote executor
    executor = subsystem.render_queue_with_executor(unreal.MoviePipelineNewProcessExecutor)
    if not executor:
        raise RuntimeError("Failed to start render executor")
    
    unreal.log("[Rendering] ▶ Render started")
    
    return {
        "status": "started",
        "sequence": sequence_path,
        "job_name": job.job_name,
        "output_directory": output_directory
    }


if __name__ == "__main__":
    # Example usage - render sequences from specific directory
    # Will use first map in /Game/Maps if map_path not specified
    render_directory_remote(
        directory="/Game/CameraController/2025-12-04",
        config_path="/Game/CameraController/Pending_MoviePipelinePrimaryConfig",
        map_path=None  # Set to specific map path if needed, e.g., "/Game/Maps/YourMap"
    )

