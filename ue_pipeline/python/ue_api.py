import unreal
from typing import Any
from logger import logger


def get_unreal_editor_subsystem() -> unreal.UnrealEditorSubsystem:
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

def get_editor_world() -> unreal.World:
    try:
        # Use UnrealEditorSubsystem instead of deprecated EditorLevelLibrary.get_editor_world
        subsystem = get_unreal_editor_subsystem()
        return subsystem.get_editor_world()
    except Exception as e:
        raise RuntimeError(f"Failed to get editor world: {e}")

def get_actor_subsystem() -> unreal.EditorActorSubsystem:
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

def get_level_editor_subsystem() -> unreal.LevelEditorSubsystem:
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

def get_editor_asset_subsystem() -> unreal.EditorAssetSubsystem:
    return unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)

def get_movie_pipeline_queue_subsystem() -> unreal.MoviePipelineQueueSubsystem:
    try:
        return unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    except AttributeError:
        try:
            return unreal.get_editor_subsystem(unreal.MoviePipelineEditorSubsystem)
        except AttributeError:
            subsystem_class = unreal.load_class(None, "/Script/MovieRenderPipelineCore.MoviePipelineQueueSubsystem")
            if subsystem_class:
                return unreal.get_editor_subsystem(subsystem_class)
    return None

def get_navigation_system(world: unreal.World = None) -> unreal.NavigationSystemV1:
    if world is None:
        world = get_editor_world()
    return unreal.NavigationSystemV1.get_navigation_system(world)

def load_map(map_asset_path: str) -> bool:
    if not map_asset_path:
        return False

    # 优先使用 LevelEditorSubsystem.load_level
    try:
        level_editor = get_level_editor_subsystem()
        if level_editor:
            logger.info(f"Loading map via LevelEditorSubsystem: {map_asset_path}")
            ok = level_editor.load_level(map_asset_path)
            if ok:
                logger.info("Map loaded")
                return True
            logger.warning("LevelEditorSubsystem.load_level returned False")
    except Exception as e:
        logger.warning(f"LevelEditorSubsystem.load_level failed: {e}")

    # 备选方案：EditorLevelLibrary.load_level
    load_level = getattr(unreal.EditorLevelLibrary, "load_level", None)
    if callable(load_level):
        logger.info(f"Loading map via EditorLevelLibrary.load_level: {map_asset_path}")
        if load_level(map_asset_path):
            logger.info("Map loaded")
            return True

    logger.error(f"Failed to load map: {map_asset_path}")
    return False

def load_blueprint_class(blueprint_asset_path: str):
    if not blueprint_asset_path:
        return None

    # 标准化路径（移除 .BP_Name 后缀）
    normalized = blueprint_asset_path
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]

    loader = getattr(unreal.EditorAssetLibrary, "load_blueprint_class", None)
    if callable(loader):
        for p in (blueprint_asset_path, normalized):
            try:
                cls = loader(p)
                if cls:
                    return cls
            except Exception:
                continue

    # 备选方案：通过 load_asset 获取 generated_class
    asset = unreal.load_asset(normalized)
    if asset is None:
        asset = unreal.load_asset(blueprint_asset_path)
        if asset is None:
            return None

    gen_cls = getattr(asset, "generated_class", None)
    if gen_cls:
        return gen_cls

    # 最后尝试：加载生成的类（_C 后缀）
    try:
        base_name = normalized.split("/")[-1]
        generated = f"{normalized}.{base_name}_C"
        cls = unreal.load_class(None, generated)
        if cls:
            return cls
    except Exception:
        pass

    return None
