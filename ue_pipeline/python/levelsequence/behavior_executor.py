import math
import random
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import unreal

from logger import logger
from .nav_utils import (
    distance_cm,
    find_path_points,
    project_to_nav,
    random_reachable_point,
    find_connected_navmesh_start_point,
)

# Try to import connectivity analysis (optional)
try:
    from .navmesh_connectivity import get_spawn_point_with_connectivity
    NAVMESH_CONNECTIVITY_AVAILABLE = True
except ImportError:
    get_spawn_point_with_connectivity = None
    NAVMESH_CONNECTIVITY_AVAILABLE = False


class BehaviorType(Enum):
    """Available behavior types for sequence generation."""
    RANDOM_ROAM = "random_roam"
    TRANSLATE_FORWARD = "translate_forward"
    TRANSLATE_BACKWARD = "translate_backward"
    TRANSLATE_LEFT = "translate_left"
    TRANSLATE_RIGHT = "translate_right"
    IDLE = "idle"
    ROTATE = "rotate"
    ROTATE_PITCH = "rotate_pitch"


class BehaviorContext:
    """Context maintaining current state during behavior execution."""
    
    def __init__(
        self,
        position: unreal.Vector,
        yaw: float,
        speed_cm_per_sec: float,
        fps: int,
    ):
        self.position = position
        self.yaw = yaw  # Current camera yaw in degrees
        self.speed_cm_per_sec = speed_cm_per_sec
        self.fps = fps
        self.accumulated_time_sec = 0.0
        self.accumulated_frames = 0
    
    def update(self, new_position: unreal.Vector, new_yaw: float, duration_frames: int):
        """Update context after behavior execution."""
        self.position = new_position
        self.yaw = new_yaw
        self.accumulated_frames += duration_frames
        self.accumulated_time_sec = self.accumulated_frames / self.fps


class BehaviorResult:
    """Result from executing a single behavior."""
    
    def __init__(
        self,
        behavior_type: BehaviorType,
        points: List[unreal.Vector],
        yaws: List[float],
        duration_frames: int,
        metadata: Optional[Dict[str, Any]] = None,
        pitches: Optional[List[float]] = None,
    ):
        self.behavior_type = behavior_type
        self.points = points
        self.yaws = yaws
        self.pitches = pitches if pitches is not None else [0.0] * len(points)
        self.duration_frames = duration_frames
        self.metadata = metadata or {}
    
    @property
    def is_valid(self) -> bool:
        """Check if behavior produced valid results."""
        return len(self.points) > 0 and len(self.yaws) > 0


def _calculate_direction_vector(yaw_deg: float, direction: str) -> Tuple[float, float]:
    """
    Calculate direction vector based on yaw and direction type.
    
    Args:
        yaw_deg: Current yaw angle in degrees
        direction: One of "forward", "backward", "left", "right"
    
    Returns:
        Tuple of (x, y) direction vector components
    """
    # Convert yaw to radians
    # Unreal yaw: 0=+X, 90=+Y
    base_angle = math.radians(yaw_deg)
    
    if direction == "forward":
        angle = base_angle
    elif direction == "backward":
        angle = base_angle + math.pi
    elif direction == "left":
        angle = base_angle + math.pi / 2
    elif direction == "right":
        angle = base_angle - math.pi / 2
    else:
        raise ValueError(f"Invalid direction: {direction}")
    
    return math.cos(angle), math.sin(angle)


