import unreal


def debug_list_methods(obj, title: str, contains: str) -> None:
    try:
        methods = [m for m in dir(obj) if contains.lower() in m.lower()]
        methods = sorted(set(methods))
        print(f"[SeqCameraBindings] DEBUG {title} methods (contains='{contains}'): {methods}")
    except Exception as e:
        print(f"[SeqCameraBindings] DEBUG: failed listing methods for {title}: {e}")


def create_camera_cuts_track(sequence, movie_scene):
    track_class = getattr(unreal, "MovieSceneCameraCutTrack", None)
    if track_class is None:
        raise RuntimeError("MovieSceneCameraCutTrack class not found in unreal module")

    # 尝试在LevelSequence上创建
    for fn_name in ("add_master_track", "add_track"):
        fn = getattr(sequence, fn_name, None)
        if callable(fn):
            try:
                track = fn(track_class)
                if track:
                    return track
            except Exception:
                pass

    # 尝试在MovieScene上创建
    for fn_name in ("add_master_track", "add_track"):
        fn = getattr(movie_scene, fn_name, None)
        if callable(fn):
            try:
                track = fn(track_class)
                if track:
                    return track
            except Exception:
                pass

    # 调试输出
    debug_list_methods(sequence, "LevelSequence", "track")
    debug_list_methods(movie_scene, "MovieScene", "track")
    debug_list_methods(movie_scene, "MovieScene", "camera")
    raise RuntimeError("Unable to create Camera Cuts track (no compatible API found)")


def get_binding_guid(binding_proxy):
    for getter_name in ("get_id", "get_guid"):
        getter = getattr(binding_proxy, getter_name, None)
        if callable(getter):
            try:
                g = getter()
                if g is not None:
                    return g
            except Exception:
                pass
    return None


def get_binding_space_local():
    space_enum = getattr(unreal, "MovieSceneObjectBindingSpace", None)
    if space_enum is None:
        return None
    for name in ("LOCAL", "Local"):
        if hasattr(space_enum, name):
            return getattr(space_enum, name)
    return None


def make_object_binding_id(sequence, movie_scene, binding_proxy):
    guid = get_binding_guid(binding_proxy)
    if guid is None:
        return None

    space_local = get_binding_space_local()

    # 优先使用 sequence/movie_scene.make_binding_id
    for owner in (sequence, movie_scene):
        for fn_name in ("make_binding_id",):
            fn = getattr(owner, fn_name, None)
            if callable(fn):
                for args in (
                    (binding_proxy, space_local),
                    (binding_proxy,),
                    (guid, space_local),
                    (guid,),
                ):
                    try:
                        bid = fn(*[a for a in args if a is not None])
                        if bid is not None:
                            return bid
                    except Exception:
                        continue

    # 备选方案：直接构造MovieSceneObjectBindingID
    cls = getattr(unreal, "MovieSceneObjectBindingID", None)
    if cls is None:
        return guid

    for args in (
        (guid, space_local),
        (guid,),
    ):
        try:
            bid = cls(*[a for a in args if a is not None])
            if bid is not None:
                return bid
        except Exception:
            continue

    # 最后尝试：创建空对象并设置属性
    try:
        bid = cls()
        try:
            bid.set_editor_property("guid", guid)
        except Exception:
            pass
        if space_local is not None:
            try:
                bid.set_editor_property("space", space_local)
            except Exception:
                pass
        return bid
    except Exception:
        return guid


def bind_camera_to_cut_section(camera_cut_section, sequence, movie_scene, camera_binding) -> bool:
    if not camera_cut_section or not camera_binding:
        return False

    binding_id = make_object_binding_id(sequence, movie_scene, camera_binding)
    if binding_id is None:
        print("[SeqCameraBindings] WARNING: Could not create camera binding id; leaving Camera Cuts unbound")
        return False

    # 尝试直接设置方法
    for setter_name in ("set_camera_binding_id", "set_camera_binding", "set_camera"):
        setter = getattr(camera_cut_section, setter_name, None)
        if callable(setter):
            try:
                setter(binding_id)
                print(f"[SeqCameraBindings] ✓ Bound camera via {setter_name}")
                try:
                    getter = getattr(camera_cut_section, "get_camera_binding_id", None)
                    if callable(getter):
                        current = getter()
                        print(f"[SeqCameraBindings]   Camera binding id now: {current}")
                except Exception:
                    pass
                return True
            except Exception:
                continue

    # 尝试通过属性设置
    try:
        camera_cut_section.set_editor_property("camera_binding_id", binding_id)
        print("[SeqCameraBindings] ✓ Bound camera via set_editor_property(camera_binding_id)")
        try:
            getter = getattr(camera_cut_section, "get_camera_binding_id", None)
            if callable(getter):
                current = getter()
                print(f"[SeqCameraBindings]   Camera binding id now: {current}")
        except Exception:
            pass
        return True
    except Exception:
        pass

    debug_list_methods(camera_cut_section, "CameraCutSection", "camera")
    debug_list_methods(camera_cut_section, "CameraCutSection", "bind")
    print("[SeqCameraBindings] WARNING: No compatible camera binding setter found on section")
    return False


