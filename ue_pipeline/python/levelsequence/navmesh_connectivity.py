import os
import json
import random
from datetime import datetime

try:
    import unreal
except ImportError:
    unreal = None

from .nav_utils import (
    distance_cm,
    project_to_nav,
    find_path_points,
    get_navmesh_bounds,
)


def find_largest_connected_region(nav, world, map_name, cache_dir, sample_count=None, sample_density=None, k_nearest=8, force_recompute=False):
    """
    Analyze NavMesh to find the largest connected region using sampling and graph analysis.
    
    Strategy:
    1. Sample M random points in NavMesh bounds
    2. Project all points to NavMesh surface
    3. Build connectivity graph using K-nearest neighbor pathfinding
    4. Use BFS to find all connected components
    5. Return the largest component's sample points
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
    
    # Auto-calculate sample_count from NavMesh area if not specified
    if sample_count is None:
        bounds = get_navmesh_bounds(world)
        if bounds:
            center, extent = bounds
            # Calculate area in cm² (XY plane)
            area_cm2 = (extent.x * 2) * (extent.y * 2)
            # Convert to m² (1 m = 100 cm)
            area_m2 = area_cm2 / (100.0 * 100.0)
            
            # Default density: 1 point per m² (10000 cm²)
            if sample_density is None:
                sample_density = 1.0
            
            # Calculate sample count based on area and density
            sample_count = max(30, min(200, int(area_m2 * sample_density)))
            print(f"[NavMesh] Auto-calculated sample_count={sample_count} (area={area_m2:.1f}m², density={sample_density:.2f}/m²)")
        else:
            # Fallback if bounds not available yet
            sample_count = 50
            print(f"[NavMesh] Using default sample_count={sample_count} (bounds not available for auto-calculation)")
    
    # Check cache first
    cache_file = os.path.join(cache_dir, f"navmesh_connectivity_{map_name}.json")
    if not force_recompute and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"[NavMesh] Loaded cached connectivity data from {cache_file}")
                print(f"[NavMesh] Cache date: {data.get('analysis_date', 'unknown')}")
                print(f"[NavMesh] Cached region has {len(data['largest_region'])} points")
                return [unreal.Vector(**p) for p in data["largest_region"]]
        except Exception as e:
            print(f"[NavMesh] Failed to load cache: {e}, will recompute")
    
    print(f"[NavMesh] Starting connectivity analysis (sample_count={sample_count}, k_nearest={k_nearest})...")
    
    # 1. Get NavMesh bounds and generate sample points
    bounds = get_navmesh_bounds(world)
    if not bounds:
        raise RuntimeError("No NavMeshBoundsVolume found in scene")
    
    center, extent = bounds
    print(f"[NavMesh] NavMesh bounds: center=({center.x:.0f}, {center.y:.0f}, {center.z:.0f}), extent=({extent.x:.0f}, {extent.y:.0f}, {extent.z:.0f})")
    
    samples = []
    max_attempts = sample_count * 3  # Allow some failures
    attempts = 0
    
    while len(samples) < sample_count and attempts < max_attempts:
        attempts += 1
        
        # Generate random point within bounds
        random_offset = unreal.Vector(
            random.uniform(-extent.x, extent.x),
            random.uniform(-extent.y, extent.y),
            random.uniform(-extent.z * 0.5, extent.z * 0.5)  # Smaller Z range
        )
        point = unreal.Vector(
            center.x + random_offset.x,
            center.y + random_offset.y,
            center.z + random_offset.z
        )
        
        # Project to NavMesh
        projected = project_to_nav(nav, world, point)
        if projected:
            # Check if it's actually different from the input (successful projection)
            dist = distance_cm(point, projected)
            if dist < extent.z * 2:  # Reasonable projection distance
                samples.append(projected)
    
    if len(samples) < 2:
        raise RuntimeError(f"Failed to get enough NavMesh samples (got {len(samples)}, need at least 2)")
    
    print(f"[NavMesh] Collected {len(samples)} valid sample points")
    
    # 2. Build connectivity graph using K-nearest neighbors
    print(f"[NavMesh] Building connectivity graph...")
    adjacency = {i: [] for i in range(len(samples))}
    path_tests = 0
    successful_paths = 0
    
    for i in range(len(samples)):
        # Find K nearest neighbors for this point
        distances = []
        for j in range(len(samples)):
            if i != j:
                dist = distance_cm(samples[i], samples[j])
                distances.append((dist, j))
        
        distances.sort()
        nearest = [j for _, j in distances[:k_nearest]]
        
        # Test pathfinding to nearest neighbors
        for j in nearest:
            if j in adjacency[i] or i in adjacency[j]:
                # Already tested this edge
                continue
            
            path_tests += 1
            path = find_path_points(nav, world, samples[i], samples[j])
            
            if path and len(path) > 0:
                # Bidirectional edge (undirected graph)
                adjacency[i].append(j)
                adjacency[j].append(i)
                successful_paths += 1
        
        if (i + 1) % 10 == 0:
            print(f"[NavMesh] Progress: {i + 1}/{len(samples)} points processed, {successful_paths}/{path_tests} paths found")
    
    print(f"[NavMesh] Connectivity graph complete: {successful_paths}/{path_tests} successful paths")
    
    # 3. Find all connected components using BFS
    print(f"[NavMesh] Finding connected components...")
    visited = set()
    components = []
    
    for start_node in range(len(samples)):
        if start_node in visited:
            continue
        
        # BFS to find all nodes in this component
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
    
    # 4. Find the largest component
    largest_component = max(components, key=len)
    largest_points = [samples[i] for i in largest_component]
    
    print(f"[NavMesh] Found {len(components)} connected region(s)")
    print(f"[NavMesh] Largest region: {len(largest_points)} points ({len(largest_points)*100//len(samples)}% of total)")
    
    if len(components) > 1:
        print(f"[NavMesh] WARNING: NavMesh has {len(components)} disconnected regions")
        component_sizes = sorted([len(c) for c in components], reverse=True)
        print(f"[NavMesh] Region sizes: {component_sizes[:5]}...")
    
    # 5. Cache results
    try:
        os.makedirs(cache_dir, exist_ok=True)
        cache_data = {
            "map_name": map_name,
            "analysis_date": datetime.now().isoformat(),
            "sample_count": len(samples),
            "k_nearest": k_nearest,
            "num_components": len(components),
            "largest_region_size": len(largest_points),
            "largest_region": [{"x": p.x, "y": p.y, "z": p.z} for p in largest_points],
            "all_component_sizes": [len(c) for c in components]
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