def _execute_translate(
    context: BehaviorContext,
    direction: str,
    nav: Any,
    world: Any,
    cfg: Dict[str, Any],
) -> BehaviorResult:
    """
    Execute translate behavior in specified direction.
    
    Uses raycast to detect obstacles and stops before collision.
    If obstacle is too close (<50cm), returns empty result (considered complete).
    
    Args:
        context: Current behavior context
        direction: "forward", "backward", "left", "right"
        nav: Navigation system
        world: World context
        cfg: Configuration dict
    
    Returns:
        BehaviorResult with translation path or empty if blocked
    """
    behavior_map = {
        "forward": BehaviorType.TRANSLATE_FORWARD,
        "backward": BehaviorType.TRANSLATE_BACKWARD,
        "left": BehaviorType.TRANSLATE_LEFT,
        "right": BehaviorType.TRANSLATE_RIGHT,
    }
    behavior_type = behavior_map[direction]
    
    # Configuration
    max_translate_distance_cm = float(cfg.get("max_translate_distance_cm", 500.0))
    min_translate_distance_cm = float(cfg.get("min_translate_distance_cm", 50.0))
    safety_margin_cm = 20.0
    
    # Calculate direction vector
    dir_x, dir_y = _calculate_direction_vector(context.yaw, direction)
    
    # Calculate desired endpoint
    desired_end = unreal.Vector(
        context.position.x + dir_x * max_translate_distance_cm,
        context.position.y + dir_y * max_translate_distance_cm,
        context.position.z,
    )
    
    # Raycast to detect obstacles
    try:
        nav_system = unreal.NavigationSystemV1.get_navigation_system(world)
        if nav_system is None:
            logger.warning(f"[Behavior] {behavior_type.value}: NavigationSystem not available")
            return BehaviorResult(behavior_type, [], [], 0.0)
        
        hit_location = unreal.NavigationSystemV1.navigation_raycast(
            world_context_object=world,
            ray_start=context.position,
            ray_end=desired_end,
            filter_class=None,
            querier=None,
        )
        
        # Determine actual travel distance
        if hit_location is None:
            # Path is clear
            actual_distance = max_translate_distance_cm
            end_point = desired_end
        else:
            # Obstacle detected
            hit_dist = distance_cm(context.position, hit_location)
            if hit_dist < min_translate_distance_cm:
                logger.info(f"[Behavior] {behavior_type.value}: obstacle too close ({hit_dist:.0f}cm), skipping")
                return BehaviorResult(behavior_type, [], [], 0.0, {"reason": "obstacle_too_close"})
            
            # Stop before obstacle
            actual_distance = max(min_translate_distance_cm, hit_dist - safety_margin_cm)
            end_point = unreal.Vector(
                context.position.x + dir_x * actual_distance,
                context.position.y + dir_y * actual_distance,
                context.position.z,
            )
        
        # Project endpoint to NavMesh
        end_point = project_to_nav(nav, world, end_point)
        
        # Calculate duration in frames
        duration_sec = actual_distance / context.speed_cm_per_sec
        duration_frames = int(duration_sec * context.fps)
        
        # Generate interpolated path with exactly duration_frames points
        points = []
        for step in range(duration_frames):
            t = float(step) / float(duration_frames - 1) if duration_frames > 1 else 0.0
            interp_point = unreal.Vector(
                context.position.x + (end_point.x - context.position.x) * t,
                context.position.y + (end_point.y - context.position.y) * t,
                context.position.z + (end_point.z - context.position.z) * t,
            )
            points.append(interp_point)
        
        # Yaw stays locked during translation
        yaws = [context.yaw] * len(points)
        
        start_frame = context.accumulated_frames
        end_frame = start_frame + duration_frames
        
        logger.info(
            f"[Behavior] {behavior_type.value}: {actual_distance:.0f}cm, frames [{start_frame}-{end_frame}], "
            # f"{len(points)} points, yaw locked at {context.yaw:.1f}°\n"
            # f"  Start: pos=({points[0].x:.1f}, {points[0].y:.1f}, {points[0].z:.1f}), yaw={yaws[0]:.1f}°\n"
            # f"  End:   pos=({points[-1].x:.1f}, {points[-1].y:.1f}, {points[-1].z:.1f}), yaw={yaws[-1]:.1f}°"
        )
        
        return BehaviorResult(
            behavior_type,
            points,
            yaws,
            duration_frames,
            {"distance_cm": actual_distance, "blocked": hit_location is not None},
            pitches=[0.0] * len(points),
        )
    
    except Exception as e:
        logger.error(f"[Behavior] {behavior_type.value} failed: {e}")
        import traceback
        traceback.print_exc()
        return BehaviorResult(behavior_type, [], [], 0.0)


