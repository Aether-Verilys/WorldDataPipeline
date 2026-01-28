import math
import os
import random
import sys
import traceback
from typing import Any, Dict, List, Optional

# Add repo root to sys.path for package imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
_python_dir = os.path.dirname(_script_dir)  # ue_pipeline/python
_ue_pipeline_dir = os.path.dirname(_python_dir)  # ue_pipeline
_repo_root = os.path.dirname(_ue_pipeline_dir)  # WorldDataPipeline

if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import unreal

# Use absolute imports for UE Python environment compatibility
from ue_pipeline.python.core import logger, get_editor_world, load_map, load_blueprint_class, validate_prerequisites, job_utils
from ue_pipeline.python.assets import ensure_directory_exists, create_level_sequence, save_asset
from ue_pipeline.python.export import camera_exporter

from ue_pipeline.python.sequence.camera.camera_bindings import (
    add_camera_cuts,
    ensure_actor_binding,
)
from ue_pipeline.python.sequence.navigation.nav_utils import (
    distance_cm,
    get_nav_system,
    resample_by_count,
    wait_for_navigation_ready,
)
from ue_pipeline.python.sequence.behavior.behavior_executor import generate_behavior_sequence
from ue_pipeline.python.sequence.navigation.navmesh_connectivity import get_spawn_point_with_connectivity
from ue_pipeline.python.sequence.keyframe.transform_track import (
    calculate_pitch_from_slope,
    sanitize_rotation_keys,
    write_transform_keys,
    yaw_degrees_xy,
)
from ue_pipeline.python.sequence.sequence_types import (
    FixedSpeedResult,
    KeyGenResult,
    SampleResult,
    SequenceJobConfig,
)
from ue_pipeline.python.sequence.sequence_config import (
    GenerationContext,
    TimingConfig,
    CameraConfig,
    PathConfig,
    ExportConfig,
)



