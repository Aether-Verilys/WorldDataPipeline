import math
import random
import time
import traceback
import unreal
import ue_api


def call_maybe(obj, method_names, *args):
    last_err = None
    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                return fn(*args)
            except Exception as e:
                last_err = e
    if last_err:
        raise last_err
    raise AttributeError(f"None of these methods exist: {method_names}")


def distance_cm(a: unreal.Vector, b: unreal.Vector) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return float(math.sqrt(dx * dx + dy * dy + dz * dz))


def get_nav_system(world):
    nav_cls = getattr(unreal, "NavigationSystemV1", None)
    if not nav_cls:
        raise RuntimeError("NavigationSystemV1 not available")

    for name in ("get_current", "get_navigation_system", "get_default_nav_system"):
        getter = getattr(nav_cls, name, None)
        if callable(getter):
            try:
                nav = getter(world)
                if nav:
                    return nav
            except Exception:
                pass

    # Some versions allow calling static blueprint-style functions directly
    return nav_cls


def project_to_nav(nav, world, point: unreal.Vector) -> unreal.Vector:
    candidates = [
        (nav, ["project_point_to_navigation", "k2_project_point_to_navigation"]),
        (getattr(unreal, "NavigationSystemV1", object), ["project_point_to_navigation", "k2_project_point_to_navigation"]),
    ]
    arg_variants = [
        (world, point),
        (world, point, None),
        (world, point, None, None),
    ]
    for target, method_names in candidates:
        for args in arg_variants:
            try:
                result = call_maybe(target, method_names, *args)
            except Exception:
                continue
            if isinstance(result, tuple) and len(result) >= 2:
                success, projected = result[0], result[1]
                if success and isinstance(projected, unreal.Vector):
                    return projected
            if isinstance(result, unreal.Vector):
                return result
    return point


def random_reachable_point(nav, world, origin: unreal.Vector, radius_cm: float) -> unreal.Vector:
    """
    Get random reachable point in NavMesh radius.
    Returns a random navigable point within radius_cm of origin.
    """
    result = nav.get_random_reachable_point_in_radius(world, origin, radius_cm)
    
    if isinstance(result, unreal.Vector):
        return result
    elif isinstance(result, tuple) and len(result) >= 2:
        success, point = result[0], result[1]
        if success and isinstance(point, unreal.Vector):
            return point
    
    raise RuntimeError(f"No reachable NavMesh point found near ({origin.x:.2f}, {origin.y:.2f}, {origin.z:.2f}) within {radius_cm:.0f}cm")


def get_navmesh_bounds(world) -> tuple:
    try:
        actor_subsystem = ue_api.get_actor_subsystem()
        actors = actor_subsystem.get_all_level_actors()
        navmesh_bounds_cls = getattr(unreal, "NavMeshBoundsVolume", None)
        if not navmesh_bounds_cls:
            print("[WorkerCreateSequence] WARNING: NavMeshBoundsVolume class not found")
            return None

        bounds_actors = [a for a in actors if isinstance(a, navmesh_bounds_cls)]
        if not bounds_actors:
            print("[WorkerCreateSequence] WARNING: No NavMeshBoundsVolume actors found in level")
            return None

        print(f"[WorkerCreateSequence] Found {len(bounds_actors)} NavMeshBoundsVolume(s)")

        bounds_actor = bounds_actors[0]
        print(f"[WorkerCreateSequence] Using NavMeshBoundsVolume: {bounds_actor.get_name()}")

        # NavMeshBoundsVolume 的大小由中心位置和缩放决定
        # 默认基础 extent 是 100cm，实际 extent = scale * 100
        # 总大小 = extent * 2
        # 例如: scale=(5,5,10) -> extent=(500,500,1000) -> 总大小=1000x1000x2000 cm
        try:
            location = bounds_actor.get_actor_location()
            scale = bounds_actor.get_actor_scale3d()
            # NavMeshBoundsVolume 默认基础 extent = 100cm
            default_extent = 100.0
            extent = unreal.Vector(
                scale.x * default_extent,
                scale.y * default_extent,
                scale.z * default_extent,
            )
            print(f"[WorkerCreateSequence] ✓ NavMesh bounds: center=({location.x:.2f}, {location.y:.2f}, {location.z:.2f}), scale=({scale.x:.2f}, {scale.y:.2f}, {scale.z:.2f})")
            print(f"[WorkerCreateSequence]   Extent: ({extent.x:.2f}, {extent.y:.2f}, {extent.z:.2f}) cm, Size: ({extent.x*2:.2f}, {extent.y*2:.2f}, {extent.z*2:.2f}) cm")
            return (location, extent)
        except Exception as e:
            print(f"[WorkerCreateSequence]   Failed to get NavMesh bounds: {e}")

        return None
    except Exception as e:
        print(f"[WorkerCreateSequence] ERROR: Failed to get NavMesh bounds: {e}")
        traceback.print_exc()
        return None