def find_camera_component(actor, component_name: str):
    if actor is None:
        return None

    # 查找所有相机类型组件
    cam_component_classes = []
    for cls_name in ("CineCameraComponent", "CameraComponent"):
        cls = getattr(unreal, cls_name, None)
        if cls:
            cam_component_classes.append(cls)

    components = []
    for cls in cam_component_classes:
        getter = getattr(actor, "get_components_by_class", None)
        if callable(getter):
            try:
                components.extend(list(getter(cls)))
            except Exception:
                pass

    # 优先按名称精确匹配
    target_lower = (component_name or "").lower()
    for c in components:
        try:
            if c is None:
                continue
            if (c.get_name() or "").lower() == target_lower:
                return c
        except Exception:
            continue

    # 备选：如果只有一个相机组件，直接使用
    if len(components) == 1:
        return components[0]

    return None


def ensure_actor_binding(
    sequence,
    actor_blueprint_class_path: str,
    load_blueprint_class_fn,
):
    """创建sequence spawnable actor绑定
    
    Args:
        sequence: LevelSequence对象
        actor_blueprint_class_path: Actor蓝图类路径
        load_blueprint_class_fn: 加载蓝图类的函数
    
    Returns:
        binding: SequenceBinding对象
    """
    if load_blueprint_class_fn is None:
        raise RuntimeError("load_blueprint_class_fn is required")
    
    cls = load_blueprint_class_fn(actor_blueprint_class_path)
    if not cls:
        raise RuntimeError(f"Failed to load blueprint class for spawnable: {actor_blueprint_class_path}")

    # Try using MovieSceneSequenceExtensions directly (recommended API)
    try:
        binding = unreal.MovieSceneSequenceExtensions.add_spawnable_from_class(sequence, cls)
        if binding:
            print(f"[SeqCameraBindings] ✓ Created spawnable binding from blueprint: {actor_blueprint_class_path}")
            return binding
    except Exception:
        pass

    # Fallback to old methods if needed
    for fn_name in ("add_spawnable_from_class", "add_spawnable"):
        fn = getattr(sequence, fn_name, None)
        if callable(fn):
            try:
                binding = fn(cls)
                if binding:
                    print(f"[SeqCameraBindings] ✓ Created spawnable binding from blueprint: {actor_blueprint_class_path}")
                    return binding
            except Exception:
                pass

    debug_list_methods(sequence, "LevelSequence", "spawn")
    raise RuntimeError("Unable to create spawnable from blueprint class")


def add_camera_cuts(
    sequence,
    actor_binding,
    total_frames: int,
) -> None:
    """Add camera cuts track bound to the spawnable actor.
    
    Args:
        sequence: LevelSequence object
        actor_binding: Actor binding to bind camera cuts to
        total_frames: Total number of frames for the section range
    """
    movie_scene = sequence.get_movie_scene()
    print("[SeqCameraBindings] Adding camera cuts bound to spawnable actor...")
    
    try:
        # Add Camera Cuts Track
        print("[SeqCameraBindings]   Adding Camera Cuts Track...")
        camera_cut_track = create_camera_cuts_track(sequence, movie_scene)
        print("[SeqCameraBindings] Created Camera Cuts Track")

        # Add a section to the camera cut track
        print("[SeqCameraBindings]   Adding Camera Cut Section...")
        camera_cut_section = camera_cut_track.add_section()
        if not camera_cut_section:
            raise RuntimeError("Failed to create camera cut section")

        # Set the section range to cover the entire sequence
        try:
            camera_cut_section.set_range(0, total_frames)
            print(f"[SeqCameraBindings] Set section range: 0-{total_frames}")
        except Exception as e:
            print(f"[SeqCameraBindings] WARNING: Could not set section range: {e}")

        # Bind the camera to the section
        bind_camera_to_cut_section(camera_cut_section, sequence, movie_scene, actor_binding)

    except Exception as e:
        print(f"[SeqCameraBindings] WARNING: Failed to add camera cuts: {e}")
        import traceback
        traceback.print_exc()
