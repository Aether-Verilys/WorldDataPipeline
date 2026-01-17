import unreal
from ue_api import get_editor_world, get_level_editor_subsystem, get_actor_subsystem, load_map, load_blueprint_class


def ensure_directory_exists(directory_path: str) -> bool:
    if not directory_path:
        return False
    
    print(f"[AssetsManager] Ensuring directory exists: {directory_path}")
    if not unreal.EditorAssetLibrary.does_directory_exist(directory_path):
        result = unreal.EditorAssetLibrary.make_directory(directory_path)
        if result:
            print(f"[AssetsManager] Created directory")
        else:
            print(f"[AssetsManager] WARNING: Failed to create directory")
        return result
    return True


def create_level_sequence(sequence_name: str, output_dir: str):
    print(f"[AssetsManager] Creating LevelSequence asset: {sequence_name}")
    
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.LevelSequenceFactoryNew()
    
    sequence = asset_tools.create_asset(
        sequence_name,
        output_dir,
        unreal.LevelSequence,
        factory
    )
    
    if sequence:
        print(f"[AssetsManager] Created sequence: {sequence.get_path_name()}")
    else:
        print(f"[AssetsManager] ERROR: Failed to create LevelSequence asset")
    
    return sequence


def save_asset(asset) -> bool:
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(asset)
        print(f"[AssetsManager] Saved asset")
        return True
    except Exception as e:
        print(f"[AssetsManager] WARNING: Save may have failed: {e}")
        return False


def find_actor_by_name(name_or_label: str):
    """在当前关卡中按名称或标签查找Actor
    
    Args:
        name_or_label: Actor的名称或标签
    
    Returns:
        找到的Actor对象，如果未找到则返回None
    """
    try:
        actor_subsystem = get_actor_subsystem()
        actors = actor_subsystem.get_all_level_actors()
    except Exception as e:
        raise RuntimeError(f"Unable to enumerate level actors: {e}")

    target_lower = (name_or_label or "").lower()
    for a in actors:
        try:
            if a is None:
                continue
            obj_name = (a.get_name() or "").lower()
            if obj_name == target_lower:
                return a
            # Actor label is often used in editor
            get_label = getattr(a, "get_actor_label", None)
            if callable(get_label):
                label = (get_label() or "").lower()
                if label == target_lower:
                    return a
        except Exception:
            continue
    return None


def spawn_actor_from_blueprint(blueprint_asset_path: str, desired_label: str, spawn_location, spawn_rotation):
    """从蓝图资产生成Actor到当前关卡
    
    Args:
        blueprint_asset_path: 蓝图资产路径
        desired_label: 期望的Actor标签
        spawn_location: 生成位置 (unreal.Vector)
        spawn_rotation: 生成旋转 (unreal.Rotator)
    
    Returns:
        生成的Actor对象
    """
    cls = load_blueprint_class(blueprint_asset_path)
    if not cls:
        raise RuntimeError(f"Failed to load blueprint class: {blueprint_asset_path}")

    actor_subsystem = get_actor_subsystem()
    actor = actor_subsystem.spawn_actor_from_class(cls, spawn_location, spawn_rotation)
    if not actor:
        raise RuntimeError("Failed to spawn actor")

    # Set label so we can find it next time
    try:
        set_label = getattr(actor, "set_actor_label", None)
        if callable(set_label) and desired_label:
            set_label(desired_label)
            print(f"[AssetsManager] ✓ Set actor label: {desired_label}")
    except Exception as e:
        print(f"[AssetsManager] WARNING: Failed to set actor label: {e}")

    try:
        # Ensure it's visible in editor
        set_hidden = getattr(actor, "set_is_temporarily_hidden_in_editor", None)
        if callable(set_hidden):
            set_hidden(False)
    except Exception:
        pass

    print(f"[AssetsManager] ✓ Spawned actor: name='{actor.get_name()}'")
    return actor


def save_current_level() -> None:
    """保存当前打开的关卡"""
    try:
        # 方法1: 使用 EditorLoadingAndSavingUtils.save_dirty_packages
        # 这是官方推荐的方式，更可靠
        import unreal
        
        # 获取当前世界的包
        world = get_editor_world()
        if world:
            package = world.get_outer()
            if package:
                # 使用 EditorLoadingAndSavingUtils 保存包
                save_options = unreal.EditorLoadingAndSavingUtils.save_packages([package], True)
                if save_options:
                    print(f"[AssetsManager] ✓ Saved current level package: {package.get_name()}")
                    return
        
        # 方法2: 如果方法1失败，尝试使用 LevelEditorSubsystem
        level_editor = get_level_editor_subsystem()
        level_editor.save_current_level()
        print(f"[AssetsManager] ✓ Saved current level")
        return
    except Exception as e:
        print(f"[AssetsManager] WARNING: save_current_level failed: {e}")

    # 方法3: 最后的备选方案 - 保存所有脏关卡
    try:
        world = get_editor_world()
        level_editor = get_level_editor_subsystem()
        level_editor.save_all_dirty_levels()
        print(f"[AssetsManager] ✓ Saved dirty levels")
    except Exception as e:
        print(f"[AssetsManager] WARNING: save_all_dirty_levels failed: {e}")