def find_connected_navmesh_start_point(nav, world, max_attempts: int = 10) -> unreal.Vector:
    """
    Get random points directly from NavMesh - randomly distributed across entire volume.
    Returns 5 sample points for analysis, then selects the first one as spawn point.
    """
    bounds = get_navmesh_bounds(world)

    if bounds is None:
        print("[NavMesh] WARNING: No NavMeshBoundsVolume found, using fallback")
        center = unreal.Vector(0, 0, 0)
        extent = unreal.Vector(10000.0, 10000.0, 1000.0)
    else:
        center, extent = bounds
        print(f"[NavMesh] Volume: center=({center.x:.0f}, {center.y:.0f}, {center.z:.0f}), extent=({extent.x:.0f}, {extent.y:.0f}, {extent.z:.0f})cm")

    # Search radius: 80% of volume extent
    search_radius = max(extent.x, extent.y) * 0.8
    print(f"[NavMesh] Sampling 5 random points (search radius={search_radius:.0f}cm per attempt)...")
    
    random_points = []
    
    for i in range(5):
        found = False
        # Try up to 5 random origins per point
        for attempt in range(5):
            try:
                # Random origin within 90% of volume bounds
                random_origin = unreal.Vector(
                    center.x + random.uniform(-extent.x * 0.9, extent.x * 0.9),
                    center.y + random.uniform(-extent.y * 0.9, extent.y * 0.9),
                    center.z + random.uniform(-extent.z * 0.5, extent.z * 0.5)
                )
                
                random_point = random_reachable_point(nav, world, random_origin, search_radius)
                random_points.append(random_point)
                
                distance_from_center = distance_cm(center, random_point)
                print(f"[NavMesh] Point {i+1}: origin({random_origin.x:7.1f}, {random_origin.y:7.1f}, {random_origin.z:6.1f}) -> result({random_point.x:7.1f}, {random_point.y:7.1f}, {random_point.z:6.1f})  Distance: {distance_from_center:6.0f}cm")
                found = True
                break
            except Exception:
                if attempt == 4:
                    # Last attempt - try fallback from center
                    try:
                        fallback_point = random_reachable_point(nav, world, center, search_radius * 1.5)
                        random_points.append(fallback_point)
                        print(f"[NavMesh] Point {i+1}: ({fallback_point.x:7.1f}, {fallback_point.y:7.1f}, {fallback_point.z:6.1f})  [FALLBACK]")
                        found = True
                    except Exception:
                        pass
                continue
        
        if not found:
            print(f"[NavMesh] Point {i+1}: Failed to find point")
    
    if not random_points:
        raise RuntimeError("Failed to find any NavMesh points - NavMesh may not be baked")
    
    selected = random_points[0]
    print(f"[NavMesh] ✓ Selected spawn point: ({selected.x:.1f}, {selected.y:.1f}, {selected.z:.1f})")
    return selected


def find_path_points(nav, world, start: unreal.Vector, end: unreal.Vector):
    candidates = [
        (nav, ["find_path_to_location_synchronously"]),
        (getattr(unreal, "NavigationSystemV1", object), ["find_path_to_location_synchronously"]),
    ]
    nav_path = None
    last_err = None
    arg_variants = [
        (world, start, end),
        (world, start, end, None),
        (world, start, end, None, None),
    ]
    for target, method_names in candidates:
        for args in arg_variants:
            try:
                nav_path = call_maybe(target, method_names, *args)
                if nav_path:
                    break
            except Exception as e:
                last_err = e
        if nav_path:
            break

    if not nav_path:
        raise RuntimeError(f"FindPathToLocationSynchronously failed: {last_err}")

    if hasattr(nav_path, "path_points"):
        pts = list(getattr(nav_path, "path_points"))
        if pts:
            return pts

    getter = getattr(nav_path, "get_path_points", None)
    if callable(getter):
        pts = list(getter())
        if pts:
            return pts

    return []


