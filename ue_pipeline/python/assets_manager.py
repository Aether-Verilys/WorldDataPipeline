import unreal


def load_map(map_asset_path: str) -> None:
    if not map_asset_path:
        return

    # 优先使用 LevelEditorSubsystem.load_level
    try:
        level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if level_editor:
            print(f"[AssetsManager] Loading map via LevelEditorSubsystem: {map_asset_path}")
            ok = level_editor.load_level(map_asset_path)
            if ok:
                print("[AssetsManager] Map loaded")
                return
            print("[AssetsManager] WARNING: LevelEditorSubsystem.load_level returned False")
    except Exception as e:
        print(f"[AssetsManager] WARNING: LevelEditorSubsystem.load_level failed: {e}")

    # 备选方案：EditorLevelLibrary.load_level
    load_level = getattr(unreal.EditorLevelLibrary, "load_level", None)
    if callable(load_level):
        print(f"[AssetsManager] Loading map via EditorLevelLibrary.load_level: {map_asset_path}")
        if load_level(map_asset_path):
            print("[AssetsManager] Map loaded")
            return

    raise RuntimeError(f"Failed to load map: {map_asset_path}")


def load_blueprint_class(blueprint_asset_path: str):
    if not blueprint_asset_path:
        return None

    # 标准化路径（移除 .BP_Name 后缀）
    normalized = blueprint_asset_path
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]

    # 尝试使用 EditorAssetLibrary.load_blueprint_class
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
    else:
        print(f"[AssetsManager] Directory exists")
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
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
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

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
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
    """保存当前关卡"""
    try:
        level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        level_editor.save_current_level()
        print(f"[AssetsManager] ✓ Saved current level")
        return
    except Exception as e:
        print(f"[AssetsManager] WARNING: save_current_level failed: {e}")

    try:
        subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        world = subsystem.get_editor_world()
        level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        level_editor.save_all_dirty_levels()
        print(f"[AssetsManager] ✓ Saved dirty levels")
    except Exception:
        pass