def _execute_roam(
    context: BehaviorContext,
    nav: Any,
    world: Any,
    cfg: Dict[str, Any],
    duration_budget_sec: float,
) -> BehaviorResult:
    
    behavior_type = BehaviorType.RANDOM_ROAM
    
    # Configuration
    min_radius_cm = float(cfg.get("min_radius_cm", 1000.0))
    max_attempts = int(cfg.get("max_random_point_tries", 20))
    min_leg_dist = float(cfg.get("min_leg_distance_cm", 300.0))
    project = bool(cfg.get("project_to_nav", True))
    
    # Try to find a valid path
    for attempt in range(max_attempts):
        try:
            # Get random reachable point
            candidate = random_reachable_point(nav, world, context.position, min_radius_cm)
            
            # Check minimum distance
            dist = distance_cm(context.position, candidate)
            if dist < min_leg_dist:
                continue
            
            # Find NavMesh path
            # start_on_nav doesn't need projection - context.position is already valid from previous behavior
            end_on_nav = project_to_nav(nav, world, candidate) if project else candidate
            
            path_points = find_path_points(nav, world, context.position, end_on_nav)
            
            if path_points and len(path_points) >= 2:
                # Calculate path distance and duration
                path_distance = sum(
                    distance_cm(path_points[i], path_points[i + 1])
                    for i in range(len(path_points) - 1)
                )
                actual_duration = path_distance / context.speed_cm_per_sec
                
                # Calculate duration in frames
                duration_frames = int(actual_duration * context.fps)
                
                # Interpolate path to generate exactly duration_frames points
                # This ensures one point per frame, eliminating resampling errors
                num_interpolated = duration_frames
                
                interpolated_points = []
                for i in range(num_interpolated):
                    t = float(i) / float(num_interpolated - 1) if num_interpolated > 1 else 0.0
                    target_dist = t * path_distance
                    
                    # Find segment containing this distance
                    accumulated_dist = 0.0
                    for seg_idx in range(len(path_points) - 1):
                        seg_dist = distance_cm(path_points[seg_idx], path_points[seg_idx + 1])
                        if accumulated_dist + seg_dist >= target_dist:
                            # Interpolate within this segment
                            local_t = (target_dist - accumulated_dist) / seg_dist if seg_dist > 0 else 0.0
                            p1 = path_points[seg_idx]
                            p2 = path_points[seg_idx + 1]
                            interp_point = unreal.Vector(
                                p1.x + (p2.x - p1.x) * local_t,
                                p1.y + (p2.y - p1.y) * local_t,
                                p1.z + (p2.z - p1.z) * local_t,
                            )
                            interpolated_points.append(interp_point)
                            break
                        accumulated_dist += seg_dist
                    else:
                        # Fallback: use last point
                        interpolated_points.append(path_points[-1])
                
                # Use interpolated points instead of raw path points
                path_points = interpolated_points
                
                # Calculate yaw for each point based on trajectory
                yaws = []
                for i in range(len(path_points)):
                    if i < len(path_points) - 1:
                        # Look towards next point
                        dx = path_points[i + 1].x - path_points[i].x
                        dy = path_points[i + 1].y - path_points[i].y
                        yaw = math.degrees(math.atan2(dy, dx))
                    else:
                        # Last point: use previous yaw
                        yaw = yaws[-1] if yaws else context.yaw
                    yaws.append(yaw)
                
                # Calculate duration in frames
                duration_frames = int(actual_duration * context.fps)
                start_frame = context.accumulated_frames
                end_frame = start_frame + duration_frames
                logger.info(
                    f"[Behavior] {behavior_type.value}: {path_distance:.0f}cm, frames [{start_frame}-{end_frame}], "
                    f"{len(path_points)} points, yaw follows trajectory\n"
                    f"  Start: pos=({path_points[0].x:.1f}, {path_points[0].y:.1f}, {path_points[0].z:.1f}), yaw={yaws[0]:.1f}°\n"
                    f"  End:   pos=({path_points[-1].x:.1f}, {path_points[-1].y:.1f}, {path_points[-1].z:.1f}), yaw={yaws[-1]:.1f}°"
                )
                
                return BehaviorResult(
                    behavior_type,
                    path_points,
                    yaws,
                    duration_frames,
                    {"distance_cm": path_distance, "attempts": attempt + 1},
                    pitches=[0.0] * len(path_points),
                )
        
        except Exception as e:
            if attempt < 3:
                logger.warning(f"[Behavior] {behavior_type.value} attempt {attempt + 1} failed: {e}")
            continue
    
    logger.warning(f"[Behavior] {behavior_type.value}: failed to find valid path after {max_attempts} attempts")
    return BehaviorResult(behavior_type, [], [], 0.0)


