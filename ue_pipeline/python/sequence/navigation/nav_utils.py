import math
import random
import time
import traceback
import unreal
from ...core import ue_api


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
            last_err = None
            for name in method_names:
                fn = getattr(target, name, None)
                if callable(fn):
                    try:
                        result = fn(*args)
                        if isinstance(result, tuple) and len(result) >= 2:
                            success, projected = result[0], result[1]
                            if success and isinstance(projected, unreal.Vector):
                                return projected
                        if isinstance(result, unreal.Vector):
                            return result
                    except Exception as e:
                        last_err = e
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
            for name in method_names:
                fn = getattr(target, name, None)
                if callable(fn):
                    try:
                        nav_path = fn(*args)
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


def resample_by_count(points, sample_count: int):
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

