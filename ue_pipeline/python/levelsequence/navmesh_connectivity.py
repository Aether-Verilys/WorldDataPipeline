import os
import json
import random
import math
from datetime import datetime

try:
    import unreal
except ImportError:
    unreal = None

from .nav_utils import (
    distance_cm,
    find_path_points,
    get_navmesh_bounds,
    project_to_nav,
    random_navigable_point,
    random_reachable_point,
    wait_for_navigation_ready,
    clamp_float,
)


def find_largest_connected_region(nav, world, map_name, cache_dir, sample_count=None, sample_density=None, k_nearest=8, force_recompute=False):
    """
    Analyze NavMesh to find the largest connected region.

    Python-only strategy (v2):
    1. Sample multiple seed points directly on navigable NavMesh (not projection-based)
    2. For each seed, sample a point cloud using reachable-point sampling (guaranteed connected to that seed)
    3. Build a small connectivity graph between seeds via pathfinding (KNN)
    4. Choose the largest connected component by total sampled points
    5. Return the component's sampled points
    6. Cache results to avoid recomputation
    
    Args:
        nav: NavigationSystemV1 instance
        world: World context object
        map_name: Name of the map (for cache file naming)
        cache_dir: Directory to store cache files
        sample_count: Number of random sample points. If None, auto-calculate from sample_density.
        sample_density: Sampling density in points per 10000 cm² (1 m²). Default 1.0.
                       Only used if sample_count is None. Area-based auto-calculation.
        k_nearest: Number of nearest neighbors to test for each point (default 8)
        force_recompute: If True, ignore cache and recompute (default False)
    
    Returns:
        List of Vector points representing the largest connected region
        
    Raises:
        RuntimeError: If NavMesh bounds not found or sampling fails
    """
    if not unreal:
        raise RuntimeError("Unreal Engine module not available")

    # Ensure navmesh is not still building (sampling can be flaky during rebuild)
    try:
        wait_seconds = 10.0
        wait_for_navigation_ready(nav, world, wait_seconds)
    except Exception:
        # Best-effort: do not fail the analysis just because waiting failed.
        pass
    
    # Bounds are required for reasonable default radii and density-based sampling.
    bounds = get_navmesh_bounds(world)
    if not bounds:
        raise RuntimeError("No NavMeshBoundsVolume found in scene")

    center, extent = bounds
    print(f"[NavMesh] NavMesh bounds: center=({center.x:.0f}, {center.y:.0f}, {center.z:.0f}), extent=({extent.x:.0f}, {extent.y:.0f}, {extent.z:.0f})")

    # Auto-calculate target total sample points from NavMesh area if not specified.
    if sample_count is None:
        area_cm2 = (extent.x * 2) * (extent.y * 2)
        area_m2 = area_cm2 / (100.0 * 100.0)
        if sample_density is None:
            sample_density = 1.0
        sample_count = max(40, min(300, int(area_m2 * sample_density)))
        print(f"[NavMesh] Auto-calculated sample_count={sample_count} (area={area_m2:.1f}m², density={sample_density:.2f}/m²)")
    else:
        sample_count = int(sample_count)
    
    ALGO_VERSION = "v2_seed_reachable"

    # Check cache first (versioned)
    cache_file = os.path.join(cache_dir, f"navmesh_connectivity_{map_name}.json")
    if not force_recompute and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("algorithm_version") != ALGO_VERSION:
                    raise RuntimeError(f"Cache algorithm_version mismatch: {data.get('algorithm_version')} != {ALGO_VERSION}")
                print(f"[NavMesh] Loaded cached connectivity data from {cache_file}")
                print(f"[NavMesh] Cache date: {data.get('analysis_date', 'unknown')}")
                region = data.get("largest_region") or []
                print(f"[NavMesh] Cached region has {len(region)} points")
                return [unreal.Vector(**p) for p in region]
        except Exception as e:
            print(f"[NavMesh] Failed to load cache: {e}, will recompute")
    
    print(f"[NavMesh] Starting connectivity analysis v2 (target_points={sample_count}, k_nearest_seeds={k_nearest})...")

    # Global radius: large enough to discover different islands.
    max_xy_extent = float(max(abs(extent.x), abs(extent.y)))
    global_radius_cm = clamp_float(max_xy_extent * 1.25, 20000.0, 300000.0)
    reachable_radius_cm = clamp_float(max_xy_extent * 0.9, 15000.0, 120000.0)

    # Decide seed count and points-per-seed from the overall target.
    num_seeds = int(clamp_float(round(math.sqrt(float(sample_count))), 6.0, 20.0))
    points_per_seed = max(20, int(math.ceil(float(sample_count) / float(max(1, num_seeds)))))

    print(f"[NavMesh] Sampling seeds: num_seeds={num_seeds}, global_radius={global_radius_cm:.0f}cm")
    print(f"[NavMesh] Sampling reachable clouds: points_per_seed={points_per_seed}, reachable_radius={reachable_radius_cm:.0f}cm")

    # 1) Sample seed points directly on the navmesh.
    seeds = []
    seed_attempts = 0
    seed_max_attempts = max(30, num_seeds * 10)
    min_seed_separation_cm = 200.0

    while len(seeds) < num_seeds and seed_attempts < seed_max_attempts:
        seed_attempts += 1
        p = random_navigable_point(nav, world, center, global_radius_cm)
        if p is None:
            # Fallback (older UE bindings): random in bounds then project for seed only.
            raw = unreal.Vector(
                center.x + random.uniform(-extent.x, extent.x),
                center.y + random.uniform(-extent.y, extent.y),
                center.z,
            )
            p = project_to_nav(nav, world, raw)

        if not isinstance(p, unreal.Vector):
            continue

        too_close = False
        for s in seeds:
            if distance_cm(s, p) < min_seed_separation_cm:
                too_close = True
                break
        if too_close:
            continue

        seeds.append(p)

    if len(seeds) < 2:
        raise RuntimeError(f"Failed to sample enough seed points on NavMesh (got {len(seeds)})")

    print(f"[NavMesh] Collected {len(seeds)} seed point(s)")

    # 2) For each seed, sample a reachable point cloud (guaranteed connected to that seed).
    seed_clouds = []
    total_cloud_points = 0
    for idx, seed in enumerate(seeds):
        cloud = [seed]
        attempts = 0
        max_attempts = points_per_seed * 6
        while len(cloud) < points_per_seed and attempts < max_attempts:
            attempts += 1
            try:
                rp = random_reachable_point(nav, world, seed, reachable_radius_cm)
            except Exception:
                continue
            if not isinstance(rp, unreal.Vector):
                continue
            cloud.append(rp)

        seed_clouds.append(cloud)
        total_cloud_points += len(cloud)
        if (idx + 1) % 5 == 0 or (idx + 1) == len(seeds):
            print(f"[NavMesh] Reachable sampling: {idx + 1}/{len(seeds)} seeds, total_points={total_cloud_points}")

    # 3) Build connectivity graph between seeds only.
    print("[NavMesh] Building seed connectivity graph...")
    adjacency = {i: [] for i in range(len(seeds))}
    path_tests = 0
    successful_paths = 0

    for i in range(len(seeds)):
        distances = []
        for j in range(len(seeds)):
            if i == j:
                continue
            distances.append((distance_cm(seeds[i], seeds[j]), j))
        distances.sort()
        nearest = [j for _, j in distances[: max(1, int(k_nearest))]]

        for j in nearest:
            if j in adjacency[i] or i in adjacency[j]:
                continue
            path_tests += 1
            try:
                path = find_path_points(nav, world, seeds[i], seeds[j])
            except Exception:
                path = []
            if path and len(path) > 0:
                adjacency[i].append(j)
                adjacency[j].append(i)
                successful_paths += 1

    print(f"[NavMesh] Seed connectivity graph complete: {successful_paths}/{path_tests} successful paths")

    # 4) Find seed components with BFS, score by total cloud size.
    visited = set()
    components = []
    for start_node in range(len(seeds)):
        if start_node in visited:
            continue
        component = []
        queue = [start_node]
        visited.add(start_node)
        while queue:
            node = queue.pop(0)
            component.append(node)
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(component)

    def _component_score(comp) -> int:
        return int(sum(len(seed_clouds[i]) for i in comp))

    largest_component = max(components, key=_component_score)
    largest_score = _component_score(largest_component)

    largest_points = []
    for i in largest_component:
        largest_points.extend(seed_clouds[i])

    # Limit size to target sample_count for caching stability.
    if len(largest_points) > int(sample_count):
        largest_points = largest_points[: int(sample_count)]

    print(f"[NavMesh] Found {len(components)} connected region(s) (seed-based)")
    print(f"[NavMesh] Largest region: {len(largest_points)} points (score={largest_score})")
    if len(components) > 1:
        component_scores = sorted([_component_score(c) for c in components], reverse=True)
        print(f"[NavMesh] WARNING: NavMesh appears disconnected; component scores: {component_scores[:5]}...")
    
    # 5. Cache results
    try:
        os.makedirs(cache_dir, exist_ok=True)
        cache_data = {
            "map_name": map_name,
            "analysis_date": datetime.now().isoformat(),
            "algorithm_version": ALGO_VERSION,
            "target_sample_count": int(sample_count),
            "num_seeds": int(len(seeds)),
            "points_per_seed": int(points_per_seed),
            "global_radius_cm": float(global_radius_cm),
            "reachable_radius_cm": float(reachable_radius_cm),
            "k_nearest_seeds": int(k_nearest),
            "num_components": int(len(components)),
            "largest_region_size": int(len(largest_points)),
            "largest_region": [{"x": p.x, "y": p.y, "z": p.z} for p in largest_points],
            "all_component_scores": [int(sum(len(seed_clouds[i]) for i in c)) for c in components],
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
        
        print(f"[NavMesh] Cached connectivity data to {cache_file}")
    except Exception as e:
        print(f"[NavMesh] WARNING: Failed to cache results: {e}")
    
    return largest_points


def select_spawn_point_from_region(region_points, strategy="random", seed=None):
    """
    Select a spawn point from the largest connected region.
    
    Args:
        region_points: List of Vector points in the largest connected region
        strategy: Selection strategy - "random" or "center" (default: "random")
        seed: Random seed for reproducibility (optional)
    
    Returns:
        Vector representing the selected spawn point
        
    Raises:
        RuntimeError: If region is empty
    """
    if not region_points:
        raise RuntimeError("Cannot select spawn point from empty region")
    
    if strategy == "center":
        # Select the most central point (closest to region centroid)
        center = unreal.Vector(
            sum(p.x for p in region_points) / len(region_points),
            sum(p.y for p in region_points) / len(region_points),
            sum(p.z for p in region_points) / len(region_points)
        )
        spawn_point = min(region_points, key=lambda p: distance_cm(p, center))
        print(f"[NavMesh] Selected center spawn point: ({spawn_point.x:.2f}, {spawn_point.y:.2f}, {spawn_point.z:.2f})")
    else:  # random
        if seed is not None:
            random.seed(seed)
        spawn_point = random.choice(region_points)
        print(f"[NavMesh] Selected random spawn point: ({spawn_point.x:.2f}, {spawn_point.y:.2f}, {spawn_point.z:.2f})")
    
    return spawn_point


def clear_cache(cache_dir, map_name=None):
    try:
        if map_name:
            cache_file = os.path.join(cache_dir, f"navmesh_connectivity_{map_name}.json")
            if os.path.exists(cache_file):
                os.remove(cache_file)
                print(f"[NavMesh] Cleared cache for map: {map_name}")
            else:
                print(f"[NavMesh] No cache found for map: {map_name}")
        else:
            # Clear all navmesh cache files
            if os.path.exists(cache_dir):
                for filename in os.listdir(cache_dir):
                    if filename.startswith("navmesh_connectivity_") and filename.endswith(".json"):
                        os.remove(os.path.join(cache_dir, filename))
                        print(f"[NavMesh] Cleared cache: {filename}")
            print(f"[NavMesh] Cache cleared")
    except Exception as e:
        print(f"[NavMesh] Error clearing cache: {e}")


def get_spawn_point_with_connectivity(nav, world, map_path, cfg):
    """
    Get a spawn point using connectivity analysis if enabled, otherwise use legacy method.
    
    This is a higher-level function that combines connectivity analysis with fallback.
    
    Args:
        nav: NavigationSystemV1 instance
        world: World context
        map_path: Map path for cache naming
        cfg: Configuration dict with nav_roam settings
        
    Returns:
        unreal.Vector: Selected spawn point
    """
    # Import nav_utils functions here to avoid circular dependency
    try:
        from .nav_utils import find_connected_navmesh_start_point
    except ImportError:
        raise RuntimeError("nav_utils module not available")
    
    use_connectivity_analysis = bool(cfg.get("use_connectivity_analysis", True))
    connectivity_sample_count = cfg.get("connectivity_sample_count", None)
    connectivity_sample_density = cfg.get("connectivity_sample_density", None)

    if not use_connectivity_analysis:
        print("[NavMesh] Connectivity analysis disabled in config")
        return find_connected_navmesh_start_point(nav, world, max_attempts=10)

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cache_dir = os.path.join(os.path.dirname(script_dir), "logs")

        # Use map name for cache - each execution will overwrite previous cache
        cache_name = "navmesh_connectivity"
        if map_path and "/" in str(map_path):
            cache_name = str(map_path).split("/")[-1]

        sample_count_param = int(connectivity_sample_count) if connectivity_sample_count is not None else None
        density_param = float(connectivity_sample_density) if connectivity_sample_density is not None else None

        print(f"[NavMesh] Using connectivity analysis (cache={cache_name}, sample_count={sample_count_param or 'auto'}, density={density_param or 'default'})")
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
        print("[NavMesh] ✓ Selected spawn point from largest connected region")
        return origin

    except Exception as e:
        print(f"[NavMesh] WARNING: Connectivity analysis failed: {e}")
        print(f"[NavMesh] Falling back to legacy method...")
        return find_connected_navmesh_start_point(nav, world, max_attempts=10)
