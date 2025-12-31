import math
import os
import random
import time
import traceback
import unreal

try:
    from levelsequence import (
        find_largest_connected_region,
        select_spawn_point_from_region,
    )
    NAVMESH_CONNECTIVITY_AVAILABLE = True
except ImportError:
    NAVMESH_CONNECTIVITY_AVAILABLE = False
    find_largest_connected_region = None
    select_spawn_point_from_region = None


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
    """Get a random point that is reachable from origin (not isolated)."""
    candidates = [
        (nav, ["get_random_reachable_point_in_radius", "k2_get_random_reachable_point_in_radius"]),
        (getattr(unreal, "NavigationSystemV1", object), ["get_random_reachable_point_in_radius", "k2_get_random_reachable_point_in_radius"]),
    ]

    arg_variants = [
        (world, origin, radius_cm),
        (world, origin, radius_cm, None),
        (world, origin, radius_cm, None, None),
    ]

    last_error = None
    for target, method_names in candidates:
        for args in arg_variants:
            try:
                result = call_maybe(target, method_names, *args)
            except Exception as e:
                last_error = e
                continue
            if isinstance(result, tuple) and len(result) >= 2:
                success, point = result[0], result[1]
                if success and isinstance(point, unreal.Vector):
                    return point
            if isinstance(result, unreal.Vector):
                return result

    error_msg = f"Failed to get random reachable point from ({origin.x:.2f}, {origin.y:.2f}, {origin.z:.2f}) radius={radius_cm:.0f}cm"
    if last_error:
        error_msg += f". Last error: {last_error}"
    raise RuntimeError(error_msg)


def get_navmesh_bounds(world) -> tuple:
    """Get the bounds of the NavMesh from NavMeshBoundsVolume actors.
    Returns (center, extent) as (Vector, Vector) or None if no bounds found.
    """
    try:
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
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

        brush_comp = getattr(bounds_actor, "brush_component", None)
        if brush_comp:
            try:
                bounds_box = brush_comp.bounds
                if bounds_box:
                    origin = bounds_box.origin
                    extent = bounds_box.box_extent
                    print(f"[WorkerCreateSequence] ✓ NavMesh bounds (from BrushComponent.Bounds): center=({origin.x:.2f}, {origin.y:.2f}, {origin.z:.2f}), extent=({extent.x:.2f}, {extent.y:.2f}, {extent.z:.2f})")
                    return (origin, extent)
            except Exception as e:
                print(f"[WorkerCreateSequence]   BrushComponent.Bounds failed: {e}")

        try:
            location = bounds_actor.get_actor_location()
            scale = bounds_actor.get_actor_scale3d()
            base_extent = 200.0
            extent = unreal.Vector(
                scale.x * base_extent,
                scale.y * base_extent,
                scale.z * base_extent,
            )
            print(f"[WorkerCreateSequence] ✓ NavMesh bounds (from Actor transform): center=({location.x:.2f}, {location.y:.2f}, {location.z:.2f}), extent=({extent.x:.2f}, {extent.y:.2f}, {extent.z:.2f})")
            return (location, extent)
        except Exception as e:
            print(f"[WorkerCreateSequence]   Actor transform failed: {e}")

        return None
    except Exception as e:
        print(f"[WorkerCreateSequence] ERROR: Failed to get NavMesh bounds: {e}")
        traceback.print_exc()
        return None


def find_connected_navmesh_start_point(nav, world, max_attempts: int = 10) -> unreal.Vector:
    """Find a random point on NavMesh that is well-connected (not isolated)."""
    bounds = get_navmesh_bounds(world)

    if bounds is None:
        print("[WorkerCreateSequence] WARNING: No NavMeshBoundsVolume found, trying common locations...")
        test_origins = [
            unreal.Vector(0, 0, 0),
            unreal.Vector(0, 0, 500),
            unreal.Vector(1000, 1000, 500),
        ]
    else:
        center, extent = bounds
        test_origins = []
        for _ in range(max_attempts):
            rx = center.x + random.uniform(-extent.x * 0.8, extent.x * 0.8)
            ry = center.y + random.uniform(-extent.y * 0.8, extent.y * 0.8)
            rz = center.z
            test_origins.append(unreal.Vector(rx, ry, rz))

    for i, origin in enumerate(test_origins):
        try:
            projected = project_to_nav(nav, world, origin)
            print(f"[WorkerCreateSequence]   Testing candidate {i+1}: origin=({origin.x:.2f}, {origin.y:.2f}, {origin.z:.2f}), projected=({projected.x:.2f}, {projected.y:.2f}, {projected.z:.2f})")

            test_radius = 8000.0
            try:
                reachable = random_reachable_point(nav, world, projected, test_radius)
                print(f"[WorkerCreateSequence] ✓ Found connected start point (attempt {i+1}): X={projected.x:.2f}, Y={projected.y:.2f}, Z={projected.z:.2f}")
                print(f"[WorkerCreateSequence]   Connectivity verified: can reach ({reachable.x:.2f}, {reachable.y:.2f}, {reachable.z:.2f})")
                return projected
            except Exception as e:
                print(f"[WorkerCreateSequence]   Candidate {i+1} connectivity test failed: {e}")
                continue
        except Exception as e:
            print(f"[WorkerCreateSequence]   Candidate {i+1} projection failed: {e}")
            continue

    raise RuntimeError(f"Failed to find connected NavMesh point after {max_attempts} attempts. NavMesh may be too fragmented or non-existent.")


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