def generate_lateral_strafe(
    nav,
    world,
    origin: unreal.Vector,
    forward_direction: unreal.Vector,
    strafe_config: dict,
    project: bool = True,
) -> dict:
    """
    Generate a round-trip lateral strafe movement using navigation raycast.
    
    Uses NavigationSystemV1.navigation_raycast() to detect obstacles and adjust
    strafe distance to stop before collision.
    
    Returns a dict with:
        - strafe_points: list of points for the strafe path (origin -> strafe_point -> origin)
        - strafe_distance_cm: actual achieved strafe distance
        - strafe_time_sec: time for the entire round-trip
    """
    strafe_distance_cm = float(strafe_config.get("strafe_distance_cm", 200.0))
    strafe_direction = strafe_config.get("strafe_direction", "random").lower()
    actor_speed_cm_per_sec = float(strafe_config.get("actor_speed_cm_per_sec", 200.0))
    min_distance_threshold_cm = 50.0  # Minimum strafe distance before giving up
    safety_margin_cm = 20.0  # Stop this far before obstacle
    
    # Normalize forward direction (ignore Z)
    forward_2d = unreal.Vector(forward_direction.x, forward_direction.y, 0.0)
    forward_len = math.sqrt(forward_2d.x**2 + forward_2d.y**2)
    if forward_len < 0.001:
        # No clear forward direction, skip strafe
        return {"strafe_points": [], "strafe_distance_cm": 0.0, "strafe_time_sec": 0.0}
    
    forward_normalized = unreal.Vector(
        forward_2d.x / forward_len,
        forward_2d.y / forward_len,
        0.0
    )
    
    # Calculate perpendicular vector (90° rotation in XY plane)
    # Left: (-y, x), Right: (y, -x)
    if strafe_direction == "left":
        perpendicular = unreal.Vector(-forward_normalized.y, forward_normalized.x, 0.0)
    elif strafe_direction == "right":
        perpendicular = unreal.Vector(forward_normalized.y, -forward_normalized.x, 0.0)
    else:  # "random" or "both"
        # Randomly choose left or right
        if random.random() < 0.5:
            perpendicular = unreal.Vector(-forward_normalized.y, forward_normalized.x, 0.0)
        else:
            perpendicular = unreal.Vector(forward_normalized.y, -forward_normalized.x, 0.0)
    
    try:
        # Project origin to NavMesh
        origin_on_nav = project_to_nav(nav, world, origin) if project else origin
        
        # Calculate desired strafe endpoint
        strafe_offset = unreal.Vector(
            perpendicular.x * strafe_distance_cm,
            perpendicular.y * strafe_distance_cm,
            0.0
        )
        desired_target = unreal.Vector(
            origin_on_nav.x + strafe_offset.x,
            origin_on_nav.y + strafe_offset.y,
            origin_on_nav.z  # Keep same Z height
        )
        
        # Use navigation raycast to check if path is clear
        nav_system = unreal.NavigationSystemV1.get_navigation_system(world)
        if nav_system is None:
            print("[NavUtils] Strafe failed: NavigationSystemV1 not available")
            return {"strafe_points": [], "strafe_distance_cm": 0.0, "strafe_time_sec": 0.0}
        
        hit_location = unreal.NavigationSystemV1.navigation_raycast(
            world_context_object=world,
            ray_start=origin_on_nav,
            ray_end=desired_target,
            filter_class=None,
            querier=None
        )
        
        # Determine actual strafe target
        if hit_location is None:
            # Path is clear, use full distance
            strafe_target = desired_target
            actual_strafe_dist = strafe_distance_cm
            print(f"[NavUtils] Strafe raycast: clear path, full distance {strafe_distance_cm:.0f}cm")
        else:
            # Path blocked, use hit location minus safety margin
            hit_dist = distance_cm(origin_on_nav, hit_location)
            safe_dist = max(min_distance_threshold_cm, hit_dist - safety_margin_cm)
            
            if safe_dist < min_distance_threshold_cm:
                print(f"[NavUtils] Strafe blocked too close (hit at {hit_dist:.0f}cm), skipping")
                return {"strafe_points": [], "strafe_distance_cm": 0.0, "strafe_time_sec": 0.0}
            
            # Calculate safe target point
            scale = safe_dist / strafe_distance_cm
            strafe_target = unreal.Vector(
                origin_on_nav.x + strafe_offset.x * scale,
                origin_on_nav.y + strafe_offset.y * scale,
                origin_on_nav.z
            )
            actual_strafe_dist = safe_dist
            print(f"[NavUtils] Strafe raycast: blocked at {hit_dist:.0f}cm, using safe distance {safe_dist:.0f}cm")
        
        # Project final target to NavMesh
        if project:
            strafe_target = project_to_nav(nav, world, strafe_target)
        
        # Validate minimum distance
        final_dist = distance_cm(origin_on_nav, strafe_target)
        if final_dist < min_distance_threshold_cm:
            print(f"[NavUtils] Strafe final distance too short ({final_dist:.0f}cm), skipping")
            return {"strafe_points": [], "strafe_distance_cm": 0.0, "strafe_time_sec": 0.0}
        
        # Create linear path: origin -> strafe_target -> origin
        # Use 10-20 intermediate points for smooth animation (based on distance)
        num_steps = max(10, int(final_dist / 50.0))  # One point per ~50cm
        
        path_to_strafe = [origin_on_nav]
        for step in range(1, num_steps + 1):
            t = float(step) / float(num_steps)
            interp_point = unreal.Vector(
                origin_on_nav.x + (strafe_target.x - origin_on_nav.x) * t,
                origin_on_nav.y + (strafe_target.y - origin_on_nav.y) * t,
                origin_on_nav.z + (strafe_target.z - origin_on_nav.z) * t,
            )
            path_to_strafe.append(interp_point)
        
        # Return path (same points in reverse)
        path_from_strafe = list(reversed(path_to_strafe))
        
        # Combine paths (avoid duplicate middle point)
        round_trip_points = path_to_strafe + path_from_strafe[1:]
        
        # Calculate total distance and time
        total_strafe_distance = 0.0
        for i in range(len(round_trip_points) - 1):
            total_strafe_distance += distance_cm(round_trip_points[i], round_trip_points[i + 1])
        
        strafe_time_sec = total_strafe_distance / actor_speed_cm_per_sec
        
        print(f"[NavUtils] Strafe success: target={strafe_distance_cm:.0f}cm, actual={final_dist:.0f}cm, "
              f"path_length={total_strafe_distance:.0f}cm, time={strafe_time_sec:.2f}s")
        
        return {
            "strafe_points": round_trip_points,
            "strafe_distance_cm": final_dist,
            "strafe_time_sec": strafe_time_sec,
        }
        
    except Exception as e:
        print(f"[NavUtils] Strafe failed with exception: {e}")
        traceback.print_exc()
        return {"strafe_points": [], "strafe_distance_cm": 0.0, "strafe_time_sec": 0.0}


