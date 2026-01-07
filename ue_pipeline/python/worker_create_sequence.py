import math
import os
import random
import sys
import traceback
from typing import Any, Dict, List, Optional

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
_parent_dir = os.path.dirname(_script_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import unreal

from logger import logger

from worker_common import load_json as _load_json, resolve_manifest_path_from_env as _resolve_manifest_path_from_env

# Setup import paths for UE direct execution environment
try:
    import levelsequence.nav_utils
except ImportError:
    pass

from validators import validate_prerequisites
from assets_manager import (
    load_map,
    load_blueprint_class,
    ensure_directory_exists,
    create_level_sequence,
    save_asset,
)
from seq_camera_bindings import (
    create_camera_cuts_track,
    bind_camera_to_cut_section,
    ensure_actor_binding,
)
from levelsequence.nav_utils import (
    build_multi_leg_nav_path,
    distance_cm,
    get_nav_system,
    resample_by_distance,
    wait_for_navigation_ready,
)
from key_frame_track import (
    sanitize_rotation_keys,
    write_transform_keys,
)
import export_UE_camera

from levelsequence.sequence_type import (
    FixedSpeedResult,
    KeyGenResult,
    NavPathResult,
    SampleResult,
    SequenceJobConfig,
)

# Try to import levelsequence helpers
try:
    from levelsequence import (
        get_spawn_point_with_connectivity,
    )
    NAVMESH_CONNECTIVITY_AVAILABLE = True
except ImportError:
    NAVMESH_CONNECTIVITY_AVAILABLE = False
    get_spawn_point_with_connectivity = None
    logger.warning("levelsequence.navmesh_connectivity not available")


def _is_instance_of(actor: Any, cls: Any) -> bool:
    try:
        return cls is not None and actor is not None and isinstance(actor, cls)
    except Exception:
        return False


def _yaw_degrees_xy(a: unreal.Vector, b: unreal.Vector) -> float:
    dx = b.x - a.x
    dy = b.y - a.y
    if abs(dx) < 1e-4 and abs(dy) < 1e-4:
        return 0.0
    return float(math.degrees(math.atan2(dy, dx)))


def _calculate_pitch_from_slope(a: unreal.Vector, b: unreal.Vector, max_pitch_deg: float = 25.0) -> float:
    """计算从点a到点b的坡度对应的相机pitch角度
    上坡：正pitch（向上看）
    下坡：负pitch（向下看）
    """
    horizontal_dist = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2)
    if horizontal_dist < 1.0:  # 避免除以0
        return 0.0

    height_diff = b.z - a.z
    slope_angle = math.degrees(math.atan2(height_diff, horizontal_dist))

    if abs(slope_angle) > max_pitch_deg:
        slope_angle = max_pitch_deg if slope_angle > 0 else -max_pitch_deg

    return float(slope_angle)
def _get_world():
    try:
        # Use UnrealEditorSubsystem instead of deprecated EditorLevelLibrary.get_editor_world
        subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        return subsystem.get_editor_world()
    except Exception as e:
        raise RuntimeError(f"Failed to get editor world: {e}")


def _find_first_startpoint(mode: str = "player_start"):
    mode = (mode or "player_start").lower()
    # 使用 EditorActorSubsystem 获取所有场景Actor
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = actor_subsystem.get_all_level_actors()

    player_start_cls = getattr(unreal, "PlayerStart", None)
    target_point_cls = getattr(unreal, "TargetPoint", None)

    if mode in ("player_start", "playerstart"):
        for a in actors:
            if _is_instance_of(a, player_start_cls):
                return a

    if mode in ("target_point", "targetpoint"):
        for a in actors:
            if _is_instance_of(a, target_point_cls):
                return a

    # Fallback: any actor whose name/label contains 'start'
    for a in actors:
        try:
            if a is None:
                continue
            name = (a.get_name() or "")
            label_fn = getattr(a, "get_actor_label", None)
            label = label_fn() if callable(label_fn) else ""
            s = f"{name} {label}".lower()
            if "start" in s:
                return a
        except Exception:
            continue

    # Last resort: return the first PlayerStart/TargetPoint if any
    for a in actors:
        if _is_instance_of(a, player_start_cls) or _is_instance_of(a, target_point_cls):
            return a
    return None


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


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _resolve_manifest_path(argv: List[str]) -> str:
    manifest_path = _resolve_manifest_path_from_env("UE_MANIFEST_PATH", argv)
    if manifest_path:
        return manifest_path
    raise RuntimeError("No manifest path provided")