def build_multi_leg_nav_path(nav, world, cfg: dict, map_path: str | None = None, run_id: int | None = None):
    """
    Generate multi-leg navigation path on NavMesh.
    
    Args:
        nav: NavigationSystemV1 instance
        world: World context
        cfg: Configuration dict with nav_roam settings
        map_path: Map path for cache naming
        run_id: Run session identifier for cache (None = force unique cache per call)
    
    Returns:
        List of Vector points representing the navigation path
    """
    radius_cm = float(cfg.get("random_point_radius_cm", 8000.0))
    num_legs = int(cfg.get("num_legs", 6))
    max_tries = int(cfg.get("max_random_point_tries", 40))
    min_step_cm = float(cfg.get("min_segment_step_cm", 75.0))
    project = bool(cfg.get("project_to_nav", True))
    min_leg_dist = float(cfg.get("min_leg_distance_cm", 300.0))

    use_connectivity_analysis = bool(cfg.get("use_connectivity_analysis", True))
    connectivity_sample_count = cfg.get("connectivity_sample_count", None)
    connectivity_sample_density = cfg.get("connectivity_sample_density", None)

    print("[WorkerCreateSequence] Finding connected start point from NavMesh using connectivity analysis...")

    if use_connectivity_analysis and NAVMESH_CONNECTIVITY_AVAILABLE:
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cache_dir = os.path.join(os.path.dirname(script_dir), "logs")

            # Use map name + run_id for cache isolation
            map_name_for_cache = "unknown_map"
            if map_path and "/" in str(map_path):
                map_name_for_cache = str(map_path).split("/")[-1]
            
            # Use run_id to identify this execution session
            # All sequences in the same run will share this cache
            if run_id is not None:
                cache_name = f"{map_name_for_cache}_run{run_id}"
            else:
                # No run_id: use timestamp to force unique cache (never reuse)
                import time
                cache_name = f"{map_name_for_cache}_{int(time.time())}"

            sample_count_param = int(connectivity_sample_count) if connectivity_sample_count is not None else None
            density_param = float(connectivity_sample_density) if connectivity_sample_density is not None else None

            print(f"[WorkerCreateSequence] Using connectivity analysis (cache_id={cache_name}, sample_count={sample_count_param or 'auto'}, density={density_param or 'default'})")
            largest_region = find_largest_connected_region(
                nav,
                world,
                cache_name,
                cache_dir,
                sample_count=sample_count_param,
                sample_density=density_param,
                k_nearest=8,
                force_recompute=False,
            )

            seed_for_spawn = cfg.get("seed", None)
            origin = select_spawn_point_from_region(largest_region, strategy="random", seed=seed_for_spawn)
            print("[WorkerCreateSequence] ✓ Selected spawn point from largest connected region")

        except Exception as e:
            print(f"[WorkerCreateSequence] WARNING: Connectivity analysis failed: {e}")
            print(f"[WorkerCreateSequence] Falling back to legacy method...")
            origin = find_connected_navmesh_start_point(nav, world, max_attempts=10)
    else:
        if not use_connectivity_analysis:
            print("[WorkerCreateSequence] Connectivity analysis disabled in config")
        origin = find_connected_navmesh_start_point(nav, world, max_attempts=10)

    a = project_to_nav(nav, world, origin) if project else origin
    print(f"[WorkerCreateSequence] ✓ Final start point (projected to NavMesh): X={a.x:.2f}, Y={a.y:.2f}, Z={a.z:.2f}")
    print(f"[WorkerCreateSequence] NavRoam config: num_legs={num_legs}, radius={radius_cm}cm, min_step={min_step_cm}cm")

    seed = cfg.get("seed", None)
    use_python_rng = seed is not None

    points = [a]
    current = a
    for leg in range(max(1, num_legs)):
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
                    print(f"[WorkerCreateSequence] NavRoam leg {leg}: found path with {len(pts)} points")
                    break

                if attempt < 3:
                    print(f"[WorkerCreateSequence] WARNING: NavRoam leg {leg}: empty path from {current} to {candidate} (attempt {attempt + 1}/{max_tries}); retrying")
            except Exception:
                continue

        if not leg_pts:
            print(f"[WorkerCreateSequence] WARNING: NavRoam leg {leg}: could not find a valid path after {max_tries} attempts; stopping early")
            break

        if distance_cm(points[-1], leg_pts[0]) < 0.1:
            leg_pts = leg_pts[1:]
        points.extend(leg_pts)
        current = leg_pts[-1]

    points = subdivide_polyline(points, min_step_cm)
    if project:
        points = [project_to_nav(nav, world, p) for p in points]

    print(f"[WorkerCreateSequence] NavRoam total points before subdivision: {len(points)}")
    return points


def wait_for_navigation_ready(nav, world, timeout_seconds: float) -> None:
    """Best-effort wait until navigation is not building/locked."""
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

        if time.time() - start_t >= timeout:
            print("[WorkerCreateSequence] WARNING: Navigation still building/locked at timeout; continuing")
            return

        time.sleep(0.25)