def generate_all_sequences(
    *,
    batch_count: int,
    start_index: int,
    map_path: str,
    output_dir: str,
    actor_blueprint_class_path: str,
    nav_roam_cfg: Dict[str, Any],
    max_yaw_rate_deg_per_sec: Optional[float],
    base_transform_key_interp: str,
    sequence_config: Dict[str, Any],
    camera_export_cfg: Optional[Dict[str, Any]],
    ue_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    completed_sequences = []
    
    # Derive map_name from map_path
    map_name = job_utils.extract_map_name(map_path)

    world, nav = _prepare_sequence_generation_run(
        map_path=map_path,
        actor_blueprint_class_path=actor_blueprint_class_path,
        output_dir=output_dir,
        nav_roam_cfg=nav_roam_cfg,
    )

    # Normalize config once  
    seq_cfg = sequence_config or {}
    roam_cfg = nav_roam_cfg or {}
    
    # Pre-compute connectivity analysis ONCE before batch loop
    # Cache will be reused for all sequences in this batch run
    use_connectivity_analysis = bool(roam_cfg.get("use_connectivity_analysis", True))
    if use_connectivity_analysis:
        logger.info("========================================")
        logger.info("PRE-COMPUTING CONNECTIVITY ANALYSIS")
        logger.info("========================================")
        try:
            origin = get_spawn_point_with_connectivity(nav, world, map_path, roam_cfg)
            logger.info(f"✓ Connectivity analysis completed, spawn point: ({origin.x:.2f}, {origin.y:.2f}, {origin.z:.2f})")
            logger.info("Cache will be reused for all sequences in this batch run")
        except Exception as e:
            logger.warning(f"Connectivity analysis pre-computation failed: {e}")
        logger.info("========================================")

    fps = int(seq_cfg.get("fps", 30))
    base_duration_seconds = float(seq_cfg.get("duration_seconds", 60.0))
    fixed_speed_cfg = seq_cfg.get("fixed_speed_cm_per_sec", None)
    strict_duration = bool(seq_cfg.get("strict_duration", False))

    camera_pitch_from_slope = bool(seq_cfg.get("camera_pitch_from_slope", False))
    max_pitch_rate = float(seq_cfg.get("max_pitch_rate_deg_per_sec", 20.0))
    
    # Get pitch range from nav_roam config (used for rotate behavior and pitch clamping)
    pitch_range_config = roam_cfg.get("rotate_pitch_target_range", [-20, 20])
    pitch_range = (float(pitch_range_config[0]), float(pitch_range_config[1]))

    z_offset_cm = float(roam_cfg.get("z_offset_cm", 0.0))

    # Create independent configuration objects
    context = GenerationContext(
        nav=nav,
        world=world,
        map_path=map_path,
        map_name=map_name,
        output_dir=output_dir,
        actor_blueprint_class_path=actor_blueprint_class_path,
    )
    
    timing = TimingConfig(
        fps=fps,
        base_duration_seconds=base_duration_seconds,
        fixed_speed_cfg=fixed_speed_cfg,
        strict_duration=strict_duration,
    )
    
    camera = CameraConfig(
        camera_pitch_from_slope=camera_pitch_from_slope,
        max_camera_pitch=pitch_range[1],  # Use max value from pitch_range for backward compatibility
        max_pitch_rate=max_pitch_rate,
        max_yaw_rate_deg_per_sec=max_yaw_rate_deg_per_sec,
    )
    
    path = PathConfig(
        roam_cfg=roam_cfg,
        seq_cfg=seq_cfg,
        z_offset_cm=z_offset_cm,
        base_transform_key_interp=base_transform_key_interp,
    )
    
    export = ExportConfig(
        camera_export_cfg=camera_export_cfg,
        ue_config=ue_config,
    )

    for batch_idx in range(batch_count):
        try:
            sequence_info = _generate_single_sequence(
                batch_idx=batch_idx,
                batch_count=batch_count,
                start_index=start_index,
                context=context,
                timing=timing,
                camera=camera,
                path=path,
                export=export,
                pitch_range=pitch_range,
            )
            completed_sequences.append(sequence_info)
        except Exception as e:
            logger.error(f"in batch {batch_idx + 1}: {e}")
            traceback.print_exc()
            continue
    
    return completed_sequences


def _find_existing_max_index(output_dir: str, map_name: str) -> int:
    """Find existing max sequence index in output dir for naming continuity."""
    existing_max_index = 0
    try:
        if unreal.EditorAssetLibrary.does_directory_exist(output_dir):
            assets = unreal.EditorAssetLibrary.list_assets(output_dir, recursive=False, include_folder=False)
            for asset_path in assets:
                asset_name = asset_path.split("/")[-1].split(".")[0]
                if asset_name.startswith(f"{map_name}_"):
                    suffix = asset_name[len(map_name) + 1 :]
                    try:
                        index = int(suffix)
                        if index > existing_max_index:
                            existing_max_index = index
                    except ValueError:
                        pass
    except Exception as e:
        logger.warning(f"Failed to check existing sequences: {e}")
        return 0
    return existing_max_index


def _prepare_sequence_generation_run(
    *,
    map_path: str,
    actor_blueprint_class_path: str,
    output_dir: str,
    nav_roam_cfg: Dict[str, Any],
) -> tuple[Any, Any]:
    validate_prerequisites(map_path, actor_blueprint_class_path, True, "[WorkerCreateSequence]")

    # Load map first (important for level possessables, and avoids world switching mid-script)
    if map_path:
        try:
            load_map(map_path)
        except Exception as e:
            logger.error(f"Map load failed: {e}")
            raise

    ensure_directory_exists(output_dir)

    world = get_editor_world()
    nav = get_nav_system(world)
    wait_for_navigation_ready(nav, world, float(nav_roam_cfg.get("nav_build_wait_seconds", 10.0)))
    return world, nav


def _build_nav_points_with_retry(
    *,
    nav: Any,
    world: Any,
    roam_cfg: Dict[str, Any],
    map_path: str,
    parent_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate navigation points using behavior-based execution.
    
    Returns:
        Dict with keys: points, yaws, seed
    """
    def _cfg_for_seed(seed: Optional[int]) -> Dict[str, Any]:
        cfg = dict(roam_cfg)
        if seed is not None:
            cfg["seed"] = int(seed)
        # Inject parent config for duration-based path generation
        if parent_config:
            cfg["_parent_config"] = parent_config
        return cfg

    # Prepare configuration
    seed_cfg = roam_cfg.get("seed", None)
    actual_seed: Optional[int] = None
    if seed_cfg is not None:
        try:
            seed_val = int(seed_cfg)
            if seed_val == -1:
                random.seed()
                actual_seed = random.randint(0, 999999)
                logger.info(f"Using random seed: {actual_seed}")
            else:
                actual_seed = seed_val
                logger.info(f"Using configured seed: {actual_seed}")
        except Exception as e:
            logger.warning(f"Failed to set seed: {e}")

    nav_roam_cfg_for_path = _cfg_for_seed(actual_seed)

    # Generate behavior-based path
    try:
        result = generate_behavior_sequence(
            nav, world, nav_roam_cfg_for_path, map_path
        )
        
        nav_points = result["points"]
        yaws = result["yaws"]
        pitches = result["pitches"]
        returned_seed = result["seed"]
        behavior_segments = result.get("behavior_segments", [])
        
        if len(nav_points) < 2:
            raise RuntimeError(f"Behavior sequence produced too few points ({len(nav_points)})")
        
        # Return extended result with yaws, pitches and behavior segments
        return {
            "points": nav_points,
            "yaws": yaws,
            "pitches": pitches,
            "seed": returned_seed,
            "behavior_segments": behavior_segments,
        }
    
    except Exception as e:
        logger.error(f"Behavior sequence generation failed: {e}")
        raise


def _generate_single_sequence(
    *,
    batch_idx: int,
    batch_count: int,
    start_index: int,
    context: GenerationContext,
    timing: TimingConfig,
    camera: CameraConfig,
    path: PathConfig,
    export: ExportConfig,
    pitch_range: tuple,
) -> Dict[str, Any]:
    """Generate a single sequence with all required setup and configuration.
    
    Args:
        batch_idx: Current batch index (0-based).
        batch_count: Total number of sequences to generate.
        start_index: Starting index for sequence naming.
        context: Generation context (nav, world, paths).
        timing: Timing and speed configuration.
        camera: Camera behavior configuration.
        path: Path generation and interpolation configuration.
        export: Camera export configuration.
    
    Returns:
        Dictionary with sequence info (name, path, seed).
    """
    logger.info("========================================")
    logger.info(f"Generating sequence {batch_idx + 1}/{batch_count}")
    logger.info("========================================")
    
    # Step 1: Create sequence asset
    sequence_number = start_index + batch_idx + 1
    sequence_name = f"{context.map_name}_{sequence_number:03d}"
    
    sequence = create_level_sequence(sequence_name, context.output_dir)
    if not sequence:
        raise RuntimeError("Failed to create LevelSequence asset")
    asset_path = sequence.get_path_name()
    
    # Step 2: Initialize playback settings
    duration_seconds = timing.base_duration_seconds
    total_frames = int(timing.fps * duration_seconds)
    
    try:
        sequence.set_playback_start(0)
        sequence.set_playback_end(total_frames)
        logger.info(f"Set initial playback range: 0-{total_frames} frames ({duration_seconds:.2f}s @ {timing.fps} fps)")
    except Exception as e:
        logger.warning(f"Could not set initial playback range: {e}")
    
    # Step 3: Generate navigation path
    nav_result = _generate_navigation_path(
        nav=context.nav,
        world=context.world,
        roam_cfg=path.roam_cfg,
        map_path=context.map_path,
        seq_cfg=path.seq_cfg,
    )
    nav_points = nav_result["points"]
    nav_yaws = nav_result["yaws"]
    nav_pitches = nav_result["pitches"]
    actual_seed = nav_result["seed"]
    behavior_segments = nav_result.get("behavior_segments", [])
    
    # Step 4: Apply speed configuration and resample path
    fixed_result = _apply_fixed_speed_if_configured(
        nav_points=nav_points,
        fps=timing.fps,
        duration_seconds=duration_seconds,
        total_frames=total_frames,
        sequence=sequence,
        fixed_speed_cfg=timing.fixed_speed_cfg,
        strict_duration=timing.strict_duration,
    )
    
    # Adjust behavior_segments if path was truncated in strict duration mode
    if behavior_segments:
        original_count = len(nav_points)
        truncated_count = len(fixed_result.nav_points)
        
        if truncated_count < original_count:
            logger.info(f"  Adjusting behavior_segments after truncation ({original_count} → {truncated_count} points)")
            behavior_segments = _adjust_behavior_segments_after_truncation(
                behavior_segments=behavior_segments,
                original_point_count=original_count,
                truncated_point_count=truncated_count,
            )
            logger.info(f"  Retained {len(behavior_segments)} behavior segments after adjustment")
    
    # Step 5: Behavior-aware resampling
    if behavior_segments:
        # Use behavior-aware resampling that respects idle/rotate/translate constraints
        resampled_points, resampled_yaws, resampled_pitches, key_interval_frames = _resample_behavior_aware(
            nav_points=fixed_result.nav_points,
            nav_yaws=nav_yaws,
            nav_pitches=nav_pitches,
            behavior_segments=behavior_segments,
            fps=timing.fps,
            total_frames=fixed_result.total_frames,
            z_offset_cm=path.z_offset_cm,
        )
        sample_result = SampleResult(samples=resampled_points, key_interval_frames=key_interval_frames)
    else:
        # Fallback to standard resampling
        sample_result = _resample_nav_points(
            nav_points=fixed_result.nav_points,
            fps=timing.fps,
            total_frames=fixed_result.total_frames,
            z_offset_cm=path.z_offset_cm,
        )
        # Map original yaws and pitches to resampled points by index ratio
        resampled_yaws = []
        resampled_pitches = []
        for i in range(len(sample_result.samples)):
            ratio = i / max(1, len(sample_result.samples) - 1)
            orig_idx = min(int(ratio * (len(nav_yaws) - 1)), len(nav_yaws) - 1)
            resampled_yaws.append(nav_yaws[orig_idx])
            resampled_pitches.append(nav_pitches[orig_idx] if orig_idx < len(nav_pitches) else 0.0)
    
    # Step 6: Determine interpolation mode
    transform_key_interp = str(path.base_transform_key_interp or "auto").lower()
    
    if camera.camera_pitch_from_slope:
        logger.info(f"Camera pitch from slope enabled (max pitch: {camera.max_camera_pitch:.1f}°)")
    
    # Step 7: Build transform keys from samples
    key_result = _build_transform_keys_from_samples(
        samples=sample_result.samples,
        fps=timing.fps,
        total_frames=fixed_result.total_frames,
        key_interval_frames=sample_result.key_interval_frames,
        camera_pitch_from_slope=camera.camera_pitch_from_slope,
        pitch_range=pitch_range,
        precomputed_yaws=resampled_yaws,
        precomputed_pitches=resampled_pitches,
        behavior_segments=behavior_segments,
    )
    logger.info(f"NavRoam generated {len(key_result.transform_keys)} keys")
    
    # Step 8: Setup actor binding and tracks
    actor_binding = ensure_actor_binding(
        sequence=sequence,
        actor_blueprint_class_path=context.actor_blueprint_class_path,
        load_blueprint_class_fn=load_blueprint_class,
    )
    
    add_camera_cuts(
        sequence=sequence,
        actor_binding=actor_binding,
        total_frames=fixed_result.total_frames,
    )
    
    # Write transform keys
    if not actor_binding:
        logger.warning("No actor binding was created")
    else:
        logger.info("Adding transform keys to actor binding...")
        try:
            # Determine if we should preserve pitch (either from slope or from rotate behavior)
            has_rotate_behavior = any(seg.get("type") == "rotate" for seg in behavior_segments) if behavior_segments else False
            should_preserve_pitch = camera.camera_pitch_from_slope or has_rotate_behavior
            
            # Sanitize rotation keys (normalize angles, clamp rates)
            sanitize_rotation_keys(
                key_result.transform_keys,
                zero_pitch_roll=not should_preserve_pitch,  # Only zero pitch if we're not preserving it
                max_yaw_rate_deg_per_sec=camera.max_yaw_rate_deg_per_sec,
                preserve_pitch=should_preserve_pitch,
                max_pitch_rate_deg_per_sec=camera.max_pitch_rate,
                pitch_range=pitch_range,
            )
            write_transform_keys(
                actor_binding, 
                int(timing.fps), 
                int(fixed_result.total_frames), 
                key_result.transform_keys, 
                transform_key_interp
            )
        except Exception as e:
            logger.warning(f"Failed to write transform keys: {e}")
            traceback.print_exc()
    
    # Step 9: Save and export
    save_asset(sequence)
    logger.info(f"Sequence {batch_idx + 1}/{batch_count} completed")
    
    _export_camera_if_enabled(
        sequence_path=asset_path,
        camera_export_cfg=export.camera_export_cfg,
        ue_config=export.ue_config,
        actor_blueprint_class_path=context.actor_blueprint_class_path,
    )
    
    return {
        "name": sequence_name,
        "path": asset_path,
        "seed": actual_seed,
    }


def _generate_navigation_path(
    *,
    nav: Any,
    world: Any,
    roam_cfg: Dict[str, Any],
    map_path: str,
    seq_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate navigation path and return points, yaws, seed."""
    result = _build_nav_points_with_retry(
        nav=nav,
        world=world,
        roam_cfg=roam_cfg,
        map_path=map_path,
        parent_config=seq_cfg,
    )
    
    nav_points = result["points"]
    yaws = result["yaws"]
    pitches = result.get("pitches", [0.0] * len(result["points"]))
    actual_seed = result["seed"]
    behavior_segments = result.get("behavior_segments", [])
    
    # Debug: Log pitch data received
    if pitches:
        logger.info(f"Received pitch data: min={min(pitches):.2f}°, max={max(pitches):.2f}°, avg={sum(pitches)/len(pitches):.2f}°, count={len(pitches)}")
    else:
        logger.warning("No pitch data received from behavior executor!")
    
    if len(nav_points) < 2:
        error_msg = f"Behavior sequence produced too few points ({len(nav_points)}). "
        error_msg += "This may indicate navigation system issues or insufficient NavMesh coverage."
        raise RuntimeError(error_msg)
    
    return {
        "points": nav_points,
        "yaws": yaws,
        "pitches": pitches,
        "seed": actual_seed,
        "behavior_segments": behavior_segments,
    }


def _adjust_behavior_segments_after_truncation(
    behavior_segments: list,
    original_point_count: int,
    truncated_point_count: int,
) -> list:
    """
    Adjust behavior segment indices after nav_points truncation.
    
    When strict duration mode truncates the path, behavior_segments must be updated
    to ensure their indices don't exceed the new point count.
    
    Args:
        behavior_segments: Original behavior segments with start_idx/end_idx
        original_point_count: Original number of points before truncation
        truncated_point_count: Number of points after truncation
    
    Returns:
        Adjusted behavior segments list with valid indices
    """
    if truncated_point_count >= original_point_count:
        # No truncation occurred
        return behavior_segments
    
    adjusted_segments = []
    last_valid_idx = truncated_point_count - 1
    
    for seg in behavior_segments:
        seg_start = seg["start_idx"]
        seg_end = seg["end_idx"]
        
        if seg_start > last_valid_idx:
            # Entire segment is beyond truncation point - discard and stop
            logger.info(f"  Discarded segment '{seg['type']}' [{seg_start}-{seg_end}] (beyond truncation at {truncated_point_count})")
            break
        
        if seg_end > last_valid_idx:
            # Segment partially truncated - clip end index
            adjusted_seg = seg.copy()
            adjusted_seg["end_idx"] = last_valid_idx
            adjusted_segments.append(adjusted_seg)
            logger.info(f"  Clipped segment '{seg['type']}' end from {seg_end} to {last_valid_idx}")
            break  # This is the last valid segment
        
        # Segment fully within valid range - keep as is
        adjusted_segments.append(seg)
    
    return adjusted_segments


def _apply_fixed_speed_if_configured(
    *,
    nav_points: list,
    fps: int,
    duration_seconds: float,
    total_frames: int,
    sequence: Any,
    fixed_speed_cfg: Any,
    strict_duration: bool,
) -> FixedSpeedResult:
    if fixed_speed_cfg is None:
        return FixedSpeedResult(nav_points=nav_points, duration_seconds=duration_seconds, total_frames=total_frames)

    try:
        fixed_speed = float(fixed_speed_cfg)
        if fixed_speed <= 0:
            return FixedSpeedResult(nav_points=nav_points, duration_seconds=duration_seconds, total_frames=total_frames)

        # 计算路径总长度
        total_path_length_cm = 0.0
        for i in range(1, len(nav_points)):
            total_path_length_cm += distance_cm(nav_points[i - 1], nav_points[i])

        # 根据固定速度计算需要的时间
        calculated_duration = total_path_length_cm / fixed_speed
        logger.info("Fixed speed mode enabled:")
        logger.info(f"  Path length: {total_path_length_cm:.2f} cm")
        logger.info(f"  Fixed speed: {fixed_speed:.2f} cm/s")
        logger.info(f"  Original duration: {duration_seconds:.2f}s")
        logger.info(f"  Calculated duration (full path): {calculated_duration:.2f}s")

        if strict_duration:
            # 严格模式：保持duration_seconds不变，可能不会走完全程
            max_distance_cm = fixed_speed * duration_seconds
            logger.info(
                f"  Strict duration mode: will travel max {max_distance_cm:.2f} cm in {duration_seconds:.2f}s"
            )

            if max_distance_cm < total_path_length_cm:
                # 沿着路径行进，找到在max_distance_cm处的点
                accumulated_dist = 0.0
                truncated_points = [nav_points[0]]

                for i in range(1, len(nav_points)):
                    seg_dist = distance_cm(nav_points[i - 1], nav_points[i])

                    if accumulated_dist + seg_dist <= max_distance_cm:
                        # 整个段都在范围内
                        truncated_points.append(nav_points[i])
                        accumulated_dist += seg_dist
                    else:
                        # 这个段需要部分截取
                        remaining = max_distance_cm - accumulated_dist
                        if remaining > 0.01:  # 至少1mm
                            # 在这个段上插值
                            ratio = remaining / seg_dist
                            a = nav_points[i - 1]
                            b = nav_points[i]
                            final_point = unreal.Vector(
                                a.x + (b.x - a.x) * ratio,
                                a.y + (b.y - a.y) * ratio,
                                a.z + (b.z - a.z) * ratio,
                            )
                            truncated_points.append(final_point)
                        break

                nav_points = truncated_points
                logger.info(f"  Truncated to {len(nav_points)} points")
            else:
                logger.info("  Full path can be completed within duration")

            return FixedSpeedResult(nav_points=nav_points, duration_seconds=duration_seconds, total_frames=total_frames)

        # 非严格模式：调整duration_seconds以走完全程
        duration_seconds = calculated_duration
        total_frames = int(fps * duration_seconds)

        # 重新设置序列的播放范围
        try:
            sequence.set_playback_start(0)
            sequence.set_playback_end(total_frames)
            logger.info(f"Updated playback range: 0-{total_frames} ({duration_seconds:.2f}s)")
        except Exception as e:
            logger.warning(f"Could not update playback range: {e}")

        return FixedSpeedResult(nav_points=nav_points, duration_seconds=duration_seconds, total_frames=total_frames)

    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid fixed_speed value: {e}")
        return FixedSpeedResult(nav_points=nav_points, duration_seconds=duration_seconds, total_frames=total_frames)


def _resample_nav_points(
    *,
    nav_points: list,
    fps: int,
    total_frames: int,
    z_offset_cm: float,
) -> SampleResult:
    key_interval_seconds = 1.0 / float(fps)
    key_interval_frames = max(1, int(round(float(fps) * key_interval_seconds)))
    key_count = max(2, int(math.floor(float(total_frames) / float(key_interval_frames))) + 1)
    samples = resample_by_count(nav_points, key_count)

    if abs(z_offset_cm) > 0.001:
        samples = [unreal.Vector(p.x, p.y, p.z + z_offset_cm) for p in samples]

    return SampleResult(samples=samples, key_interval_frames=key_interval_frames)


def _resample_behavior_aware(
    *,
    nav_points: list,
    nav_yaws: list,
    nav_pitches: list,
    behavior_segments: list,
    fps: int,
    total_frames: int,
    z_offset_cm: float,
) -> tuple[list, list, list, int]:
    """
    Resample points, yaws, and pitches with behavior-aware interpolation.
    
    - IDLE: Keep position, yaw, and pitch constant
    - ROTATE: Keep position constant, interpolate yaw and pitch
    - TRANSLATE: Interpolate position, keep yaw and pitch constant
    - ROAM: Interpolate position and yaw, keep pitch constant (or from slope if enabled)
    
    Returns:
        Tuple of (resampled_points, resampled_yaws, resampled_pitches, key_interval_frames)
    """
    key_interval_seconds = 1.0 / float(fps)
    key_interval_frames = max(1, int(round(float(fps) * key_interval_seconds)))
    key_count = max(2, int(math.floor(float(total_frames) / float(key_interval_frames))) + 1)
    
    # Build frame-based segment map for accurate behavior type lookup
    frame_to_segment = {}  # frame -> segment_info
    for seg in behavior_segments:
        for frame in range(seg["start_frame"], seg["end_frame"] + 1):
            frame_to_segment[frame] = seg
    
    # Build point index to segment map
    point_to_segment = {}
    for seg in behavior_segments:
        for idx in range(seg["start_idx"], seg["end_idx"] + 1):
            point_to_segment[idx] = seg
    
    resampled_points = []
    resampled_yaws = []
    resampled_pitches = []
    
    for i in range(key_count):
        # Calculate the frame for this key
        frame = i * key_interval_frames
        if frame > total_frames:
            frame = total_frames
        
        # Find which segment this frame belongs to
        segment = frame_to_segment.get(frame)
        
        if not segment:
            # No segment info, use standard interpolation
            ratio = float(i) / float(key_count - 1) if key_count > 1 else 0.0
            point_idx = int(ratio * (len(nav_points) - 1))
            point_idx = min(point_idx, len(nav_points) - 1)
            
            resampled_points.append(nav_points[point_idx])
            resampled_yaws.append(nav_yaws[point_idx] if point_idx < len(nav_yaws) else 0.0)
            resampled_pitches.append(nav_pitches[point_idx] if point_idx < len(nav_pitches) else 0.0)
            continue
        
        behavior_type = segment["type"]
        seg_start_idx = segment["start_idx"]
        seg_end_idx = segment["end_idx"]
        seg_start_frame = segment["start_frame"]
        seg_end_frame = segment["end_frame"]
        
        # Calculate position within segment (0.0 to 1.0)
        if seg_end_frame > seg_start_frame:
            seg_ratio = float(frame - seg_start_frame) / float(seg_end_frame - seg_start_frame)
        else:
            seg_ratio = 0.0
        seg_ratio = max(0.0, min(1.0, seg_ratio))
        
        # Apply behavior-specific interpolation
        if behavior_type == "idle":
            # IDLE: completely freeze position, yaw, and pitch
            idle_pos = nav_points[seg_start_idx]
            idle_yaw = nav_yaws[seg_start_idx] if seg_start_idx < len(nav_yaws) else 0.0
            idle_pitch = nav_pitches[seg_start_idx] if seg_start_idx < len(nav_pitches) else 0.0
            
            resampled_points.append(idle_pos)
            resampled_yaws.append(idle_yaw)
            resampled_pitches.append(idle_pitch)
        
        elif behavior_type == "rotate":
            # ROTATE: freeze position, interpolate yaw and pitch linearly within segment
            rotate_pos = nav_points[seg_start_idx]
            
            # Interpolate yaw between start and end of segment
            if seg_start_idx < len(nav_yaws) and seg_end_idx < len(nav_yaws):
                start_yaw = nav_yaws[seg_start_idx]
                end_yaw = nav_yaws[seg_end_idx]
                interpolated_yaw = start_yaw + (end_yaw - start_yaw) * seg_ratio
            else:
                interpolated_yaw = nav_yaws[seg_start_idx] if seg_start_idx < len(nav_yaws) else 0.0
            
            # Interpolate pitch between start and end of segment
            if seg_start_idx < len(nav_pitches) and seg_end_idx < len(nav_pitches):
                start_pitch = nav_pitches[seg_start_idx]
                end_pitch = nav_pitches[seg_end_idx]
                interpolated_pitch = start_pitch + (end_pitch - start_pitch) * seg_ratio
            else:
                interpolated_pitch = nav_pitches[seg_start_idx] if seg_start_idx < len(nav_pitches) else 0.0
            
            resampled_points.append(rotate_pos)
            resampled_yaws.append(interpolated_yaw)
            resampled_pitches.append(interpolated_pitch)
        
        elif "translate" in behavior_type:
            # TRANSLATE: interpolate position linearly, freeze yaw and pitch
            if seg_end_idx > seg_start_idx:
                # Linear interpolation between segment start and end points
                start_pos = nav_points[seg_start_idx]
                end_pos = nav_points[seg_end_idx]
                
                interpolated_pos = unreal.Vector(
                    start_pos.x + (end_pos.x - start_pos.x) * seg_ratio,
                    start_pos.y + (end_pos.y - start_pos.y) * seg_ratio,
                    start_pos.z + (end_pos.z - start_pos.z) * seg_ratio,
                )
            else:
                interpolated_pos = nav_points[seg_start_idx]
            
            # Yaw and pitch locked to segment start
            locked_yaw = nav_yaws[seg_start_idx] if seg_start_idx < len(nav_yaws) else 0.0
            locked_pitch = nav_pitches[seg_start_idx] if seg_start_idx < len(nav_pitches) else 0.0
            
            resampled_points.append(interpolated_pos)
            resampled_yaws.append(locked_yaw)
            resampled_pitches.append(locked_pitch)
        
        else:
            # ROAM: interpolate position and yaw, keep pitch constant within segment
            # Use distance-based interpolation for smoother paths
            seg_point_count = seg_end_idx - seg_start_idx + 1
            if seg_point_count > 1:
                # Find the two surrounding points in the segment
                local_idx = seg_start_idx + int(seg_ratio * (seg_point_count - 1))
                local_idx = min(local_idx, seg_end_idx - 1)
                
                # Interpolate between local_idx and local_idx+1
                if local_idx + 1 <= seg_end_idx and local_idx + 1 < len(nav_points):
                    p1 = nav_points[local_idx]
                    p2 = nav_points[local_idx + 1]
                    
                    # Sub-ratio within this segment
                    local_ratio = (seg_ratio * (seg_point_count - 1)) - int(seg_ratio * (seg_point_count - 1))
                    
                    interpolated_pos = unreal.Vector(
                        p1.x + (p2.x - p1.x) * local_ratio,
                        p1.y + (p2.y - p1.y) * local_ratio,
                        p1.z + (p2.z - p1.z) * local_ratio,
                    )
                    
                    if local_idx < len(nav_yaws) and local_idx + 1 < len(nav_yaws):
                        # Angle-aware interpolation for yaw (handles wraparound at ±180°)
                        yaw1 = nav_yaws[local_idx]
                        yaw2 = nav_yaws[local_idx + 1]
                        
                        # Calculate shortest angular distance
                        delta = yaw2 - yaw1
                        if delta > 180:
                            delta -= 360
                        elif delta < -180:
                            delta += 360
                        
                        # Interpolate along shortest path
                        interpolated_yaw = yaw1 + delta * local_ratio
                        
                        # Normalize to [-180, 180]
                        while interpolated_yaw > 180:
                            interpolated_yaw -= 360
                        while interpolated_yaw < -180:
                            interpolated_yaw += 360
                    else:
                        interpolated_yaw = nav_yaws[local_idx] if local_idx < len(nav_yaws) else 0.0
                    
                    # Pitch stays constant during roam (will be calculated from slope later if enabled)
                    interpolated_pitch = nav_pitches[seg_start_idx] if seg_start_idx < len(nav_pitches) else 0.0
                else:
                    interpolated_pos = nav_points[local_idx]
                    interpolated_yaw = nav_yaws[local_idx] if local_idx < len(nav_yaws) else 0.0
                    interpolated_pitch = nav_pitches[local_idx] if local_idx < len(nav_pitches) else 0.0
            else:
                interpolated_pos = nav_points[seg_start_idx]
                interpolated_yaw = nav_yaws[seg_start_idx] if seg_start_idx < len(nav_yaws) else 0.0
                interpolated_pitch = nav_pitches[seg_start_idx] if seg_start_idx < len(nav_pitches) else 0.0
            
            resampled_points.append(interpolated_pos)
            resampled_yaws.append(interpolated_yaw)
            resampled_pitches.append(interpolated_pitch)
    
    # Apply Z offset
    if abs(z_offset_cm) > 0.001:
        resampled_points = [unreal.Vector(p.x, p.y, p.z + z_offset_cm) for p in resampled_points]
    
    # Debug: Log resampled pitch statistics
    if resampled_pitches:
        logger.info(f"Resampled pitch data: min={min(resampled_pitches):.2f}°, max={max(resampled_pitches):.2f}°, avg={sum(resampled_pitches)/len(resampled_pitches):.2f}°, count={len(resampled_pitches)}")
    
    return resampled_points, resampled_yaws, resampled_pitches, key_interval_frames


def _build_transform_keys_from_samples(
    *,
    samples: list,
    fps: int,
    total_frames: int,
    key_interval_frames: int,
    camera_pitch_from_slope: bool,
    pitch_range: tuple,
    precomputed_yaws: Optional[list] = None,
    precomputed_pitches: Optional[list] = None,
    behavior_segments: Optional[list] = None,
) -> KeyGenResult:
    keys = []
    
    # Debug: Log input pitch data
    if precomputed_pitches:
        logger.info(f"Building keys with precomputed pitch: min={min(precomputed_pitches):.2f}°, max={max(precomputed_pitches):.2f}°, avg={sum(precomputed_pitches)/len(precomputed_pitches):.2f}°, count={len(precomputed_pitches)}")
    else:
        logger.info("Building keys WITHOUT precomputed pitch data")
    
    # Build a frame-to-segment map for quick lookup
    frame_to_segment = {}
    if behavior_segments:
        for seg in behavior_segments:
            for frame in range(seg["start_frame"], seg["end_frame"] + 1):
                frame_to_segment[frame] = seg
    
    for i, p in enumerate(samples):
        frame = i * key_interval_frames
        if frame > total_frames:
            frame = total_frames
        t = float(frame) / float(fps)

        # Use precomputed yaw if available (from behavior executor)
        if precomputed_yaws and i < len(precomputed_yaws):
            yaw = precomputed_yaws[i]
        else:
            # Fallback: calculate yaw from trajectory
            if i < len(samples) - 1:
                yaw = yaw_degrees_xy(p, samples[i + 1])
            else:
                yaw = yaw_degrees_xy(samples[i - 1], p) if i > 0 else 0.0

        # Determine pitch based on behavior type
        pitch = 0.0
        segment = frame_to_segment.get(frame)
        
        # If this frame is part of a ROTATE behavior, use precomputed pitch
        if segment and segment.get("type") == "rotate":
            if precomputed_pitches and i < len(precomputed_pitches):
                pitch = precomputed_pitches[i]
            else:
                pitch = 0.0
        # Otherwise, use precomputed pitch or calculate from slope
        elif precomputed_pitches and i < len(precomputed_pitches):
            # Use precomputed pitch (from behavior executor, e.g., roam/translate/idle)
            pitch = precomputed_pitches[i]
            
            # If camera_pitch_from_slope is enabled, calculate slope-based pitch for non-rotate segments
            if camera_pitch_from_slope and (not segment or segment.get("type") in ["random_roam", None]):
                if i < len(samples) - 1:
                    # Forward slope
                    pitch = calculate_pitch_from_slope(p, samples[i + 1], pitch_range)
                elif i > 0:
                    # Last point uses previous segment's slope
                    pitch = calculate_pitch_from_slope(samples[i - 1], p, pitch_range)
        elif camera_pitch_from_slope:
            # No precomputed pitch, calculate from slope if enabled
            if i < len(samples) - 1:
                pitch = calculate_pitch_from_slope(p, samples[i + 1], pitch_range)
            elif i > 0:
                pitch = calculate_pitch_from_slope(samples[i - 1], p, pitch_range)

        keys.append(
            {
                "time_seconds": t,
                "location": {"x": float(p.x), "y": float(p.y), "z": float(p.z)},
                "rotation": {"pitch": float(pitch), "yaw": float(yaw), "roll": 0.0},
            }
        )

    # Debug: Log output pitch statistics
    output_pitches = [k["rotation"]["pitch"] for k in keys]
    if output_pitches:
        logger.info(f"Output keys pitch: min={min(output_pitches):.2f}°, max={max(output_pitches):.2f}°, avg={sum(output_pitches)/len(output_pitches):.2f}°, count={len(output_pitches)}")

    return KeyGenResult(transform_keys=keys)


def _export_camera_if_enabled(
    *,
    sequence_path: str,
    camera_export_cfg: Optional[Dict[str, Any]],
    ue_config: Dict[str, Any],
    actor_blueprint_class_path: str,
) -> None:
    """
    如果启用了camera_export，自动导出相机数据
    """
    if not camera_export_cfg or not camera_export_cfg.get("enabled", False):
        logger.info("Camera export disabled, skipping")
        return
    
    binding_camera = camera_export_cfg.get("binding_camera")
    if not binding_camera:
        logger.warning("camera_export enabled but no binding_camera specified, skipping export")
        return
    
    try:
        logger.info("========================================")
        logger.info("AUTO-EXPORTING CAMERA DATA")
        logger.info("========================================")
        logger.info(f"Sequence: {sequence_path}")
        logger.info(f"Camera binding: {binding_camera}")
        logger.info(f"UE Config output_base_dir: {ue_config.get('output_base_dir', 'NOT SET')}")
        
        # 构建导出manifest
        export_manifest = {
            "sequence": sequence_path,
            "camera_export": camera_export_cfg,
            "ue_config": ue_config,
            "sequence_config": {
                "actor_blueprint_class_path": actor_blueprint_class_path,
            },
        }
        
        # 调用导出函数
        result = camera_exporter.export_camera_from_manifest(export_manifest)
        
        if result.get("status") == "success":
            logger.info(f"  Camera data exported successfully")
            logger.info(f"  Output: {result.get('output_dir')}")
            logger.info(f"  Extrinsic: {result.get('extrinsic_csv')}")
            logger.info(f"  Transform: {result.get('transform_csv')}")
            logger.info(f"  Intrinsic: {result.get('intrinsic_csv')}")
        else:
            logger.warning(f"Camera export returned unexpected status: {result}")
            
    except Exception as e:
        logger.error(f"Failed to auto-export camera data: {e}")
        import traceback
        traceback.print_exc()


def main(argv: Optional[List[str]] = None) -> int:
    logger.info("Starting job execution...")

    argv = list(argv) if argv is not None else sys.argv[1:]
    
    manifest_path = job_utils.resolve_manifest_path_from_env("UE_MANIFEST_PATH", argv)
    if not manifest_path:
        logger.error("No manifest path provided")
        return 1

    logger.info(f"Manifest: {manifest_path}")

    try:
        manifest = job_utils.load_manifest(manifest_path)
    except Exception as e:
        logger.error(str(e))
        return 1

    job_id = manifest.get("job_id", "unknown")
    job_type = manifest.get("job_type", "unknown")
    map_path = manifest.get("map", "")
    sequence_config = manifest.get("sequence_config", {}) or {}
    job_config = SequenceJobConfig.from_dict(sequence_config)
    
    # Extract camera_export config and ue_config for auto-export
    camera_export_cfg = sequence_config.get("camera_export", None)
    ue_config = manifest.get("ue_config", {})
    
    logger.info("========================================")
    logger.info("MANIFEST UE_CONFIG VERIFICATION")
    logger.info("========================================")
    logger.info(f"ue_config present in manifest: {bool(ue_config)}")
    if ue_config:
        logger.info(f"  editor_cmd: {ue_config.get('editor_cmd', 'NOT SET')}")
        logger.info(f"  project_path: {ue_config.get('project_path', 'NOT SET')}")
        logger.info(f"  output_base_dir: {ue_config.get('output_base_dir', 'NOT SET')}")
        logger.info(f"  scenes: {bool(ue_config.get('scenes'))}")
    else:
        logger.warning("ue_config is MISSING or EMPTY in manifest!")
    logger.info("========================================")
    logger.info("CAMERA EXPORT CONFIGURATION")
    logger.info("========================================")
    if camera_export_cfg:
        logger.info(f"Camera export enabled: {camera_export_cfg.get('enabled', False)}")
        logger.info(f"Binding camera: {camera_export_cfg.get('binding_camera', 'N/A')}")
    else:
        logger.info("Camera export config: NOT FOUND")
    logger.info("========================================")

    # Resolve output directory
    # Priority: 1) job_config.output_dir, 2) auto-derive from map_path
    output_dir = job_config.output_dir
    if not output_dir or output_dir.strip() == "":
        derived_dir = job_utils.derive_output_dir_from_map(map_path)
        if derived_dir:
            output_dir = derived_dir
            logger.info(f"Using auto-derived output directory: {output_dir}")
        else:
            logger.error("Failed to derive output directory from map path and no output_dir specified")
            return 1
    
    # Extract job configuration
    batch_count = int(job_config.sequence_count)
    actor_blueprint_class_path = job_config.actor_blueprint_class_path
    nav_roam_cfg = job_config.nav_roam
    max_yaw_rate_deg_per_sec = job_config.max_yaw_rate_deg_per_sec
    base_transform_key_interp = job_config.transform_key_interp
    
    # Derive map_name for logging and sequence naming
    map_name = job_utils.extract_map_name(map_path)

    logger.info(f"Job ID:   {job_id}")
    logger.info(f"Job Type: {job_type}")
    logger.info(f"Map:      {map_path}")
    logger.info(f"Output:   {output_dir}")
    logger.info(f"Actor:    {job_config.actor_name}")
    logger.info(f"Camera:   {job_config.camera_component_name}")
    logger.info(f"BindMode: {job_config.actor_binding_mode}")


    if job_type != "create_sequence":
        logger.error(f"Invalid job type '{job_type}', expected 'create_sequence'")
        return 1

    logger.info(f"Will generate {batch_count} sequence(s)")

    logger.info(f"Checking for existing sequences in {output_dir}...")
    existing_max_index = _find_existing_max_index(output_dir, map_name)
    if existing_max_index > 0:
        logger.info(f"Found existing sequences up to {map_name}_{existing_max_index:03d}")
    else:
        logger.info("No existing sequences found")

    try:
        completed_sequences = generate_all_sequences(
            batch_count=batch_count,
            start_index=existing_max_index,
            map_path=map_path,
            output_dir=output_dir,
            actor_blueprint_class_path=actor_blueprint_class_path,
            nav_roam_cfg=nav_roam_cfg,
            max_yaw_rate_deg_per_sec=max_yaw_rate_deg_per_sec,
            base_transform_key_interp=base_transform_key_interp,
            sequence_config=sequence_config,
            camera_export_cfg=camera_export_cfg,
            ue_config=ue_config,
        )
    except Exception as e:
        logger.error(str(e))
        traceback.print_exc()
        return 1

    logger.plain("\n" + "=" * 60)
    logger.info("✓ All batches completed")
    logger.info(f"Successfully generated: {len(completed_sequences)}/{batch_count} sequences")
    logger.plain("=" * 60)
    for idx, seq_info in enumerate(completed_sequences, 1):
        logger.plain(f"  {idx}. {seq_info['name']}")
        logger.plain(f"     Path: {seq_info['path']}")
        if seq_info.get("seed") is not None:
            logger.plain(f"     Seed: {seq_info['seed']}")
    logger.plain("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())