def _load_manifest(manifest_path: str) -> Dict[str, Any]:
    try:
        return _load_json(manifest_path)
    except Exception as e:
        raise RuntimeError(f"Failed to read manifest: {e}")


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

    world = _get_world()
    nav = get_nav_system(world)
    wait_for_navigation_ready(nav, world, float(nav_roam_cfg.get("nav_build_wait_seconds", 10.0)))
    return world, nav


def _build_nav_points_with_retry(
    *,
    nav: Any,
    world: Any,
    roam_cfg: Dict[str, Any],
    map_path: str,
    run_id: int,
    parent_config: Dict[str, Any] = None,
) -> NavPathResult:
    seed_cfg = roam_cfg.get("seed", None)
    actual_seed: Optional[int] = None
    if seed_cfg is not None:
        try:
            seed_val = int(seed_cfg)
            if seed_val == -1:
                # -1表示使用随机种子
                actual_seed = random.randint(0, 999999)
                random.seed(actual_seed)
                logger.info(f"✓ NavRoam seed: {actual_seed} (random)")
            else:
                actual_seed = seed_val
                random.seed(actual_seed)
                logger.info(f"✓ NavRoam seed: {actual_seed}")
        except Exception as e:
            logger.warning(f"Failed to set seed: {e}")

    def _cfg_for_seed(seed: Optional[int]) -> Dict[str, Any]:
        cfg = dict(roam_cfg)
        if seed is not None:
            cfg["seed"] = int(seed)
        # Inject parent config for duration-based path generation
        if parent_config:
            cfg["_parent_config"] = parent_config
        return cfg

    nav_roam_cfg_for_path = _cfg_for_seed(actual_seed)

    # 尝试生成路径，如果失败则重新生成种子重试一次
    for path_attempt in range(2):  # 最多尝试2次
        try:
            if path_attempt == 1:
                # 第二次尝试：重新生成随机种子
                actual_seed = random.randint(0, 999999)
                random.seed(actual_seed)
                logger.warning(f"Retry with new seed: {actual_seed}")
                nav_roam_cfg_for_path = _cfg_for_seed(actual_seed)

            # Pass map_path for cache naming
            nav_points = build_multi_leg_nav_path(nav, world, nav_roam_cfg_for_path, map_path)
            logger.info(f"NavRoam generated {len(nav_points)} raw points")
            return NavPathResult(nav_points=nav_points, actual_seed=actual_seed)

        except RuntimeError as e:
            error_msg = str(e)
            if "Failed to find connected NavMesh point" in error_msg:
                if path_attempt == 0:
                    logger.warning(f"NavMesh connection failed on first attempt: {e}")
                    logger.warning("Retrying with new random seed...")
                    continue
                logger.error("NavMesh connection failed after 2 attempts")
                raise
            raise

    raise RuntimeError("Failed to generate nav path after retries")


