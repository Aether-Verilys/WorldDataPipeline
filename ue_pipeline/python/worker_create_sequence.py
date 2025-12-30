import json
import math
import os
import random
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
# Ensure local python modules (worker_common, key_frame_track, etc.) are importable
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
    load_map as _load_map,
    load_blueprint_class as _load_blueprint_class,
    ensure_directory_exists as _ensure_directory_exists,
    create_level_sequence as _create_level_sequence,
    save_asset as _save_asset,
)
from seq_camera_bindings import (
    create_camera_cuts_track as _create_camera_cuts_track,
    bind_camera_to_cut_section as _bind_camera_to_cut_section,
    ensure_actor_binding as _ensure_actor_binding,
)
from levelsequence.nav_utils import (
    build_multi_leg_nav_path as _build_multi_leg_nav_path,
    distance_cm as _distance_cm,
    get_nav_system as _get_nav_system,
    resample_by_distance as _resample_by_distance,
    wait_for_navigation_ready as _wait_for_navigation_ready,
)
from key_frame_track import (
    sanitize_rotation_keys as _sanitize_rotation_keys,
    write_transform_keys as _write_transform_keys,
)

# Try to import levelsequence helpers
try:
    from levelsequence import (
        find_largest_connected_region,
        select_spawn_point_from_region,
    )
    NAVMESH_CONNECTIVITY_AVAILABLE = True
except ImportError:
    NAVMESH_CONNECTIVITY_AVAILABLE = False
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


@dataclass
class SequenceJobConfig:
    output_dir: str = "/Game/CameraController/Generated"
    sequence_count: int = 1
    actor_name: str = "BP_NPC_NavMesh"
    camera_component_name: str = "Camera"
    actor_blueprint_class_path: str = "/Game/FirstPerson/Blueprints/BP_NPC_NavMesh.BP_NPC_NavMesh"
    spawn_actor_if_missing: bool = False
    actor_binding_mode: str = "sequence_spawnable"
    save_level_if_spawned: bool = False
    spawn_at_startpoint: bool = False
    nav_roam: dict = field(default_factory=dict)
    force_zero_pitch_roll: bool = True
    max_yaw_rate_deg_per_sec: Optional[float] = None
    write_transform_keys: bool = False
    transform_keys: Optional[list] = None
    transform_key_interp: str = "auto"
    spawn_location: dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    spawn_rotation: dict = field(default_factory=lambda: {"pitch": 0.0, "yaw": 0.0, "roll": 0.0})

    @classmethod
    def from_dict(cls, data: dict) -> "SequenceJobConfig":
        cfg = data or {}
        inst = cls()

        inst.output_dir = cfg.get("output_dir", inst.output_dir)
        inst.sequence_count = int(cfg.get("sequence_count", inst.sequence_count))
        inst.actor_name = cfg.get("actor_name", inst.actor_name)
        inst.camera_component_name = cfg.get("camera_component_name", inst.camera_component_name)
        inst.actor_blueprint_class_path = cfg.get("actor_blueprint_class_path", inst.actor_blueprint_class_path)
        inst.spawn_actor_if_missing = bool(cfg.get("spawn_actor_if_missing", inst.spawn_actor_if_missing))
        inst.actor_binding_mode = (cfg.get("actor_binding_mode", inst.actor_binding_mode) or inst.actor_binding_mode).lower()
        inst.save_level_if_spawned = bool(cfg.get("save_level_if_spawned", inst.save_level_if_spawned))
        inst.spawn_at_startpoint = bool(cfg.get("spawn_at_startpoint", inst.spawn_at_startpoint))
        inst.nav_roam = cfg.get("nav_roam", {}) or {}
        inst.force_zero_pitch_roll = bool(cfg.get("force_zero_pitch_roll", inst.force_zero_pitch_roll))
        inst.write_transform_keys = bool(cfg.get("write_transform_keys", inst.write_transform_keys))
        inst.transform_keys = cfg.get("transform_keys", inst.transform_keys)
        inst.transform_key_interp = (cfg.get("transform_key_interp", inst.transform_key_interp) or inst.transform_key_interp).lower()
        inst.spawn_location = cfg.get("spawn_location", inst.spawn_location)
        inst.spawn_rotation = cfg.get("spawn_rotation", inst.spawn_rotation)

        max_yaw = cfg.get("max_yaw_rate_deg_per_sec", None)
        try:
            if max_yaw is not None:
                max_yaw = float(max_yaw)
                if max_yaw <= 0:
                    max_yaw = None
        except Exception:
            max_yaw = None
        inst.max_yaw_rate_deg_per_sec = max_yaw

        return inst

    @property
    def nav_roam_enabled(self) -> bool:
        return bool(self.nav_roam.get("enabled", False))


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