def _execute_idle(
    context: BehaviorContext,
    duration_sec: float,
) -> BehaviorResult:
    """
    Execute idle behavior.
    
    Stays at current position, yaw remains constant.
    Simple waiting period with no movement.
    
    Args:
        context: Current behavior context
        duration_sec: Duration to remain idle
    
    Returns:
        BehaviorResult with repeated position
    """
    behavior_type = BehaviorType.IDLE
    
    # Generate repeated points for smooth timeline
    duration_frames = int(duration_sec * context.fps)
    num_points = max(2, duration_frames // 30)  # ~30 frames per point
    points = [context.position] * num_points
    yaws = [context.yaw] * num_points
    
    start_frame = context.accumulated_frames
    end_frame = start_frame + duration_frames
    logger.info(
        f"[Behavior] {behavior_type.value}: frames [{start_frame}-{end_frame}], {num_points} points, "
        f"position fixed, yaw={context.yaw:.1f}°\n"
        f"  Start: pos=({points[0].x:.1f}, {points[0].y:.1f}, {points[0].z:.1f}), yaw={yaws[0]:.1f}°\n"
        f"  End:   pos=({points[-1].x:.1f}, {points[-1].y:.1f}, {points[-1].z:.1f}), yaw={yaws[-1]:.1f}°"
    )
    
    return BehaviorResult(
        behavior_type,
        points,
        yaws,
        duration_frames,
        {},
        pitches=[0.0] * num_points,
    )


def _execute_rotate(
    context: BehaviorContext,
    angle_deg: float,
    cfg: Dict[str, Any],
    rotate_axis: str = "yaw",
) -> BehaviorResult:
    """
    Execute rotate behavior.
    
    Rotates in place by specified angle at configured speed.
    Position remains fixed, only rotation changes.
    
    Args:
        context: Current behavior context
        angle_deg: Angle to rotate (positive=CCW, negative=CW)
        cfg: Configuration dict
        rotate_axis: "yaw" for horizontal rotation, "pitch" for vertical rotation
    
    Returns:
        BehaviorResult with rotation sequence
    """
    if rotate_axis == "pitch":
        behavior_type = BehaviorType.ROTATE_PITCH
    else:
        behavior_type = BehaviorType.ROTATE
    
    # Configuration
    rotate_speed_deg_per_sec = float(cfg.get("rotate_speed_deg_per_sec", 30.0))
    
    # Calculate duration based on angle and speed
    duration_sec = abs(angle_deg) / rotate_speed_deg_per_sec
    duration_frames = int(duration_sec * context.fps)
    
    # Generate rotation keyframes
    num_points = max(2, duration_frames // 15)  # ~15 frames per point
    points = [context.position] * num_points
    
    if rotate_axis == "pitch":
        # Pitch rotation: yaw stays constant, pitch changes
        yaws = [context.yaw] * num_points
        start_pitch = 0.0  # Assuming camera starts at level
        end_pitch = angle_deg
        
        pitches = []
        for i in range(num_points):
            t = float(i) / float(num_points - 1) if num_points > 1 else 0.0
            pitch = start_pitch + (end_pitch - start_pitch) * t
            pitches.append(pitch)
        
        start_frame = context.accumulated_frames
        end_frame = start_frame + duration_frames
        logger.info(
            f"[Behavior] {behavior_type.value}: {angle_deg:+.1f}°, frames [{start_frame}-{end_frame}], "
            f"{num_points} points, pitch {start_pitch:.1f}° → {end_pitch:.1f}°\n"
            f"  Start: pos=({points[0].x:.1f}, {points[0].y:.1f}, {points[0].z:.1f}), yaw={yaws[0]:.1f}°, pitch={pitches[0]:.1f}°\n"
            f"  End:   pos=({points[-1].x:.1f}, {points[-1].y:.1f}, {points[-1].z:.1f}), yaw={yaws[-1]:.1f}°, pitch={pitches[-1]:.1f}°"
        )
        
        return BehaviorResult(
            behavior_type,
            points,
            yaws,
            duration_frames,
            {"angle_deg": angle_deg, "speed_deg_per_sec": rotate_speed_deg_per_sec, "axis": "pitch"},
            pitches=pitches,
        )
    else:
        # Yaw rotation: pitch stays at 0, yaw changes
        start_yaw = context.yaw
        end_yaw = context.yaw + angle_deg
        
        yaws = []
        for i in range(num_points):
            t = float(i) / float(num_points - 1) if num_points > 1 else 0.0
            yaw = start_yaw + (end_yaw - start_yaw) * t
            yaws.append(yaw)
        
        pitches = [0.0] * num_points
        
        start_frame = context.accumulated_frames
        end_frame = start_frame + duration_frames
        logger.info(
            f"[Behavior] {behavior_type.value}: {angle_deg:+.1f}°, frames [{start_frame}-{end_frame}], "
            f"{num_points} points, yaw {start_yaw:.1f}° → {end_yaw:.1f}°\n"
            f"  Start: pos=({points[0].x:.1f}, {points[0].y:.1f}, {points[0].z:.1f}), yaw={yaws[0]:.1f}°, pitch={pitches[0]:.1f}°\n"
            f"  End:   pos=({points[-1].x:.1f}, {points[-1].y:.1f}, {points[-1].z:.1f}), yaw={yaws[-1]:.1f}°, pitch={pitches[-1]:.1f}°"
        )
        
        return BehaviorResult(
            behavior_type,
            points,
            yaws,
            duration_frames,
            {"angle_deg": angle_deg, "speed_deg_per_sec": rotate_speed_deg_per_sec, "axis": "yaw"},
            pitches=pitches,
        )


def _select_random_behavior(cfg: Dict[str, Any]) -> BehaviorType:
    """
    Select random behavior based on configured weights.
    
    Args:
        cfg: Configuration dict with optional behavior_weights
    
    Returns:
        Randomly selected BehaviorType
    """
    # Default weights if not specified in config
    default_weights = {
        "random_roam": 0.6,
        "translate_forward": 0.1,
        "translate_backward": 0.1,
        "translate_left": 0.05,
        "translate_right": 0.05,
        "idle": 0.05,
        "rotate": 0.05,
        "rotate_pitch": 0.0,
    }
    
    # Get weights from config, fallback to defaults
    config_weights = cfg.get("behavior_weights", default_weights)
    
    # Map string keys to BehaviorType enum
    behavior_type_map = {
        "random_roam": BehaviorType.RANDOM_ROAM,
        "translate_forward": BehaviorType.TRANSLATE_FORWARD,
        "translate_backward": BehaviorType.TRANSLATE_BACKWARD,
        "translate_left": BehaviorType.TRANSLATE_LEFT,
        "translate_right": BehaviorType.TRANSLATE_RIGHT,
        "idle": BehaviorType.IDLE,
        "rotate": BehaviorType.ROTATE,
        "rotate_pitch": BehaviorType.ROTATE_PITCH,
    }
    
    # Build weighted list
    behaviors = []
    weights = []
    
    for key, behavior_type in behavior_type_map.items():
        weight = config_weights.get(key, default_weights.get(key, 0.0))
        behaviors.append(behavior_type)
        weights.append(weight)
    
    # Normalize weights
    total = sum(weights)
    if total <= 0:
        logger.warning("Total behavior weights is 0, using equal weights")
        weights = [1.0] * len(behaviors)
        total = len(behaviors)
    
    weights = [w / total for w in weights]
    
    # Random selection
    r = random.random()
    cumsum = 0.0
    for behavior, weight in zip(behaviors, weights):
        cumsum += weight
        if r <= cumsum:
            return behavior
    
    return BehaviorType.RANDOM_ROAM  # Fallback


def generate_behavior_sequence(
    nav: Any,
    world: Any,
    cfg: Dict[str, Any],
    map_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate navigation path using behavior-based simulation.
    
    Executes random behaviors sequentially until target duration is reached.
    Each behavior runs to completion before transitioning to the next.
    
    Args:
        nav: Navigation system
        world: World context
        cfg: Configuration dict with nav_roam and sequence settings
        map_path: Map path for cache naming
    
    Returns:
        Tuple of (nav_points, seed)
    """
    logger.info("========================================")
    logger.info("BEHAVIOR-BASED SEQUENCE GENERATION")
    logger.info("========================================")
    
    # Extract configuration
    parent_cfg = cfg.get("_parent_config", {})
    target_duration_sec = float(parent_cfg.get("duration_seconds", 60.0))
    speed_cm_per_sec = float(parent_cfg.get("fixed_speed_cm_per_sec", 150.0))
    fps = int(parent_cfg.get("fps", 30))
    
    # Pre-calculate total frames
    target_total_frames = int(target_duration_sec * fps)
    
    # Behavior minimum durations
    min_roam_duration = float(cfg.get("min_roam_duration_sec", 3.0))
    min_translate_duration = float(cfg.get("min_translate_duration_sec", 1.0))
    min_idle_duration = float(cfg.get("min_idle_duration_sec", 1.0))
    
    # Rotate angle range
    rotate_angle_range = cfg.get("rotate_angle_range", [-90, 90])
    
    # Seed handling
    seed_cfg = cfg.get("seed", None)
    actual_seed: Optional[int] = None
    if seed_cfg is not None:
        try:
            seed_val = int(seed_cfg)
            if seed_val == -1:
                random.seed()
                actual_seed = random.randint(0, 999999)
                random.seed(actual_seed)
                logger.info(f"Seed: {actual_seed} (random)")
            else:
                actual_seed = seed_val
                random.seed(actual_seed)
                logger.info(f"Seed: {actual_seed}")
        except Exception as e:
            logger.warning(f"Failed to set seed: {e}")
    
    # Initialize spawn point
    use_connectivity_analysis = bool(cfg.get("use_connectivity_analysis", True))
    if use_connectivity_analysis and NAVMESH_CONNECTIVITY_AVAILABLE:
        try:
            origin = get_spawn_point_with_connectivity(nav, world, map_path, cfg)
            logger.info(f"Spawn point (connectivity): ({origin.x:.2f}, {origin.y:.2f}, {origin.z:.2f})")
        except Exception as e:
            logger.warning(f"Connectivity analysis failed: {e}, using legacy method")
            origin = find_connected_navmesh_start_point(nav, world, max_attempts=10)
    else:
        origin = find_connected_navmesh_start_point(nav, world, max_attempts=10)
    
    # Initialize context
    context = BehaviorContext(
        position=origin,
        yaw=0.0,  # Initial yaw
        speed_cm_per_sec=speed_cm_per_sec,
        fps=fps,
    )
    
    logger.info(f"Target: {target_total_frames} frames ({target_duration_sec:.1f}s) @ {speed_cm_per_sec:.0f}cm/s")
    logger.info("========================================")
    
    # Collect all points and yaws (start empty, behaviors will populate from frame 0)
    all_points = []
    all_yaws = []
    all_pitches = []
    
    # Track behavior segments for proper interpolation downstream
    behavior_segments = []  # List of {type, start_idx, end_idx}
    
    behavior_count = 0
    consecutive_failures = 0
    max_consecutive_failures = 5
    
    # Main behavior loop
    while context.accumulated_frames < target_total_frames:
        # Select random behavior
        behavior_type = _select_random_behavior(cfg)
        
        # Execute behavior
        result = None
        
        if behavior_type == BehaviorType.RANDOM_ROAM:
            remaining_frames = target_total_frames - context.accumulated_frames
            remaining_time = remaining_frames / fps
            budget = max(min_roam_duration, min(remaining_time, 10.0))  # Cap at 10s per roam
            result = _execute_roam(context, nav, world, cfg, budget)
        
        elif behavior_type in [
            BehaviorType.TRANSLATE_FORWARD,
            BehaviorType.TRANSLATE_BACKWARD,
            BehaviorType.TRANSLATE_LEFT,
            BehaviorType.TRANSLATE_RIGHT,
        ]:
            direction_map = {
                BehaviorType.TRANSLATE_FORWARD: "forward",
                BehaviorType.TRANSLATE_BACKWARD: "backward",
                BehaviorType.TRANSLATE_LEFT: "left",
                BehaviorType.TRANSLATE_RIGHT: "right",
            }
            result = _execute_translate(context, direction_map[behavior_type], nav, world, cfg)
        
        elif behavior_type == BehaviorType.IDLE:
            remaining_frames = target_total_frames - context.accumulated_frames
            remaining_time = remaining_frames / fps
            duration = max(min_idle_duration, min(remaining_time, 3.0))  # Cap at 3s per idle
            result = _execute_idle(context, duration)
        
        elif behavior_type == BehaviorType.ROTATE:
            angle = random.uniform(rotate_angle_range[0], rotate_angle_range[1])
            result = _execute_rotate(context, angle, cfg, rotate_axis="yaw")
        
        elif behavior_type == BehaviorType.ROTATE_PITCH:
            # Get pitch angle range from config
            rotate_pitch_range = cfg.get("rotate_pitch_angle_range", [-30, 30])
            pitch_angle = random.uniform(rotate_pitch_range[0], rotate_pitch_range[1])
            result = _execute_rotate(context, pitch_angle, cfg, rotate_axis="pitch")
        
        # Process result
        if result and result.is_valid:
            # Check if adding this behavior would exceed target frames
            remaining_frames = target_total_frames - context.accumulated_frames
            
            if remaining_frames <= 0:
                # Already reached target, stop
                break
            
            # Truncate behavior if it exceeds remaining frames
            actual_frames_to_add = min(result.duration_frames, remaining_frames)
            points_to_add = result.points[:actual_frames_to_add]
            yaws_to_add = result.yaws[:actual_frames_to_add]
            pitches_to_add = result.pitches[:actual_frames_to_add]
            
            # Record segment start index
            segment_start_idx = len(all_points)
            
            # Don't skip first point - we need exact frame count matching point count
            all_points.extend(points_to_add)
            all_yaws.extend(yaws_to_add)
            all_pitches.extend(pitches_to_add)
            
            # Record segment end index and metadata
            segment_end_idx = len(all_points) - 1
            behavior_segments.append({
                "type": result.behavior_type.value,
                "start_idx": segment_start_idx,
                "end_idx": segment_end_idx,
                "start_frame": context.accumulated_frames,
                "end_frame": context.accumulated_frames + actual_frames_to_add,
            })
            
            # Update context with actual frames added
            context.update(
                points_to_add[-1],
                yaws_to_add[-1],
                actual_frames_to_add
            )
            
            behavior_count += 1
            consecutive_failures = 0
            
            # If we truncated this behavior, we've reached the target
            if actual_frames_to_add < result.duration_frames:
                logger.info(f"[Behavior] Truncated last behavior to fit target frames")
                break
        else:
            # Behavior failed or returned empty (e.g., translate blocked)
            consecutive_failures += 1
            logger.warning(f"[Behavior] {behavior_type.value} returned empty result ({consecutive_failures}/{max_consecutive_failures})")
            
            if consecutive_failures >= max_consecutive_failures:
                logger.error("Too many consecutive behavior failures, stopping generation")
                break
            
            # Try a different behavior on next iteration
            continue
    
    logger.info(f" Behavior sequence completed")

    return {
        "points": all_points,
        "yaws": all_yaws,
        "pitches": all_pitches,
        "seed": actual_seed,
        "behavior_count": behavior_count,
        "behavior_segments": behavior_segments,
    }