def _apply_fixed_speed_if_configured(
    *,
    nav_points: list,
    fps: int,
    duration_seconds: float,
    total_frames: int,
    movie_scene: Any,
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
            movie_scene.set_playback_range(0, total_frames)
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
    samples = resample_by_distance(nav_points, key_count)

    if abs(z_offset_cm) > 0.001:
        samples = [unreal.Vector(p.x, p.y, p.z + z_offset_cm) for p in samples]

    return SampleResult(samples=samples, key_interval_frames=key_interval_frames)


def _build_transform_keys_from_samples(
    *,
    samples: list,
    fps: int,
    total_frames: int,
    key_interval_frames: int,
    camera_pitch_from_slope: bool,
    max_camera_pitch: float,
) -> KeyGenResult:
    keys = []
    for i, p in enumerate(samples):
        frame = i * key_interval_frames
        if frame > total_frames:
            frame = total_frames
        t = float(frame) / float(fps)

        # 计算yaw（水平朝向）
        if i < len(samples) - 1:
            yaw = _yaw_degrees_xy(p, samples[i + 1])
        else:
            yaw = _yaw_degrees_xy(samples[i - 1], p) if i > 0 else 0.0

        # 计算pitch（相机俯仰角，根据坡度）
        pitch = 0.0
        if camera_pitch_from_slope:
            if i < len(samples) - 1:
                # 前向坡度（看向前方）
                pitch = _calculate_pitch_from_slope(p, samples[i + 1], max_camera_pitch)
            elif i > 0:
                # 最后一个点使用前一段的坡度
                pitch = _calculate_pitch_from_slope(samples[i - 1], p, max_camera_pitch)

        keys.append(
            {
                "time_seconds": t,
                "location": {"x": float(p.x), "y": float(p.y), "z": float(p.z)},
                "rotation": {"pitch": float(pitch), "yaw": float(yaw), "roll": 0.0},
            }
        )

    return KeyGenResult(transform_keys=keys)


def _add_camera_cuts_if_enabled(
    *,
    add_camera: bool,
    sequence: Any,
    movie_scene: Any,
    actor_binding: Any,
    total_frames: int,
) -> None:
    if not add_camera:
        return

    logger.info("Adding camera cuts bound to spawnable actor...")
    try:
        # Add Camera Cuts Track
        logger.info("  Adding Camera Cuts Track...")
        camera_cut_track = create_camera_cuts_track(sequence, movie_scene)
        logger.info("Created Camera Cuts Track")

        # Add a section to the camera cut track
        logger.info("  Adding Camera Cut Section...")
        camera_cut_section = camera_cut_track.add_section()
        if not camera_cut_section:
            raise RuntimeError("Failed to create camera cut section")

        # Set the section range to cover the entire sequence
        try:
            camera_cut_section.set_range(0, total_frames)
            logger.info(f"Set section range: 0-{total_frames}")
        except Exception as e:
            logger.warning(f"Could not set section range: {e}")

        # Bind the camera to the section
        # Note: We bind to the actor binding; UE will use its camera component.
        bind_camera_to_cut_section(camera_cut_section, sequence, movie_scene, actor_binding)

    except Exception as e:
        logger.warning(f"Failed to add camera cuts: {e}")
        traceback.print_exc()


def _export_camera_if_enabled(
    *,
    sequence_path: str,
    camera_export_cfg: Optional[Dict[str, Any]],
    ue_config: Dict[str, Any],
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
        }
        
        # 调用导出函数
        result = export_UE_camera.export_camera_from_manifest(export_manifest)
        
        if result.get("status") == "success":
            logger.info(f"  Camera data exported successfully")
            logger.info(f"  Output: {result.get('output_dir')}")
            logger.info(f"  Extrinsic: {result.get('extrinsic_csv')}")
            logger.info(f"  Transform: {result.get('transform_csv')}")
        else:
            logger.warning(f"Camera export returned unexpected status: {result}")
            
    except Exception as e:
        logger.error(f"Failed to auto-export camera data: {e}")
        import traceback
        traceback.print_exc()


def _write_transform_keys_to_binding(
    *,
    actor_binding: Any,
    fps: int,
    total_frames: int,
    transform_keys_cfg: Any,
    transform_key_interp: str,
    force_zero_pitch_roll: bool,
    max_yaw_rate_deg_per_sec: Optional[float],
    camera_pitch_from_slope: bool,
    max_pitch_rate: float,
) -> None:
    # Write Transform Keys (always enabled)
    if not actor_binding:
        logger.warning("No actor binding was created")
        return

    logger.info("Adding transform keys to actor binding...")
    try:
        # 如果启用了camera_pitch_from_slope，保留pitch值
        sanitize_rotation_keys(
            transform_keys_cfg,
            force_zero_pitch_roll,
            max_yaw_rate_deg_per_sec,
            preserve_pitch=camera_pitch_from_slope,
            max_pitch_rate_deg_per_sec=max_pitch_rate,
        )
        write_transform_keys(actor_binding, int(fps), int(total_frames), transform_keys_cfg, transform_key_interp)
    except Exception as e:
        logger.warning(f"Failed to write transform keys: {e}")
        traceback.print_exc()


def generate_all_sequences(
    *,
    batch_count: int,
    start_index: int,
    map_path: str,
    map_name: str,
    output_dir: str,
    actor_blueprint_class_path: str,
    nav_roam_cfg: Dict[str, Any],
    force_zero_pitch_roll: bool,
    max_yaw_rate_deg_per_sec: Optional[float],
    base_transform_keys_cfg: Optional[list],
    base_transform_key_interp: str,
    sequence_config: Dict[str, Any],
    camera_export_cfg: Optional[Dict[str, Any]],
    ue_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    completed_sequences = []

    import time
    run_id = int(time.time())

    world, nav = _prepare_sequence_generation_run(
        map_path=map_path,
        actor_blueprint_class_path=actor_blueprint_class_path,
        output_dir=output_dir,
        nav_roam_cfg=nav_roam_cfg,
    )

    # Normalize config once (invariant across batches)
    seq_cfg = sequence_config or {}
    roam_cfg = nav_roam_cfg or {}
    
    # Pre-compute connectivity analysis ONCE before batch loop
    # Cache will be reused for all sequences in this batch run
    use_connectivity_analysis = bool(roam_cfg.get("use_connectivity_analysis", True))
    if use_connectivity_analysis and NAVMESH_CONNECTIVITY_AVAILABLE and get_spawn_point_with_connectivity is not None:
        logger.info("========================================")
        logger.info("PRE-COMPUTING CONNECTIVITY ANALYSIS")
        logger.info("========================================")
        try:
            origin = get_spawn_point_with_connectivity(nav, world, map_path, roam_cfg)
            logger.info(f"✓ Connectivity analysis completed, spawn point: ({origin.x:.2f}, {origin.y:.2f}, {origin.z:.2f})")
            logger.info("Cache will be reused for all sequences in this batch run")
        except Exception as e:
            logger.warning(f"Connectivity analysis pre-computation failed: {e}")
            logger.warning("Will fall back to legacy method in batch loop")
        logger.info("========================================")

    fps = int(seq_cfg.get("fps", 30))
    base_duration_seconds = float(seq_cfg.get("duration_seconds", 60.0))
    add_camera = bool(seq_cfg.get("add_camera", False))
    fixed_speed_cfg = seq_cfg.get("fixed_speed_cm_per_sec", None)
    strict_duration = bool(seq_cfg.get("strict_duration", False))

    camera_pitch_from_slope = bool(seq_cfg.get("camera_pitch_from_slope", False))
    max_camera_pitch = float(seq_cfg.get("max_camera_pitch_deg", 25.0))
    max_pitch_rate = float(seq_cfg.get("max_pitch_rate_deg_per_sec", 20.0))

    z_offset_cm = float(roam_cfg.get("z_offset_cm", 0.0))
    interp_override = roam_cfg.get("interpolation", None)

    for batch_idx in range(batch_count):
        try:
            logger.info("========================================")
            logger.info(f"Generating sequence {batch_idx + 1}/{batch_count}")
            logger.info("========================================")
            
            # 生成当前批次的sequence名称（从已存在的最大编号+1开始）
            sequence_number = start_index + batch_idx + 1
            sequence_name = f"{map_name}_{sequence_number:03d}"

            sequence = create_level_sequence(sequence_name, output_dir)
            if not sequence:
                logger.error("Failed to create LevelSequence asset")
                raise RuntimeError("Failed to create LevelSequence asset")
            
            asset_path = sequence.get_path_name()

            # Per-batch derived values
            duration_seconds = base_duration_seconds
            total_frames = int(fps * duration_seconds)
            
            movie_scene = sequence.get_movie_scene()

            transform_key_interp = str(base_transform_key_interp or "auto").lower()

            nav_result = _build_nav_points_with_retry(
                nav=nav,
                world=world,
                roam_cfg=roam_cfg,
                map_path=map_path,
                run_id=run_id,
                parent_config=seq_cfg,
            )

            if len(nav_result.nav_points) < 2:
                error_msg = f"NavRoam produced too few points ({len(nav_result.nav_points)}). "
                error_msg += "Possible causes: "
                error_msg += "(1) NavMesh coverage too small, "
                error_msg += "(2) random_point_radius_cm too small, "
                error_msg += "(3) NavMesh disconnected/fragmented, "
                raise RuntimeError(error_msg)

            fixed_result = _apply_fixed_speed_if_configured(
                nav_points=nav_result.nav_points,
                fps=fps,
                duration_seconds=duration_seconds,
                total_frames=total_frames,
                movie_scene=movie_scene,
                fixed_speed_cfg=fixed_speed_cfg,
                strict_duration=strict_duration,
            )

            sample_result = _resample_nav_points(
                nav_points=fixed_result.nav_points,
                fps=fps,
                total_frames=fixed_result.total_frames,
                z_offset_cm=z_offset_cm,
            )

            # Prefer linear interpolation for safety (avoid cubic overshoot through walls)
            if interp_override:
                transform_key_interp = (str(interp_override) or transform_key_interp).lower()
            
            if camera_pitch_from_slope:
                logger.info(f"Camera pitch from slope enabled (max pitch: {max_camera_pitch:.1f}°)")

            key_result = _build_transform_keys_from_samples(
                samples=sample_result.samples,
                fps=fps,
                total_frames=fixed_result.total_frames,
                key_interval_frames=sample_result.key_interval_frames,
                camera_pitch_from_slope=camera_pitch_from_slope,
                max_camera_pitch=max_camera_pitch,
            )
            logger.info(f"NavRoam generated {len(key_result.transform_keys)} keys")

            # Always need an actor binding (transform keys are always enabled)
            actor_binding = ensure_actor_binding(
                sequence=sequence,
                actor_blueprint_class_path=actor_blueprint_class_path,
                load_blueprint_class_fn=load_blueprint_class,
            )

            _add_camera_cuts_if_enabled(
                add_camera=add_camera,
                sequence=sequence,
                movie_scene=movie_scene,
                actor_binding=actor_binding,
                total_frames=fixed_result.total_frames,
            )

            _write_transform_keys_to_binding(
                actor_binding=actor_binding,
                fps=fps,
                total_frames=fixed_result.total_frames,
                transform_keys_cfg=key_result.transform_keys,
                transform_key_interp=transform_key_interp,
                force_zero_pitch_roll=force_zero_pitch_roll,
                max_yaw_rate_deg_per_sec=max_yaw_rate_deg_per_sec,
                camera_pitch_from_slope=camera_pitch_from_slope,
                max_pitch_rate=max_pitch_rate,
            )
            
            save_asset(sequence)

            completed_sequences.append(
                {
                    "name": sequence_name,
                    "path": asset_path,
                    "seed": nav_result.actual_seed,
                }
            )
            
            logger.info(f"Sequence {batch_idx + 1}/{batch_count} completed")
            
            # Auto-export camera data if enabled
            _export_camera_if_enabled(
                sequence_path=asset_path,
                camera_export_cfg=camera_export_cfg,
                ue_config=ue_config,
            )
            
        except Exception as e:
            logger.error(f"in batch {batch_idx + 1}: {e}")
            traceback.print_exc()
            continue
    
    return completed_sequences


def _derive_output_dir_from_map(map_path: str) -> Optional[str]:
    if not map_path:
        return None
    
    parts = map_path.split('/')
    if len(parts) < 3:  # 至少需要 /Game/SceneName/...
        return None
    
    # 找到场景根目录 (通常是 /Game/ 后的第一级)
    # /Game/SecretBase/Map -> /Game/SecretBase
    scene_root = '/'.join(parts[:3])
    
    output_dir = f"{scene_root}/Levelsequence"
    logger.info(f"  Output dir: {output_dir}")
    
    return output_dir


def main(argv: Optional[List[str]] = None) -> int:
    logger.info("Starting job execution...")

    argv = list(argv) if argv is not None else sys.argv[1:]
    try:
        manifest_path = _resolve_manifest_path(argv)
    except Exception as e:
        logger.error(str(e))
        return 1

    logger.info(f"Manifest: {manifest_path}")

    try:
        manifest = _load_manifest(manifest_path)
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
        logger.info(f"  editor_path: {ue_config.get('editor_path', 'NOT SET')}")
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

    # 如果配置中没有指定 output_dir 或为空，则从 map 路径自动推导
    output_dir = job_config.output_dir
    if not output_dir or output_dir.strip() == "":
        derived_dir = _derive_output_dir_from_map(map_path)
        if derived_dir:
            output_dir = derived_dir
            logger.info(f"Using auto-derived output directory: {output_dir}")
        else:
            logger.error("Failed to derive output directory from map path and no output_dir specified")
            return 1
    
    batch_count = int(job_config.sequence_count)
    actor_blueprint_class_path = job_config.actor_blueprint_class_path
    nav_roam_cfg = job_config.nav_roam
    force_zero_pitch_roll = bool(job_config.force_zero_pitch_roll)
    max_yaw_rate_deg_per_sec = job_config.max_yaw_rate_deg_per_sec
    base_transform_keys_cfg = job_config.transform_keys
    base_transform_key_interp = job_config.transform_key_interp

    map_name = "Unknown"
    if map_path:
        map_name = map_path.split("/")[-1]

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
        # todo 参数过多，待重构
        completed_sequences = generate_all_sequences(
            batch_count=batch_count,
            start_index=existing_max_index,
            map_path=map_path,
            map_name=map_name,
            output_dir=output_dir,
            actor_blueprint_class_path=actor_blueprint_class_path,
            nav_roam_cfg=nav_roam_cfg,
            force_zero_pitch_roll=force_zero_pitch_roll,
            max_yaw_rate_deg_per_sec=max_yaw_rate_deg_per_sec,
            base_transform_keys_cfg=base_transform_keys_cfg,
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