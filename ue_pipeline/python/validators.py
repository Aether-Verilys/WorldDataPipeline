import unreal
from ue_api import get_level_editor_subsystem, get_actor_subsystem, load_map


def validate_prerequisites(map_path: str, blueprint_path: str, check_navmesh: bool, log_prefix: str = "[Validator]") -> None:
    errors = []
    
    if map_path:
        if not unreal.EditorAssetLibrary.does_asset_exist(map_path):
            errors.append(f"Map does not exist: {map_path}")
    
    if blueprint_path:
        normalized = blueprint_path.split(".")[0] if "." in blueprint_path else blueprint_path
        if not unreal.EditorAssetLibrary.does_asset_exist(normalized):
            errors.append(f"Blueprint does not exist: {blueprint_path}")
    
    if check_navmesh and map_path:
        navmesh_found = False
        
        try:
            if not load_map(map_path):
                errors.append(f"Failed to load map for NavMesh check: {map_path}")
            else:
                # 检查场景中的NavMeshBoundsVolume
                actor_subsystem = get_actor_subsystem()
                actors = actor_subsystem.get_all_level_actors()
                
                # 查找NavMeshBoundsVolume
                navmesh_bounds_cls = getattr(unreal, "NavMeshBoundsVolume", None)
                for actor in actors:
                    try:
                        if navmesh_bounds_cls and isinstance(actor, navmesh_bounds_cls):
                            navmesh_found = True
                            print(f"{log_prefix} ✓ Found NavMeshBoundsVolume in scene")
                            break
                    except Exception:
                        pass
                
                # 查找RecastNavMesh
                if not navmesh_found:
                    recast_navmesh_cls = getattr(unreal, "RecastNavMesh", None)
                    for actor in actors:
                        try:
                            if recast_navmesh_cls and isinstance(actor, recast_navmesh_cls):
                                navmesh_found = True
                                print(f"{log_prefix} ✓ Found RecastNavMesh in scene")
                                break
                        except Exception:
                            pass
                
                if not navmesh_found:
                    errors.append(f"Map has no NavMesh (checked: NavMeshBoundsVolume, RecastNavMesh): {map_path}")
        except Exception as e:
            errors.append(f"NavMesh validation failed: {e}")
    
    if errors:
        error_msg = "Prerequisites validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(error_msg)


def validate_map_exists(map_path: str) -> bool:
    if not map_path:
        return False
    return unreal.EditorAssetLibrary.does_asset_exist(map_path)


def validate_blueprint_exists(blueprint_path: str) -> bool:
    if not blueprint_path:
        return False
    normalized = blueprint_path.split(".")[0] if "." in blueprint_path else blueprint_path
    return unreal.EditorAssetLibrary.does_asset_exist(normalized)


def validate_navmesh_in_scene(map_path: str, log_prefix: str = "[Validator]") -> bool:
    if not map_path:
        return False
    
    try:
        # 先加载地图
        if not load_map(map_path):
            return False
        
        # 检查场景中的NavMeshBoundsVolume
        actor_subsystem = get_actor_subsystem()
        actors = actor_subsystem.get_all_level_actors()
        
        # 查找NavMeshBoundsVolume
        navmesh_bounds_cls = getattr(unreal, "NavMeshBoundsVolume", None)
        for actor in actors:
            try:
                if navmesh_bounds_cls and isinstance(actor, navmesh_bounds_cls):
                    print(f"{log_prefix} ✓ Found NavMeshBoundsVolume in scene")
                    return True
            except Exception:
                pass
        
        # 查找RecastNavMesh
        recast_navmesh_cls = getattr(unreal, "RecastNavMesh", None)
        for actor in actors:
            try:
                if recast_navmesh_cls and isinstance(actor, recast_navmesh_cls):
                    print(f"{log_prefix} ✓ Found RecastNavMesh in scene")
                    return True
            except Exception:
                pass
        
        return False
    except Exception:
        return False