def generate_all_sequences(
    *,
    batch_count: int,
    start_index: int,
    map_path: str,
    map_name: str,
    output_dir: str,
    actor_blueprint_class_path: str,
    spawn_at_startpoint: bool,
    nav_roam_cfg: Dict[str, Any],
    nav_roam_enabled: bool,
    force_zero_pitch_roll: bool,
    max_yaw_rate_deg_per_sec: Optional[float],
    base_write_transform_keys: bool,
    base_transform_keys_cfg: Optional[list],
    base_transform_key_interp: str,
    spawn_location: Any,
    spawn_rotation: Any,
    sequence_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    completed_sequences = []
    
    for batch_idx in range(batch_count):
        try:
            logger.info("========================================")
            logger.info(f"Generating sequence {batch_idx + 1}/{batch_count}")
            logger.info("========================================")
            
            # 生成当前批次的sequence名称（从已存在的最大编号+1开始）
            sequence_number = start_index + batch_idx + 1
            sequence_name = f"{map_name}_{sequence_number:03d}"
            logger.info(f"Sequence name: {sequence_name}")
            
            # 预检查：地图、蓝图、NavMesh必须都存在（只在第一次执行）
            if batch_idx == 0:
                validate_prerequisites(map_path, actor_blueprint_class_path, nav_roam_enabled, "[WorkerCreateSequence]")
            
            # Load map first (important for level possessables, and avoids world switching mid-script)
            if map_path and batch_idx == 0:
                try:
                    _load_map(map_path)
                except Exception as e:
                    logger.error(f"Map load failed: {e}")
                    raise

            # NavRoam模式下完全依赖NavMesh生成起始点，不使用PlayerStart
            start_location = None
            start_rotation = None
            if spawn_at_startpoint and not nav_roam_enabled:
                # 只有在非NavRoam模式下且需要在StartPoint生成时才查找PlayerStart
                start_mode = (nav_roam_cfg.get("startpoint_mode", "player_start") or "player_start")
                sp = _find_first_startpoint(start_mode)
                if sp is None:
                    logger.warning(f"No StartPoint found (mode={start_mode}); using spawn_location from config")
                else:
                    try:
                        start_location = sp.get_actor_location()
                        start_rotation = sp.get_actor_rotation()
                        logger.info(f"✓ StartPoint: {sp.get_name()} loc={start_location} rot={start_rotation}")
                    except Exception as e:
                        logger.warning(f"Failed reading StartPoint transform: {e}")

            # If we spawn a level actor (possessable mode), optionally spawn it at the startpoint
            batch_spawn_location = spawn_location
            batch_spawn_rotation = spawn_rotation
            if spawn_at_startpoint and start_location is not None:
                batch_spawn_location = start_location
                if start_rotation is not None:
                    batch_spawn_rotation = start_rotation
                logger.info("✓ Using StartPoint as spawn transform")

            # Ensure output directory exists
            _ensure_directory_exists(output_dir)

            # Create LevelSequence asset
            sequence = _create_level_sequence(sequence_name, output_dir)
            if not sequence:
                logger.error("Failed to create LevelSequence asset")
                raise RuntimeError("Failed to create LevelSequence asset")
            
            asset_path = sequence.get_path_name()
            
            # Set basic properties
            fps = sequence_config.get("fps", 30)
            duration_seconds = sequence_config.get("duration_seconds", 60.0)
            total_frames = int(fps * duration_seconds)
            
            movie_scene = sequence.get_movie_scene()
            
            # Set frame rate
            try:
                movie_scene.set_display_rate(unreal.FrameRate(fps, 1))
                logger.info(f"✓ Set frame rate: {fps} fps")
            except Exception as e:
                logger.warning(f"Could not set frame rate: {e}")
            
            # Set playback range
            try:
                movie_scene.set_playback_range(0, total_frames)
                logger.info(f"✓ Set playback range: 0-{total_frames} ({duration_seconds}s)")
            except Exception as e:
                logger.warning(f"Could not set playback range: {e}")
            
            add_camera = bool(sequence_config.get("add_camera", False))
            write_transform_keys = bool(base_write_transform_keys)
            transform_keys_cfg = base_transform_keys_cfg
            transform_key_interp = str(base_transform_key_interp or "auto").lower()
            actor_binding = None
            actual_seed = None

            # If NavRoam is enabled, generate keys from NavMesh and override transform_keys_cfg
            if nav_roam_enabled:
                world = _get_world()
                nav = _get_nav_system(world)
                _wait_for_navigation_ready(nav, world, float(nav_roam_cfg.get("nav_build_wait_seconds", 10.0)))
                seed_cfg = nav_roam_cfg.get("seed", None)
                actual_seed = None
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

                start = start_location if start_location is not None else batch_spawn_location
                logger.info(f"NavRoam starting from: {start}")

                # IMPORTANT: build_multi_leg_nav_path() uses cfg['seed'] to select the NavMesh start point.
                # If config seed is -1 (random), we must pass the resolved actual_seed, otherwise the
                # start point can become effectively fixed across runs.
                nav_roam_cfg_for_path = dict(nav_roam_cfg or {})
                if actual_seed is not None:
                    nav_roam_cfg_for_path["seed"] = int(actual_seed)
                
                # 尝试生成路径，如果失败则重新生成种子重试一次
                nav_points = None
                for path_attempt in range(2):  # 最多尝试2次
                    try:
                        if path_attempt == 1:
                            # 第二次尝试：重新生成随机种子
                            actual_seed = random.randint(0, 999999)
                            random.seed(actual_seed)
                            logger.warning(f"⚠ Retry with new seed: {actual_seed}")

                            nav_roam_cfg_for_path = dict(nav_roam_cfg or {})
                            nav_roam_cfg_for_path["seed"] = int(actual_seed)
                        
                        nav_points = _build_multi_leg_nav_path(nav, world, start, nav_roam_cfg_for_path, map_path)
                        logger.info(f"NavRoam generated {len(nav_points)} raw points")
                        break  # 成功则跳出循环
                        
                    except RuntimeError as e:
                        error_msg = str(e)
                        if "Failed to find connected NavMesh point" in error_msg:
                            if path_attempt == 0:
                                logger.warning(f"⚠ NavMesh connection failed on first attempt: {e}")
                                logger.warning("⚠ Retrying with new random seed...")
                                continue
                            else:
                                logger.error("✗ NavMesh connection failed after 2 attempts")
                                raise
                        else:
                            # 其他类型的错误直接抛出
                            raise
                
                if nav_points is None:
                    raise RuntimeError("Failed to generate nav path after retries")
                
                if len(nav_points) < 2:
                    error_msg = f"NavRoam produced too few points ({len(nav_points)}). "
                    error_msg += f"Starting position: {start}. "
                    error_msg += "Possible causes: "
                    error_msg += "(1) Starting position not on NavMesh, "
                    error_msg += "(2) NavMesh coverage too small, "
                    error_msg += "(3) random_point_radius_cm too small, "
                    error_msg += f"(4) All {nav_roam_cfg.get('num_legs', 6)} legs failed to find valid paths."
                    raise RuntimeError(error_msg)

                # 如果设置了固定速度，计算路径总长度并调整 duration_seconds
                fixed_speed = sequence_config.get("fixed_speed_cm_per_sec", None)
                strict_duration = bool(sequence_config.get("strict_duration", False))
                
                if fixed_speed is not None:
                    try:
                        fixed_speed = float(fixed_speed)
                        if fixed_speed > 0:
                            # 计算路径总长度
                            total_path_length_cm = 0.0
                            for i in range(1, len(nav_points)):
                                total_path_length_cm += _distance_cm(nav_points[i - 1], nav_points[i])
                            
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
                                logger.info(f"  Strict duration mode: will travel max {max_distance_cm:.2f} cm in {duration_seconds:.2f}s")
                                
                                if max_distance_cm < total_path_length_cm:
                                    # 需要截断路径
                                    logger.info(
                                        f"  Path will be truncated (only {max_distance_cm/total_path_length_cm*100:.1f}% of full path)"
                                    )
                                    
                                    # 沿着路径行进，找到在max_distance_cm处的点
                                    accumulated_dist = 0.0
                                    truncated_points = [nav_points[0]]
                                    
                                    for i in range(1, len(nav_points)):
                                        seg_dist = _distance_cm(nav_points[i-1], nav_points[i])
                                        
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
                                                a = nav_points[i-1]
                                                b = nav_points[i]
                                                final_point = unreal.Vector(
                                                    a.x + (b.x - a.x) * ratio,
                                                    a.y + (b.y - a.y) * ratio,
                                                    a.z + (b.z - a.z) * ratio
                                                )
                                                truncated_points.append(final_point)
                                            break
                                    
                                    nav_points = truncated_points
                                    logger.info(f"  Truncated to {len(nav_points)} points")
                                else:
                                    logger.info("  Full path can be completed within duration")
                            else:
                                # 非严格模式：调整duration_seconds以走完全程
                                duration_seconds = calculated_duration
                                total_frames = int(fps * duration_seconds)
                                
                                # 重新设置序列的播放范围
                                try:
                                    movie_scene.set_playback_range(0, total_frames)
                                    logger.info(f"✓ Updated playback range: 0-{total_frames} ({duration_seconds:.2f}s)")
                                except Exception as e:
                                    logger.warning(f"Could not update playback range: {e}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid fixed_speed value: {e}")

                key_interval_seconds = 1.0 / float(fps)
                key_interval_frames = max(1, int(round(float(fps) * key_interval_seconds)))
                key_count = max(2, int(math.floor(float(total_frames) / float(key_interval_frames))) + 1)
                samples = _resample_by_distance(nav_points, key_count)

                z_offset_cm = float(nav_roam_cfg.get("z_offset_cm", 0.0))
                if abs(z_offset_cm) > 0.001:
                    samples = [unreal.Vector(p.x, p.y, p.z + z_offset_cm) for p in samples]

                # Prefer linear interpolation for safety (avoid cubic overshoot through walls)
                interp_override = nav_roam_cfg.get("interpolation", None)
                if interp_override:
                    transform_key_interp = (str(interp_override) or transform_key_interp).lower()
                
                # 是否根据坡度调整相机pitch
                camera_pitch_from_slope = bool(sequence_config.get("camera_pitch_from_slope", False))
                max_camera_pitch = float(sequence_config.get("max_camera_pitch_deg", 25.0))
                
                if camera_pitch_from_slope:
                    logger.info(f"Camera pitch from slope enabled (max pitch: {max_camera_pitch:.1f}°)")

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
                    
                    # 打印前3个关键帧的位置用于调试
                    if i < 3:
                        logger.info(
                            f"  Key {i}: time={t:.2f}s, pos=({p.x:.2f}, {p.y:.2f}, {p.z:.2f}), yaw={yaw:.2f}"
                        )

                transform_keys_cfg = keys
                write_transform_keys = True
                logger.info(f"✓ NavRoam generated {len(keys)} keys")

            # Add camera cuts / transform tracks need a binding
            needs_actor_binding = bool(add_camera) or bool(write_transform_keys)
            if needs_actor_binding:
                actor_binding = _ensure_actor_binding(
                    sequence=sequence,
                    actor_blueprint_class_path=actor_blueprint_class_path,
                    load_blueprint_class_fn=_load_blueprint_class,
                )

            if add_camera:
                logger.info("Adding camera cuts bound to spawnable actor...")

                try:
                    camera_binding = actor_binding

                    # Add Camera Cuts Track
                    logger.info("  Adding Camera Cuts Track...")
                    camera_cut_track = _create_camera_cuts_track(sequence, movie_scene)
                    logger.info("✓ Created Camera Cuts Track")

                    # Add a section to the camera cut track
                    logger.info("  Adding Camera Cut Section...")
                    camera_cut_section = camera_cut_track.add_section()
                    if not camera_cut_section:
                        raise RuntimeError("Failed to create camera cut section")

                    # Set the section range to cover the entire sequence
                    try:
                        camera_cut_section.set_range(0, total_frames)
                        logger.info(f"✓ Set section range: 0-{total_frames}")
                    except Exception as e:
                        logger.warning(f"Could not set section range: {e}")

                    # Bind the camera to the section
                    # Note: We bind to the actor binding; UE will use its camera component.
                    _bind_camera_to_cut_section(camera_cut_section, sequence, movie_scene, camera_binding)

                except Exception as e:
                    logger.warning(f"Failed to add camera cuts: {e}")
                    traceback.print_exc()

            if write_transform_keys:
                if not actor_binding:
                    logger.warning("write_transform_keys=true but no actor binding was created")
                else:
                    logger.info("Adding transform keys to actor binding...")
                    try:
                        # 如果启用了camera_pitch_from_slope，保留pitch值
                        camera_pitch_from_slope = bool(sequence_config.get("camera_pitch_from_slope", False))
                        max_pitch_rate = float(sequence_config.get("max_pitch_rate_deg_per_sec", 20.0))
                        _sanitize_rotation_keys(transform_keys_cfg, force_zero_pitch_roll, max_yaw_rate_deg_per_sec, preserve_pitch=camera_pitch_from_slope, max_pitch_rate_deg_per_sec=max_pitch_rate)
                        _write_transform_keys(actor_binding, int(fps), int(total_frames), transform_keys_cfg, transform_key_interp)
                    except Exception as e:
                        logger.warning(f"Failed to write transform keys: {e}")
                        traceback.print_exc()
            
            # Save asset
            _save_asset(sequence)
            
            # 记录成功生成的sequence
            completed_sequences.append(
                {
                    "name": sequence_name,
                    "path": asset_path,
                    "seed": actual_seed if nav_roam_enabled else None,
                }
            )
            
            logger.info(f"✓ Sequence {batch_idx + 1}/{batch_count} completed")
            
        except Exception as e:
            logger.error(f"in batch {batch_idx + 1}: {e}")
            traceback.print_exc()
            # 继续下一个批次，不中断整个任务
            continue
    
    return completed_sequences


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

    output_dir = job_config.output_dir
    batch_count = int(job_config.sequence_count)
    actor_blueprint_class_path = job_config.actor_blueprint_class_path
    spawn_at_startpoint = bool(job_config.spawn_at_startpoint)
    nav_roam_cfg = job_config.nav_roam
    nav_roam_enabled = job_config.nav_roam_enabled
    force_zero_pitch_roll = bool(job_config.force_zero_pitch_roll)
    max_yaw_rate_deg_per_sec = job_config.max_yaw_rate_deg_per_sec
    base_write_transform_keys = bool(job_config.write_transform_keys)
    base_transform_keys_cfg = job_config.transform_keys
    base_transform_key_interp = job_config.transform_key_interp

    spawn_location_cfg = job_config.spawn_location or {}
    spawn_rotation_cfg = job_config.spawn_rotation or {}
    spawn_location = unreal.Vector(
        _as_float(spawn_location_cfg.get("x", 0.0)),
        _as_float(spawn_location_cfg.get("y", 0.0)),
        _as_float(spawn_location_cfg.get("z", 0.0)),
    )
    spawn_rotation = unreal.Rotator(
        _as_float(spawn_rotation_cfg.get("pitch", 0.0)),
        _as_float(spawn_rotation_cfg.get("yaw", 0.0)),
        _as_float(spawn_rotation_cfg.get("roll", 0.0)),
    )

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
    if nav_roam_enabled:
        logger.info("NavRoam:  enabled")

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
            spawn_at_startpoint=spawn_at_startpoint,
            nav_roam_cfg=nav_roam_cfg,
            nav_roam_enabled=nav_roam_enabled,
            force_zero_pitch_roll=force_zero_pitch_roll,
            max_yaw_rate_deg_per_sec=max_yaw_rate_deg_per_sec,
            base_write_transform_keys=base_write_transform_keys,
            base_transform_keys_cfg=base_transform_keys_cfg,
            base_transform_key_interp=base_transform_key_interp,
            spawn_location=spawn_location,
            spawn_rotation=spawn_rotation,
            sequence_config=sequence_config,
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