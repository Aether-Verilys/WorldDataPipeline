import unreal
from typing import List, Optional, Dict, Any
import gc
import os
import json

def discover_level_sequences(directory: str) -> List[str]:
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
        
        if isinstance(setting, unreal.MoviePipelineDeferredPassBase):
            # 禁用不必要的渲染通道
            if hasattr(setting, 'disable_multisample_effects'):
                setting.disable_multisample_effects = True
                unreal.log("[Rendering] 禁用多重采样效果以节省内存")
        
        if isinstance(setting, unreal.MoviePipelineOutputSetting):
            # 确保每帧后刷新磁盘缓存
            if hasattr(setting, 'flush_disk_writes_per_shot'):
                setting.flush_disk_writes_per_shot = True
                unreal.log("[Rendering] 启用每镜头刷新磁盘写入")


def log_output_settings(config: unreal.MoviePipelinePrimaryConfig, context: str) -> None:
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


def find_map_path_from_sequence_name(sequence_name: str, ue_config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    根据序列名称从ue_config中查找匹配的地图路径
    
    Args:
        sequence_name: 序列名称，如 "Lvl_FirstPerson_001"
        ue_config: UE配置字典，如果为None则尝试从默认路径加载
    
    Returns:
        匹配的地图路径，如 "/Game/S0001/LevelPrototyping/Lvl_FirstPerson"
    """
    if not sequence_name:
        return None
    
    # 从序列名称中提取前缀（去掉数字后缀）
    # 例如: "Lvl_FirstPerson_001" -> "Lvl_FirstPerson"
    import re
    # 移除末尾的数字后缀 (如 _001, _01, 或纯数字)
    map_name_pattern = re.sub(r'[_-]?\d+$', '', sequence_name)
    
    unreal.log(f"[Rendering] 从序列名称 '{sequence_name}' 提取地图前缀: '{map_name_pattern}'")
    
    # 如果没有提供ue_config，尝试加载默认配置
    if ue_config is None:
        # 尝试从常见位置加载ue_config.json
        # 获取当前脚本所在目录的父目录（ue_pipeline）
        current_file = os.path.abspath(__file__)
        python_dir = os.path.dirname(current_file)
        ue_pipeline_dir = os.path.dirname(python_dir)
        
        config_paths = [
            os.path.join(ue_pipeline_dir, "config", "ue_config.json"),
            os.path.join(os.getcwd(), "ue_pipeline", "config", "ue_config.json"),
            os.path.join(os.getcwd(), "config", "ue_config.json"),
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        ue_config = json.load(f)
                    unreal.log(f"[Rendering] 加载配置文件: {config_path}")
                    break
                except Exception as e:
                    unreal.log_warning(f"[Rendering] 无法加载配置 {config_path}: {e}")
        
        if ue_config:
            unreal.log(f"[Rendering] 成功加载ue_config，包含 {len(ue_config.get('scenes', []))} 个场景")
        else:
            unreal.log_warning("[Rendering] 所有配置路径均未找到ue_config.json")
            for path in config_paths:
                unreal.log_warning(f"[Rendering]   尝试: {path} - 存在: {os.path.exists(path)}")
    
    if not ue_config:
        unreal.log_warning("[Rendering] 无法加载ue_config，无法自动检测地图")
        return None
    
    # 在所有scene的maps中查找匹配的地图
    scenes = ue_config.get("scenes", [])
    for scene in scenes:
        maps = scene.get("maps", [])
        for map_info in maps:
            map_name = map_info.get("name", "")
            map_path = map_info.get("path", "")
            
            # 检查地图名称是否匹配序列前缀
            if map_name == map_name_pattern or map_name_pattern.startswith(map_name):
                unreal.log(f"[Rendering] 找到匹配地图: {map_name} -> {map_path}")
                return map_path
    
    unreal.log_warning(f"[Rendering] 在ue_config中未找到匹配 '{map_name_pattern}' 的地图")
    return None


def create_render_job(
    sequence_path: str,
    config_path: str,
    output_directory: Optional[str] = None,
    map_path: Optional[str] = None,
    ue_config: Optional[Dict[str, Any]] = None,
    frame_range: Optional[Dict[str, int]] = None
) -> Optional[unreal.MoviePipelineExecutorJob]:
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
    
    # Extract sequence name from path (last part after /)
    sequence_name = sequence_path.split("/")[-1]
    unreal.log(f"[Rendering] 提取序列名称: {sequence_name}")
    
    unreal.log(f"[Rendering] 尝试加载配置: {config_path}")
    config = unreal.load_asset(config_path)
    if not config:
        unreal.log_error(f"[Rendering] 无法加载配置: {config_path}")
        return None
    log_output_settings(config, "Preset before job")
    
    if map_path:
        target_map = map_path
        unreal.log(f"[Rendering] 使用指定地图: {target_map}")
    else:
        # 先尝试从序列的outer获取地图
        try:
            outer_path = sequence.get_outer().get_path_name()
            # Check if it's a valid world/map
            if outer_path.startswith("/Game/") and "World" in str(type(sequence.get_outer())):
                target_map = outer_path
                unreal.log(f"[Rendering] 从序列检测到地图: {target_map}")
            else:
                raise Exception("Not a valid map path")
        except Exception as e:
            unreal.log(f"[Rendering] 无法从序列outer获取地图: {e}")
            
            # 尝试根据序列名称从ue_config中查找地图
            detected_map = find_map_path_from_sequence_name(sequence_name, ue_config)
            if detected_map:
                target_map = detected_map
                unreal.log(f"[Rendering] 从ue_config检测到地图: {target_map}")
            else:
                unreal.log_error("[Rendering] 无法确定地图路径")
                unreal.log_error("[Rendering] 请在job配置中明确指定map_path参数，或确保ue_config.json中包含对应的地图配置")
                return None
    
    # Create job
    job = unreal.MoviePipelineExecutorJob()
    job.sequence = unreal.SoftObjectPath(sequence_path)
    job.map = unreal.SoftObjectPath(target_map)
    job.job_name = sequence_name  # Use extracted sequence name
    
    job.set_configuration(config)
    log_output_settings(job.get_configuration(), "Job initial config")
    
    # 应用自定义帧范围覆盖
    if frame_range:
        start_frame = frame_range.get("start_frame", 0)
        end_frame = frame_range.get("end_frame", 0)
        if end_frame >= 0:  # Allow 0 as valid end frame
            unreal.log(f"[Rendering] 应用帧范围覆盖: {start_frame} - {end_frame}")
            
            # MoviePipeline 的正确方法是通过 shot_info 设置自定义帧范围
            # 首先获取或创建 shot_info 列表
            try:
                shot_list = job.shot_info
                if not shot_list or len(shot_list) == 0:
                    # 如果没有 shot，创建一个默认的
                    shot = unreal.MoviePipelineExecutorShot()
                    job.shot_info = [shot]
                    shot_list = job.shot_info
                    unreal.log("[Rendering] 创建默认 shot")
                
                # 对每个 shot 设置自定义帧范围
                for shot in shot_list:
                    shot.enabled = True
                    # 使用 bUseCustomPlaybackRange 启用自定义范围
                    try:
                        shot.set_editor_property("bUseCustomPlaybackRange", True)
                        shot.set_editor_property("CustomStartFrame", start_frame)
                        shot.set_editor_property("CustomEndFrame", end_frame)
                        unreal.log(f"[Rendering] ✓ Shot '{shot.outer_name}' 设置帧范围: {start_frame} - {end_frame}")
                    except AttributeError:
                        # 尝试其他可能的属性名
                        try:
                            shot.b_use_custom_playback_range = True
                            shot.custom_start_frame = start_frame
                            shot.custom_end_frame = end_frame
                            unreal.log(f"[Rendering] ✓ Shot 设置帧范围 (属性方式): {start_frame} - {end_frame}")
                        except Exception as e2:
                            unreal.log_warning(f"[Rendering] 无法设置 shot 帧范围: {e2}")
            except Exception as e:
                unreal.log_error(f"[Rendering] 设置帧范围失败: {e}")
                # 尝试备用方法：通过控制台变量
                try:
                    job_config = job.get_configuration()
                    # 查找或添加 Console Variable Setting
                    console_var_setting = None
                    for setting in job_config.get_all_settings():
                        if isinstance(setting, unreal.MoviePipelineConsoleVariableSetting):
                            console_var_setting = setting
                            break
                    
                    if not console_var_setting:
                        console_var_setting = job_config.find_or_add_setting_by_class(
                            unreal.MoviePipelineConsoleVariableSetting
                        )
                    
                    if console_var_setting:
                        # 注意：这种方法可能不是所有版本都支持
                        unreal.log("[Rendering] 使用控制台变量作为备用方案")
                except Exception as e3:
                    unreal.log_warning(f"[Rendering] 备用方案也失败: {e3}")
        else:
            unreal.log_warning(f"[Rendering] 帧范围无效: start={start_frame}, end={end_frame}")
    
    # 优化配置以防止内存泄漏 todo 暂时关闭
    # optimize_render_config_for_memory(job.get_configuration())
    
    settings = job.get_configuration().get_all_settings()
    
    for setting in settings:
        if isinstance(setting, unreal.MoviePipelineOutputSetting):
            if output_directory:
                # Output directory already includes the sequence name from caller
                # No need to add sequence_name subfolder again
                # Ensure absolute path and normalize separators
                import os
                abs_output = os.path.abspath(output_directory)
                # Convert to forward slashes for UE compatibility
                abs_output_normalized = abs_output.replace('\\', '/')
                setting.output_directory = unreal.DirectoryPath(abs_output_normalized)
                unreal.log(f"[Rendering] Output directory set (absolute): {abs_output_normalized}")
                
                # Verify the path was set correctly
                try:
                    set_path = setting.output_directory.path
                    unreal.log(f"[Rendering] Verified output_directory.path = '{set_path}'")
                    if not set_path or set_path.strip() == "":
                        unreal.log_error("[Rendering] WARNING: output_directory.path is empty!")
                except Exception as e:
                    unreal.log_warning(f"[Rendering] Could not verify output path: {e}")
            
            # Always ensure file name format includes sequence name and frame number
            current_format = getattr(setting, "file_name_format", "")
            unreal.log(f"[Rendering] Current file_name_format: '{current_format}'")
            
            # Format: {sequence_name}.{frame_number} -> e.g., Scene_1_02.0001.png
            setting.file_name_format = f"{sequence_name}.{{frame_number}}"
            unreal.log(f"[Rendering] File name format set to: {sequence_name}.{{frame_number}}")
            
            try:
                if hasattr(setting, "set_editor_property"):
                    setting.set_editor_property("file_name_format", f"{sequence_name}.{{frame_number}}")
                    unreal.log(f"[Rendering] Set file_name_format via editor property")
            except Exception as e:
                unreal.log_warning(f"[Rendering] Could not set via editor property: {e}")
            
            # Final verification of all output settings
            unreal.log("[Rendering] ========== Final Output Settings ==========")
            try:
                final_dir = setting.output_directory.path if hasattr(setting.output_directory, 'path') else str(setting.output_directory)
                unreal.log(f"[Rendering] Final output_directory: '{final_dir}'")
                unreal.log(f"[Rendering] Final file_name_format: '{setting.file_name_format}'")
                unreal.log(f"[Rendering] Final output_file_extension: '{getattr(setting, 'output_file_extension', 'N/A')}'")
            except Exception as e:
                unreal.log_error(f"[Rendering] Error verifying final settings: {e}")
            unreal.log("[Rendering] ===========================================")
            
            break
    
    unreal.log(f"[Rendering] 创建渲染任务: {job.job_name} -> {target_map}")
    log_output_settings(job.get_configuration(), "Job after adjustments")
    return job


def render_sequences_remote(
    sequence_paths: List[str],
    config_path: str,
    output_directory: Optional[str] = None,
    map_path: Optional[str] = None
) -> bool:
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
            unreal.log(f"[Rendering] 添加到队列: {job.job_name}")
        
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
    
    unreal.log("[Rendering] 开始渲染...")
    return True


def render_directory_remote(
    directory: str,
    config_path: str,
    output_directory: Optional[str] = None,
    map_path: Optional[str] = None
) -> bool:
    sequences = discover_level_sequences(directory)
    if not sequences:
        unreal.log_warning(f"[Rendering] 在 {directory} 中未找到任何序列")
        return False
    
    unreal.log(f"[Rendering] 找到 {len(sequences)} 个序列")
    
    return render_sequences_remote(sequences, config_path, output_directory, map_path)


# Manifest-driven API
def render_sequence_from_manifest(manifest: dict) -> dict:
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
    config_path = render_config.get("preset")
    if not config_path:
        raise ValueError("Manifest missing 'preset' in rendering config")
    base_output_path = render_config.get("output_path")
    
    # Get frame range from rendering config
    frame_range = render_config.get("frame_range")
    if frame_range:
        unreal.log(f"[Rendering] 从配置中读取帧范围: {frame_range.get('start_frame', 0)} - {frame_range.get('end_frame', 0)}")
    
    # Build output path: base_path/scene_id/map_name/sequence_name
    output_directory = base_output_path
    
    # 获取ue_config用于地图检测和场景查找
    ue_config = manifest.get("ue_config", {})
    
    if base_output_path:
        # Extract scene ID and map name from map_path
        # Map path format: /Game/S0001/LevelPrototyping/Lvl_FirstPerson
        scene_id = "UnknownScene"
        map_name = "UnknownMap"
        
        if map_path:
            # Extract map name (last part)
            map_name = map_path.split("/")[-1]
            
            # Extract scene ID from map path (e.g., S0001 from /Game/S0001/...)
            path_parts = map_path.split("/")
            if len(path_parts) > 2:
                # Try to find scene ID in path (format: S####)
                import re
                for part in path_parts:
                    if re.match(r'^S\d{4}$', part):
                        scene_id = part
                        break
            
            # If no scene ID found in path, try to lookup from ue_config
            if scene_id == "UnknownScene":
                scenes = ue_config.get("scenes", [])
                for scene in scenes:
                    maps = scene.get("maps", [])
                    for map_info in maps:
                        if map_info.get("path") == map_path:
                            scene_id = scene.get("id", "UnknownScene")
                            break
                    if scene_id != "UnknownScene":
                        break
        
        # Extract sequence name from sequence_path
        # Sequence path format: /Game/CameraController/Generated/Lvl_FirstPerson_001
        sequence_name = sequence_path.split("/")[-1] if sequence_path else "UnknownSequence"
        
        # Construct full output path: base/scene_id/map_name/sequence_name
        output_directory = os.path.join(base_output_path, scene_id, map_name, sequence_name)
        # Convert to absolute path immediately
        output_directory = os.path.abspath(output_directory)
        # Normalize path separators for UE (use forward slashes)
        output_directory = output_directory.replace('\\', '/')
        unreal.log(f"[Rendering] Scene ID: {scene_id}")
        unreal.log(f"[Rendering] Map name: {map_name}")
        unreal.log(f"[Rendering] Sequence name: {sequence_name}")
        unreal.log(f"[Rendering] Constructed absolute output path: {output_directory}")
    
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
    
    # Ensure output directory exists and is absolute path
    if output_directory:
        # Always ensure absolute path (even if already absolute, normalize it)
        abs_output = os.path.abspath(output_directory)
        # Normalize to forward slashes for UE
        abs_output = abs_output.replace('\\', '/')
        output_directory = abs_output
        unreal.log(f"[Rendering] Final absolute output path: {abs_output}")
        
        # Create directory structure (use original format for os.makedirs)
        abs_output_for_mkdir = abs_output.replace('/', os.sep)
        try:
            os.makedirs(abs_output_for_mkdir, exist_ok=True)
            unreal.log(f"[Rendering] Output directory created/verified: {abs_output}")
        except Exception as e:
            unreal.log_error(f"[Rendering] Failed to create output directory: {e}")
    
    # Create render job
    job = create_render_job(
        sequence_path=sequence_path,
        config_path=config_path,
        output_directory=output_directory,
        map_path=map_path,
        ue_config=ue_config,
        frame_range=frame_range
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
    
    queue = subsystem.get_queue()
    queue.delete_all_jobs()
    
    gc.collect()
    
    new_job = queue.allocate_new_job(type(job))
    new_job.sequence = job.sequence
    new_job.map = job.map
    new_job.job_name = job.job_name
    new_job.set_configuration(job.get_configuration())
    log_output_settings(new_job.get_configuration(), "Queue job config (manifest)")
    
    unreal.log(f"[Rendering] Job added to queue: {job.job_name}")
    
    gc.collect()
    
    unreal.log(f"[Rendering] Job added to queue: {job.job_name}")
    
    # Create render status tracking file
    status_file = None
    if output_directory:
        try:
            abs_output_for_mkdir = output_directory.replace('/', os.sep)
            status_file = os.path.join(abs_output_for_mkdir, ".render_status.json")
            status_data = {
                "status": "rendering",
                "sequence": sequence_path,
                "job_name": job.job_name,
                "output_directory": output_directory,
                "start_time": str(unreal.DateTime.now())
            }
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, indent=2)
            unreal.log(f"[Rendering] Created status file: {status_file}")
        except Exception as e:
            unreal.log_warning(f"[Rendering] Failed to create status file: {e}")
            status_file = None
    
    # Start render with remote executor
    executor = subsystem.render_queue_with_executor(unreal.MoviePipelineNewProcessExecutor)
    if not executor:
        raise RuntimeError("Failed to start render executor")
    
    unreal.log("[Rendering] Render started")
    
    # Setup executor callbacks to update status file
    if status_file and executor:
        try:
            # Register callback for when rendering finishes
            def on_render_finished(executor_instance, success):
                try:
                    status = "completed" if success else "failed"
                    status_data = {
                        "status": status,
                        "sequence": sequence_path,
                        "job_name": job.job_name,
                        "output_directory": output_directory,
                        "start_time": str(unreal.DateTime.now()),
                        "end_time": str(unreal.DateTime.now()),
                        "success": success
                    }
                    with open(status_file, 'w', encoding='utf-8') as f:
                        json.dump(status_data, f, indent=2)
                    unreal.log(f"[Rendering] Updated status to '{status}': {status_file}")
                except Exception as e:
                    unreal.log_error(f"[Rendering] Failed to update status file: {e}")
            
            # Try to bind to executor's finished event if available
            if hasattr(executor, 'on_executor_finished_delegate'):
                executor.on_executor_finished_delegate.add_callable(on_render_finished)
                unreal.log("[Rendering] Registered render completion callback")
        except Exception as e:
            unreal.log_warning(f"[Rendering] Could not register completion callback: {e}")
    
    return {
        "status": "started",
        "sequence": sequence_path,
        "job_name": job.job_name,
        "output_directory": output_directory,
        "status_file": status_file
    }


if __name__ == "__main__":
    pass