def subdivide_polyline(points, step_cm: float):
    if len(points) < 2:
        return points
    out = [points[0]]
    for i in range(1, len(points)):
        a = out[-1]
        b = points[i]
        seg_len = distance_cm(a, b)
        if seg_len <= step_cm:
            out.append(b)
            continue

        steps = max(1, int(math.floor(seg_len / step_cm)))
        for s in range(1, steps + 1):
            t = min(1.0, (s * step_cm) / seg_len)
            p = unreal.Vector(
                a.x + (b.x - a.x) * t,
                a.y + (b.y - a.y) * t,
                a.z + (b.z - a.z) * t,
            )
            out.append(p)

        if distance_cm(out[-1], b) > 0.01:
            out.append(b)
    return out


def resample_by_distance(points, sample_count: int):
    if len(points) < 2:
        return points
    if sample_count <= 2:
        return [points[0], points[-1]]

    dists = [0.0]
    for i in range(1, len(points)):
        dists.append(dists[-1] + distance_cm(points[i - 1], points[i]))
    total = dists[-1]
    if total <= 0.001:
        return [points[0]] * sample_count

    out = [points[0]]
    step = total / float(sample_count - 1)
    target = step
    seg = 1

    while len(out) < sample_count - 1:
        while seg < len(points) and dists[seg] < target:
            seg += 1
        if seg >= len(points):
            break

        d0 = dists[seg - 1]
        d1 = dists[seg]
        t = 0.0 if d1 <= d0 else (target - d0) / (d1 - d0)
        a = points[seg - 1]
        b = points[seg]
        p = unreal.Vector(
            a.x + (b.x - a.x) * t,
            a.y + (b.y - a.y) * t,
            a.z + (b.z - a.z) * t,
        )
        out.append(p)
        target += step

    out.append(points[-1])
    return out


def build_multi_leg_nav_path(nav, world, cfg: dict, map_path: str | None = None):
    """
    Generate multi-leg navigation path on NavMesh.
    
    This function will attempt to use connectivity analysis if enabled in config,
    otherwise falls back to the legacy random search method.
    
    Args:
        nav: NavigationSystemV1 instance
        world: World context
        cfg: Configuration dict with nav_roam settings
        map_path: Map path for cache naming
    
    Returns:
        List of Vector points representing the navigation path
    """
    # Get duration-based configuration (from parent config)
    parent_cfg = cfg.get("_parent_config", {})
    target_duration_sec = float(parent_cfg.get("duration_seconds", 60.0))
    actor_speed_cm_per_sec = float(parent_cfg.get("fixed_speed_cm_per_sec", 150.0))
    
    max_tries = int(cfg.get("max_random_point_tries", 40))
    min_step_cm = float(cfg.get("min_segment_step_cm", 75.0))
    min_radius_cm = float(cfg.get("min_radius_cm", 1000.0))
    project = bool(cfg.get("project_to_nav", True))
    min_leg_dist = float(cfg.get("min_leg_distance_cm", 300.0))
    max_legs = int(cfg.get("max_legs", 100))  # Safety limit to prevent infinite loops

    # Get NavMesh bounds to calculate appropriate search radius
    bounds = get_navmesh_bounds(world)
    if bounds:
        center, extent = bounds
        # Use 60% of average extent as search radius, with minimum of min_radius_cm
        avg_extent = (extent.x + extent.y) / 2.0
        radius_cm = max(min_radius_cm, avg_extent * 0.6)
        print(f"[WorkerCreateSequence] Auto-calculated search radius: {radius_cm:.0f}cm ({radius_cm/100:.1f}m) based on NavMesh volume (avg_extent={avg_extent:.0f}cm, min_radius={min_radius_cm:.0f}cm)")
    else:
        # Fallback to config or default
        radius_cm = max(min_radius_cm, float(cfg.get("random_point_radius_cm", 2000.0)))
        print(f"[WorkerCreateSequence] Using fallback search radius: {radius_cm:.0f}cm (min_radius={min_radius_cm:.0f}cm)")

    # Try to use connectivity analysis if available and enabled
    use_connectivity_analysis = bool(cfg.get("use_connectivity_analysis", True))
    if use_connectivity_analysis:
        try:
            from .navmesh_connectivity import get_spawn_point_with_connectivity
            print("[WorkerCreateSequence] Using connectivity analysis for spawn point selection...")
            origin = get_spawn_point_with_connectivity(nav, world, map_path, cfg)
        except ImportError:
            print("[WorkerCreateSequence] Connectivity analysis not available, using legacy method...")
            origin = find_connected_navmesh_start_point(nav, world, max_attempts=10)
        except Exception as e:
            print(f"[WorkerCreateSequence] Connectivity analysis failed: {e}, using legacy method...")
            origin = find_connected_navmesh_start_point(nav, world, max_attempts=10)
    else:
        print("[WorkerCreateSequence] Connectivity analysis disabled, using legacy method...")
        origin = find_connected_navmesh_start_point(nav, world, max_attempts=10)

    a = project_to_nav(nav, world, origin) if project else origin
    print(f"[WorkerCreateSequence] ✓ Final start point: X={a.x:.2f}, Y={a.y:.2f}, Z={a.z:.2f}")
    print(f"[WorkerCreateSequence] NavRoam: target_duration={target_duration_sec:.1f}s, speed={actor_speed_cm_per_sec:.0f}cm/s, radius={radius_cm:.0f}cm, min_step={min_step_cm:.0f}cm")

    seed = cfg.get("seed", None)
    use_python_rng = seed is not None

    points = [a]
    current = a
    accumulated_time_sec = 0.0
    leg = 0
    last_strafe_leg = -999  # Track last leg where strafe occurred
    strafe_segments = []  # Track which point ranges are strafe movements
    
    # Extract strafe configuration
    strafe_enabled = bool(cfg.get("strafe_enabled", False))
    strafe_probability = float(cfg.get("strafe_probability", 0.2))
    strafe_min_interval_legs = int(cfg.get("strafe_min_interval_legs", 2))
    strafe_cfg = {
        "strafe_distance_cm": float(cfg.get("strafe_distance_cm", 200.0)),
        "strafe_direction": cfg.get("strafe_direction", "random"),
        "actor_speed_cm_per_sec": actor_speed_cm_per_sec,
    }
    
    while accumulated_time_sec < target_duration_sec and leg < max_legs:
        leg_pts = None
        for attempt in range(max_tries):
            try:
                if use_python_rng:
                    ang = random.uniform(-math.pi, math.pi)
                    r = random.uniform(0.25 * radius_cm, radius_cm)
                    raw = unreal.Vector(
                        current.x + math.cos(ang) * r,
                        current.y + math.sin(ang) * r,
                        current.z,
                    )
                    candidate = project_to_nav(nav, world, raw) if project else raw
                else:
                    candidate = random_reachable_point(nav, world, current, radius_cm)

                if distance_cm(current, candidate) <= min_leg_dist:
                    continue

                start_on_nav = project_to_nav(nav, world, current) if project else current
                end_on_nav = project_to_nav(nav, world, candidate) if project else candidate

                pts = find_path_points(nav, world, start_on_nav, end_on_nav)
                if pts and len(pts) >= 2:
                    leg_pts = pts
                    # Calculate path distance and time
                    leg_distance_cm = sum(distance_cm(pts[i], pts[i+1]) for i in range(len(pts)-1))
                    leg_time_sec = leg_distance_cm / actor_speed_cm_per_sec
                    print(f"[WorkerCreateSequence] NavRoam leg {leg}: path={len(pts)} points, distance={leg_distance_cm:.0f}cm ({leg_distance_cm/100:.1f}m), estimated_time={leg_time_sec:.2f}s")
                    break

                if attempt < 3:
                    print(f"[WorkerCreateSequence] WARNING: NavRoam leg {leg}: empty path from {current} to {candidate} (attempt {attempt + 1}/{max_tries}); retrying")
            except Exception:
                continue

        if not leg_pts:
            print(f"[WorkerCreateSequence] WARNING: NavRoam leg {leg}: could not find a valid path after {max_tries} attempts; stopping early")
            break

        # Calculate this leg's contribution to total time
        leg_distance_cm = sum(distance_cm(leg_pts[i], leg_pts[i+1]) for i in range(len(leg_pts)-1))
        leg_time_sec = leg_distance_cm / actor_speed_cm_per_sec
        
        # Add the leg points
        if distance_cm(points[-1], leg_pts[0]) < 0.1:
            leg_pts = leg_pts[1:]
        points.extend(leg_pts)
        current = leg_pts[-1]
        
        # Update accumulated time
        accumulated_time_sec += leg_time_sec
        leg += 1
        
        # Check if we should add a strafe movement after this leg
        if strafe_enabled and accumulated_time_sec < target_duration_sec:
            # Check interval requirement
            legs_since_last_strafe = leg - last_strafe_leg
            if legs_since_last_strafe >= strafe_min_interval_legs:
                # Roll for strafe probability
                if random.random() < strafe_probability:
                    # Calculate forward direction from this leg
                    if len(leg_pts) >= 2:
                        leg_start = leg_pts[0]
                        leg_end = leg_pts[-1]
                        forward_vec = unreal.Vector(
                            leg_end.x - leg_start.x,
                            leg_end.y - leg_start.y,
                            0.0  # Ignore Z for direction
                        )
                        
                        # Generate strafe movement
                        strafe_result = generate_lateral_strafe(
                            nav, world, current, forward_vec, strafe_cfg, project
                        )
                        
                        if strafe_result["strafe_points"]:
                            strafe_pts = strafe_result["strafe_points"]
                            strafe_time = strafe_result["strafe_time_sec"]
                            
                            # Record strafe segment metadata
                            strafe_start_idx = len(points)
                            
                            # Add strafe points (skip first if duplicate)
                            if distance_cm(points[-1], strafe_pts[0]) < 0.1:
                                strafe_pts = strafe_pts[1:]
                            
                            points.extend(strafe_pts)
                            strafe_end_idx = len(points)
                            
                            # Store strafe segment range
                            strafe_segments.append({
                                "start_idx": strafe_start_idx,
                                "end_idx": strafe_end_idx,
                                "leg": leg,
                            })
                            
                            current = strafe_pts[-1]  # Update current position
                            accumulated_time_sec += strafe_time
                            last_strafe_leg = leg
                            
                            print(f"[WorkerCreateSequence] ✓ Added strafe after leg {leg}: +{strafe_time:.2f}s (points {strafe_start_idx}-{strafe_end_idx})")
        
        print(f"[WorkerCreateSequence] NavRoam: accumulated_time={accumulated_time_sec:.2f}s / {target_duration_sec:.1f}s ({accumulated_time_sec/target_duration_sec*100:.1f}%), legs={leg}")

    points = subdivide_polyline(points, min_step_cm)
    if project:
        points = [project_to_nav(nav, world, p) for p in points]

    # Calculate final path statistics
    total_distance_cm = sum(distance_cm(points[i], points[i+1]) for i in range(len(points)-1))
    final_time_sec = total_distance_cm / actor_speed_cm_per_sec
    print(f"[WorkerCreateSequence] NavRoam complete: legs={leg}, points={len(points)}, distance={total_distance_cm:.0f}cm ({total_distance_cm/100:.1f}m), estimated_time={final_time_sec:.2f}s")
    if strafe_segments:
        print(f"[WorkerCreateSequence] NavRoam: {len(strafe_segments)} strafe segments included")
    
    # Store strafe metadata in config for downstream processing
    cfg["_strafe_segments"] = strafe_segments
    
    return points


def wait_for_navigation_ready(nav, world, timeout_seconds: float) -> None:
    """
    Wait for NavMesh to be ready, with option to force rebuild if stuck.
    """
    try:
        timeout = max(0.0, float(timeout_seconds))
    except Exception:
        timeout = 0.0
    if timeout <= 0.0:
        return

    fn = getattr(nav, "is_navigation_being_built_or_locked", None)
    if not callable(fn):
        fn = getattr(getattr(unreal, "NavigationSystemV1", None), "is_navigation_being_built_or_locked", None)
    if not callable(fn):
        return

    start_t = time.time()
    check_count = 0
    printed = False
    
    while True:
        try:
            building = bool(fn(world))
        except Exception:
            break

        if not building:
            if printed:
                print("[WorkerCreateSequence] ✓ Navigation ready")
            return

        if not printed:
            print(f"[WorkerCreateSequence] Waiting for navigation to finish building (timeout={timeout:.1f}s)...")
            printed = True
        
        check_count += 1
        elapsed = time.time() - start_t
        
        # Every 2 seconds, print status
        if check_count % 8 == 0:
            print(f"[WorkerCreateSequence] Still waiting... ({elapsed:.1f}s elapsed)")
        
        # If timeout reached, try to force rebuild
        if elapsed >= timeout:
            print(f"[WorkerCreateSequence] ⚠️ WARNING: Navigation still building after {timeout:.1f}s")
            print(f"[WorkerCreateSequence] Attempting to force rebuild...")
            
            # Try to rebuild navigation
            try:
                rebuild_fn = getattr(nav, "rebuild_all", None) or getattr(nav, "rebuild_navigation_data", None)
                if callable(rebuild_fn):
                    rebuild_fn()
                    print(f"[WorkerCreateSequence] Navigation rebuild triggered, waiting additional 5s...")
                    # Wait additional time for rebuild
                    time.sleep(5.0)
                    # Check one more time
                    if not fn(world):
                        print(f"[WorkerCreateSequence] ✓ Navigation ready after rebuild")
                        return
                    else:
                        print(f"[WorkerCreateSequence] ⚠️ Navigation still building after rebuild attempt")
            except Exception as e:
                print(f"[WorkerCreateSequence] Failed to force rebuild: {e}")
            
            print(f"[WorkerCreateSequence] Continuing anyway - NavMesh may not be fully ready")
            return

        time.sleep(0.25)

