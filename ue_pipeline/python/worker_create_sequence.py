import json
import math
import os
import random
import sys
import time
import unreal

print("[WorkerCreateSequence] Starting job execution...")

# Parse manifest path from environment variable or command line arguments
manifest_path = os.environ.get('UE_MANIFEST_PATH')

if not manifest_path:
    # Fallback to command line arguments
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--manifest="):
            manifest_path = arg.split("=", 1)[1]
        elif arg == "--manifest" and i + 1 < len(sys.argv):
            manifest_path = sys.argv[i + 1]

if not manifest_path:
    print("[WorkerCreateSequence] ERROR: No manifest path provided")
    sys.exit(1)

print(f"[WorkerCreateSequence] Manifest: {manifest_path}")

# Read manifest
try:
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
except Exception as e:
    print(f"[WorkerCreateSequence] ERROR: Failed to read manifest: {e}")
    sys.exit(1)

job_id = manifest.get("job_id", "unknown")
job_type = manifest.get("job_type", "unknown")
map_path = manifest.get("map", "")
sequence_config = manifest.get("sequence_config", {})

output_dir = sequence_config.get("output_dir", "/Game/CameraController/Generated")
sequence_number = sequence_config.get("sequence_number", 1)

actor_name = sequence_config.get("actor_name", "BP_NPC_NavMesh")
camera_component_name = sequence_config.get("camera_component_name", "Camera")
actor_blueprint_class_path = sequence_config.get(
    "actor_blueprint_class_path",
    "/Game/FirstPerson/Blueprints/BP_NPC_NavMesh.BP_NPC_NavMesh",
)
spawn_actor_if_missing = bool(sequence_config.get("spawn_actor_if_missing", False))
actor_binding_mode = (sequence_config.get("actor_binding_mode", "sequence_spawnable") or "sequence_spawnable").lower()
save_level_if_spawned = bool(sequence_config.get("save_level_if_spawned", False))

spawn_at_startpoint = bool(sequence_config.get("spawn_at_startpoint", False))
nav_roam_cfg = sequence_config.get("nav_roam", {}) or {}
nav_roam_enabled = bool(nav_roam_cfg.get("enabled", False))

force_zero_pitch_roll = bool(sequence_config.get("force_zero_pitch_roll", True))
max_yaw_rate_deg_per_sec = sequence_config.get("max_yaw_rate_deg_per_sec", None)
try:
    if max_yaw_rate_deg_per_sec is not None:
        max_yaw_rate_deg_per_sec = float(max_yaw_rate_deg_per_sec)
        if max_yaw_rate_deg_per_sec <= 0:
            max_yaw_rate_deg_per_sec = None
except Exception:
    max_yaw_rate_deg_per_sec = None

write_transform_keys = bool(sequence_config.get("write_transform_keys", False))
transform_keys_cfg = sequence_config.get("transform_keys", None)
transform_key_interp = (sequence_config.get("transform_key_interp", "auto") or "auto").lower()

spawn_location_cfg = sequence_config.get("spawn_location", {"x": 0.0, "y": 0.0, "z": 0.0})
spawn_rotation_cfg = sequence_config.get("spawn_rotation", {"pitch": 0.0, "yaw": 0.0, "roll": 0.0})

def _as_float(v, default=0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


spawn_location = unreal.Vector(
    _as_float(spawn_location_cfg.get("x", 0.0)),
    _as_float(spawn_location_cfg.get("y", 0.0)),
    _as_float(spawn_location_cfg.get("z", 0.0)),
)
spawn_rotation = unreal.Rotator(
    _as_float(spawn_rotation_cfg.get("pitch", 0.0)),
    _as_float(spawn_rotation_cfg.get("yaw", 0.0)),
    _as_float(spawn_rotation_cfg.get("roll", 0.0)),
)

print(f"[WorkerCreateSequence] Job ID:   {job_id}")
print(f"[WorkerCreateSequence] Job Type: {job_type}")
print(f"[WorkerCreateSequence] Map:      {map_path}")
print(f"[WorkerCreateSequence] Output:   {output_dir}")
print(f"[WorkerCreateSequence] Actor:    {actor_name}")
print(f"[WorkerCreateSequence] Camera:   {camera_component_name}")
print(f"[WorkerCreateSequence] BindMode: {actor_binding_mode}")
if nav_roam_enabled:
    print(f"[WorkerCreateSequence] NavRoam:  enabled")

if job_type != "create_sequence":
    print(f"[WorkerCreateSequence] ERROR: Invalid job type '{job_type}', expected 'create_sequence'")
    sys.exit(1)

# Extract map name from path
# e.g. "/Game/Maps/Lvl_FirstPerson" -> "Lvl_FirstPerson"
map_name = "Unknown"
if map_path:
    map_name = map_path.split("/")[-1]

# Generate sequence name
sequence_name = f"{map_name}_{sequence_number:03d}"
print(f"[WorkerCreateSequence] Sequence name: {sequence_name}")


def _debug_list_methods(obj, title: str, contains: str) -> None:
    try:
        methods = [m for m in dir(obj) if contains.lower() in m.lower()]
        methods = sorted(set(methods))
        print(f"[WorkerCreateSequence] DEBUG {title} methods (contains='{contains}'): {methods}")
    except Exception as e:
        print(f"[WorkerCreateSequence] DEBUG: failed listing methods for {title}: {e}")


def _get_world():
    try:
        return unreal.EditorLevelLibrary.get_editor_world()
    except Exception as e:
        raise RuntimeError(f"Failed to get editor world: {e}")


def _get_nav_system(world):
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


def _call_maybe(obj, method_names, *args):
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


def _distance_cm(a: unreal.Vector, b: unreal.Vector) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return float(math.sqrt(dx * dx + dy * dy + dz * dz))


def _random_navigable_point(nav, world, origin: unreal.Vector, radius_cm: float) -> unreal.Vector:
    candidates = [
        (nav, ["get_random_point_in_navigable_radius", "k2_get_random_point_in_navigable_radius"]),
        (getattr(unreal, "NavigationSystemV1", object), ["get_random_point_in_navigable_radius", "k2_get_random_point_in_navigable_radius"]),
    ]

    arg_variants = [
        (world, origin, radius_cm),
        (world, origin, radius_cm, None),
        (world, origin, radius_cm, None, None),
    ]

    for target, method_names in candidates:
        for args in arg_variants:
            try:
                result = _call_maybe(target, method_names, *args)
            except Exception:
                continue
            if isinstance(result, tuple) and len(result) >= 2:
                success, point = result[0], result[1]
                if success and isinstance(point, unreal.Vector):
                    return point
            if isinstance(result, unreal.Vector):
                return result

    raise RuntimeError("Failed to get random navigable point. Ensure NavMesh exists in this map.")


def _project_to_nav(nav, world, point: unreal.Vector) -> unreal.Vector:
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
                result = _call_maybe(target, method_names, *args)
            except Exception:
                continue
            if isinstance(result, tuple) and len(result) >= 2:
                success, projected = result[0], result[1]
                if success and isinstance(projected, unreal.Vector):
                    return projected
            if isinstance(result, unreal.Vector):
                return result
    return point


def _find_path_points(nav, world, start: unreal.Vector, end: unreal.Vector):
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
                nav_path = _call_maybe(target, method_names, *args)
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

    # Some maps / nav states can return an empty path even though nav_path exists.
    # Treat this as "no valid path" and let the caller retry a different destination.
    return []


def _subdivide_polyline(points, step_cm: float):
    if len(points) < 2:
        return points
    out = [points[0]]
    for i in range(1, len(points)):
        a = out[-1]
        b = points[i]
        seg_len = _distance_cm(a, b)
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

        if _distance_cm(out[-1], b) > 0.01:
            out.append(b)
    return out


def _resample_by_distance(points, sample_count: int):
    if len(points) < 2:
        return points
    if sample_count <= 2:
        return [points[0], points[-1]]

    dists = [0.0]
    for i in range(1, len(points)):
        dists.append(dists[-1] + _distance_cm(points[i - 1], points[i]))
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


def _build_multi_leg_nav_path(nav, world, start: unreal.Vector, cfg: dict):
    radius_cm = float(cfg.get("random_point_radius_cm", 8000.0))
    num_legs = int(cfg.get("num_legs", 6))
    max_tries = int(cfg.get("max_random_point_tries", 40))
    min_step_cm = float(cfg.get("min_segment_step_cm", 75.0))
    project = bool(cfg.get("project_to_nav", True))
    min_leg_dist = float(cfg.get("min_leg_distance_cm", 300.0))

    origin = start if start is not None else unreal.Vector(0.0, 0.0, 0.0)

    # Ensure start is on navmesh
    a = _project_to_nav(nav, world, origin) if project else origin

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
                    candidate = _project_to_nav(nav, world, raw) if project else raw
                else:
                    candidate = _random_navigable_point(nav, world, current, radius_cm)

                if _distance_cm(current, candidate) <= min_leg_dist:
                    continue

                # Ensure endpoints are on navmesh
                start_on_nav = _project_to_nav(nav, world, current) if project else current
                end_on_nav = _project_to_nav(nav, world, candidate) if project else candidate

                pts = _find_path_points(nav, world, start_on_nav, end_on_nav)
                if pts and len(pts) >= 2:
                    leg_pts = pts
                    break

                # No valid path; retry another destination
                if attempt < 3:
                    print(f"[WorkerCreateSequence] WARNING: NavRoam leg {leg}: empty path (attempt {attempt + 1}/{max_tries}); retrying")
            except Exception:
                continue

        if not leg_pts:
            print(f"[WorkerCreateSequence] WARNING: NavRoam leg {leg}: could not find a valid path after {max_tries} attempts; stopping early")
            break

        if _distance_cm(points[-1], leg_pts[0]) < 0.1:
            leg_pts = leg_pts[1:]
        points.extend(leg_pts)
        current = leg_pts[-1]

    points = _subdivide_polyline(points, min_step_cm)
    if project:
        points = [_project_to_nav(nav, world, p) for p in points]
    return points


def _find_first_startpoint(mode: str = "player_start"):
    mode = (mode or "player_start").lower()
    actors = unreal.EditorLevelLibrary.get_all_level_actors()

    def _is_instance_of(actor, cls):
        try:
            return cls is not None and actor is not None and isinstance(actor, cls)
        except Exception:
            return False

    player_start_cls = getattr(unreal, "PlayerStart", None)
    target_point_cls = getattr(unreal, "TargetPoint", None)

    if mode in ("player_start", "playerstart"):
        for a in actors:
            if _is_instance_of(a, player_start_cls):
                return a

    if mode in ("target_point", "targetpoint"):
        for a in actors:
            if _is_instance_of(a, target_point_cls):
                return a

    # Fallback: any actor whose name/label contains 'start'
    for a in actors:
        try:
            if a is None:
                continue
            name = (a.get_name() or "")
            label_fn = getattr(a, "get_actor_label", None)
            label = label_fn() if callable(label_fn) else ""
            s = f"{name} {label}".lower()
            if "start" in s:
                return a
        except Exception:
            continue

    # Last resort: return the first PlayerStart/TargetPoint if any
    for a in actors:
        if _is_instance_of(a, player_start_cls) or _is_instance_of(a, target_point_cls):
            return a
    return None


def _wait_for_navigation_ready(nav, world, timeout_seconds: float) -> None:
    """Best-effort wait until navigation is not building/locked.

    In headless runs right after map load, FindPath may return empty while nav is initializing.
    """
    try:
        timeout = max(0.0, float(timeout_seconds))
    except Exception:
        timeout = 0.0
    if timeout <= 0.0:
        return

    fn = getattr(nav, "is_navigation_being_built_or_locked", None)
    if not callable(fn):
        # Some versions only expose this on the class
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


def _channel_add_key(channel, frame: int, value):
    """Add a key on a scripting channel across UE API variants."""
    add_key = getattr(channel, "add_key", None)
    if not callable(add_key):
        raise RuntimeError("Channel has no add_key")

    # Common call patterns across versions
    for t in (
        unreal.FrameNumber(int(frame)),
        int(frame),
        unreal.FrameTime(unreal.FrameNumber(int(frame))),
    ):
        try:
            return add_key(t, value)
        except Exception:
            continue

    raise RuntimeError("Failed to add key on channel (no compatible signature)")


def _apply_key_interpolation(scripting_key, mode: str) -> None:
    if scripting_key is None:
        return

    set_interp = getattr(scripting_key, "set_interpolation_mode", None)
    if not callable(set_interp):
        return

    # Best-effort enum resolution
    enum_candidates = []
    for enum_name in (
        "MovieSceneKeyInterpolation",
        "MovieSceneKeyInterpolationMode",
    ):
        enum_candidates.append(getattr(unreal, enum_name, None))

    enum_candidates = [e for e in enum_candidates if e is not None]
    if not enum_candidates:
        return

    mode_upper = (mode or "auto").upper()
    for enum in enum_candidates:
        try:
            if hasattr(enum, mode_upper):
                set_interp(getattr(enum, mode_upper))
                return
        except Exception:
            continue


def _get_transform_channels(section):
    """Return a list of scripting channels for a 3D transform section."""
    for fn_name in (
        "get_channels",
        "get_all_channels",
    ):
        fn = getattr(section, fn_name, None)
        if callable(fn):
            try:
                channels = list(fn())
                if channels:
                    return channels
            except Exception:
                pass

    _debug_list_methods(section, "TransformSection", "channel")
    return []


def _write_transform_keys(binding, fps: int, total_frames: int, keys_cfg):
    """Write a few transform keys on the binding so the sequence animates the actor."""
    track_class = getattr(unreal, "MovieScene3DTransformTrack", None)
    if track_class is None:
        raise RuntimeError("MovieScene3DTransformTrack class not found in unreal module")

    # Create transform track on the binding
    add_track = getattr(binding, "add_track", None)
    if not callable(add_track):
        _debug_list_methods(binding, "Binding", "track")
        raise RuntimeError("Binding has no add_track")

    transform_track = add_track(track_class)
    if not transform_track:
        raise RuntimeError("Failed to create transform track")

    section = transform_track.add_section()
    if not section:
        raise RuntimeError("Failed to add transform section")

    try:
        section.set_range(0, total_frames)
    except Exception:
        pass

    channels = _get_transform_channels(section)
    if len(channels) < 6:
        raise RuntimeError(f"Unable to access transform section channels (got {len(channels)})")

    # Typical order: loc(x,y,z), rot(x,y,z), scale(x,y,z)
    # Rotation channels in UE are usually: X=Roll, Y=Pitch, Z=Yaw
    loc = channels[0:3]
    rot = channels[3:6]  # rot[0]=X(Roll), rot[1]=Y(Pitch), rot[2]=Z(Yaw)
    scl = channels[6:9] if len(channels) >= 9 else []

    def _frame_from_time_seconds(t: float) -> int:
        try:
            return int(round(float(t) * float(fps)))
        except Exception:
            return 0

    # If no explicit keys provided, write a small default motion
    if not keys_cfg:
        keys_cfg = [
            {"time_seconds": 0.0, "location": {"x": 0, "y": 0, "z": 0}, "rotation": {"pitch": 0, "yaw": 0, "roll": 0}},
            {"time_seconds": 2.0, "location": {"x": 200, "y": 0, "z": 0}, "rotation": {"pitch": 0, "yaw": 45, "roll": 0}},
            {"time_seconds": 4.0, "location": {"x": 200, "y": 200, "z": 0}, "rotation": {"pitch": 0, "yaw": 90, "roll": 0}},
        ]

    print(f"[WorkerCreateSequence] Writing {len(keys_cfg)} transform keys...")

    for k in keys_cfg:
        t = _as_float(k.get("time_seconds", 0.0))
        frame = _frame_from_time_seconds(t)
        frame = max(0, min(total_frames, frame))

        loc_cfg = k.get("location", {}) or {}
        rot_cfg = k.get("rotation", {}) or {}
        scl_cfg = k.get("scale", None)

        lx = _as_float(loc_cfg.get("x", 0.0))
        ly = _as_float(loc_cfg.get("y", 0.0))
        lz = _as_float(loc_cfg.get("z", 0.0))
        
        # Rotation: sanitize already happened via _sanitize_rotation_keys if force_zero_pitch_roll=True
        rp = _as_float(rot_cfg.get("pitch", 0.0))
        ry = _as_float(rot_cfg.get("yaw", 0.0))
        rr = _as_float(rot_cfg.get("roll", 0.0))

        sx = sy = sz = 1.0
        if isinstance(scl_cfg, dict):
            sx = _as_float(scl_cfg.get("x", 1.0), 1.0)
            sy = _as_float(scl_cfg.get("y", 1.0), 1.0)
            sz = _as_float(scl_cfg.get("z", 1.0), 1.0)

        try:
            kx = _channel_add_key(loc[0], frame, lx)
            ky = _channel_add_key(loc[1], frame, ly)
            kz = _channel_add_key(loc[2], frame, lz)
            _apply_key_interpolation(kx, transform_key_interp)
            _apply_key_interpolation(ky, transform_key_interp)
            _apply_key_interpolation(kz, transform_key_interp)
        except Exception as e:
            raise RuntimeError(f"Failed adding location keys at frame {frame}: {e}")

        try:
            # UE rotation channel order: X=Roll, Y=Pitch, Z=Yaw
            kr = _channel_add_key(rot[0], frame, rr)      # X = Roll
            kp = _channel_add_key(rot[1], frame, rp)      # Y = Pitch
            kyaw = _channel_add_key(rot[2], frame, ry)    # Z = Yaw
            _apply_key_interpolation(kr, transform_key_interp)
            _apply_key_interpolation(kp, transform_key_interp)
            _apply_key_interpolation(kyaw, transform_key_interp)
        except Exception as e:
            raise RuntimeError(f"Failed adding rotation keys at frame {frame}: {e}")

        if scl:
            try:
                ksx = _channel_add_key(scl[0], frame, sx)
                ksy = _channel_add_key(scl[1], frame, sy)
                ksz = _channel_add_key(scl[2], frame, sz)
                _apply_key_interpolation(ksx, transform_key_interp)
                _apply_key_interpolation(ksy, transform_key_interp)
                _apply_key_interpolation(ksz, transform_key_interp)
            except Exception:
                # Scale isn't essential for this test
                pass

    print("[WorkerCreateSequence] ✓ Wrote transform keys")


def _normalize_angle_continuous(angles_deg):
    """Unwrap angles to avoid jumps at -180/+180 boundary.
    
    Example: [170, -175, -170] becomes [170, 185, 190] (continuous rotation)
    """
    if not angles_deg or len(angles_deg) < 2:
        return angles_deg
    
    result = [float(angles_deg[0])]
    for i in range(1, len(angles_deg)):
        prev = result[-1]
        curr = float(angles_deg[i])
        
        # Find the shortest angular distance
        diff = curr - prev
        while diff > 180.0:
            diff -= 360.0
        while diff < -180.0:
            diff += 360.0
        
        result.append(prev + diff)
    
    return result


def _sanitize_rotation_keys(keys_cfg, zero_pitch_roll: bool, max_yaw_rate_deg_per_sec: float | None) -> None:
    if not keys_cfg:
        return

    count = 0
    times = []
    for key in keys_cfg:
        if not isinstance(key, dict):
            continue
        rot = key.get("rotation")
        if rot is None or not isinstance(rot, dict):
            rot = {}
            key["rotation"] = rot

        if zero_pitch_roll:
            rot["pitch"] = 0.0
            rot["roll"] = 0.0

        times.append(float(key.get("time_seconds", 0.0)))
        count += 1

    if count <= 0:
        return

    # Make yaw continuous to prevent jumps at -180/+180 boundary
    yaws = []
    rot_refs = []
    for key in keys_cfg:
        if isinstance(key, dict):
            rot = key.get("rotation", {})
            if isinstance(rot, dict):
                rot_refs.append(rot)
                yaws.append(rot.get("yaw", 0.0))

    if len(yaws) == len(rot_refs) and len(yaws) > 0:
        continuous_yaws = _normalize_angle_continuous(yaws)

        # Optional yaw-rate clamp (deg/sec)
        if max_yaw_rate_deg_per_sec and len(times) == len(continuous_yaws):
            smoothed = [continuous_yaws[0]]
            for i in range(1, len(continuous_yaws)):
                prev = smoothed[-1]
                target = continuous_yaws[i]
                dt = max(1e-3, times[i] - times[i - 1])
                max_delta = max_yaw_rate_deg_per_sec * dt
                delta = target - prev
                if delta > max_delta:
                    delta = max_delta
                elif delta < -max_delta:
                    delta = -max_delta
                smoothed.append(prev + delta)
            continuous_yaws = smoothed

        for rot, yaw in zip(rot_refs, continuous_yaws):
            rot["yaw"] = float(yaw)

    msg = f"[WorkerCreateSequence] ✓ Sanitized {count} keys: yaw continuous"
    if max_yaw_rate_deg_per_sec:
        msg += f", yaw rate ≤ {max_yaw_rate_deg_per_sec:.1f} deg/s"
    if zero_pitch_roll:
        msg += ", pitch=0, roll=0"
    print(msg)


def _create_camera_cuts_track(sequence, movie_scene):
    """Create a Camera Cuts track in a way that works across UE versions.

    Common APIs across versions:
      - sequence.add_master_track(unreal.MovieSceneCameraCutTrack)
      - movie_scene.add_master_track(unreal.MovieSceneCameraCutTrack)
    """
    track_class = getattr(unreal, "MovieSceneCameraCutTrack", None)
    if track_class is None:
        raise RuntimeError("MovieSceneCameraCutTrack class not found in unreal module")

    # Try on LevelSequence first
    for fn_name in ("add_master_track", "add_track"):
        fn = getattr(sequence, fn_name, None)
        if callable(fn):
            try:
                track = fn(track_class)
                if track:
                    return track
            except Exception:
                pass

    # Try on MovieScene
    for fn_name in ("add_master_track", "add_track"):
        fn = getattr(movie_scene, fn_name, None)
        if callable(fn):
            try:
                track = fn(track_class)
                if track:
                    return track
            except Exception:
                pass

    # Debug: show nearby API names to help future fixes
    _debug_list_methods(sequence, "LevelSequence", "track")
    _debug_list_methods(movie_scene, "MovieScene", "track")
    _debug_list_methods(movie_scene, "MovieScene", "camera")
    raise RuntimeError("Unable to create Camera Cuts track (no compatible API found)")


def _get_binding_guid(binding_proxy):
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


def _get_binding_space_local():
    space_enum = getattr(unreal, "MovieSceneObjectBindingSpace", None)
    if space_enum is None:
        return None
    for name in ("LOCAL", "Local"):
        if hasattr(space_enum, name):
            return getattr(space_enum, name)
    return None


def _make_object_binding_id(sequence, movie_scene, binding_proxy):
    """Create a MovieSceneObjectBindingID from a binding proxy across UE versions."""
    guid = _get_binding_guid(binding_proxy)
    if guid is None:
        return None

    space_local = _get_binding_space_local()

    # Preferred: sequence.make_binding_id(binding_proxy, space)
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

    # Fallback: construct MovieSceneObjectBindingID
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

    # Last resort: create empty and set properties
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


def _try_bind_camera_cut_section(camera_cut_section, sequence, movie_scene, camera_binding) -> None:
    """Best-effort binding for camera cut sections across UE versions."""
    if not camera_cut_section or not camera_binding:
        return

    binding_id = _make_object_binding_id(sequence, movie_scene, camera_binding)
    if binding_id is None:
        print("[WorkerCreateSequence] WARNING: Could not create camera binding id; leaving Camera Cuts unbound")
        return

    # Try direct setters
    for setter_name in ("set_camera_binding_id", "set_camera_binding", "set_camera"):
        setter = getattr(camera_cut_section, setter_name, None)
        if callable(setter):
            try:
                setter(binding_id)
                print(f"[WorkerCreateSequence] ✓ Bound camera via {setter_name}")
                try:
                    getter = getattr(camera_cut_section, "get_camera_binding_id", None)
                    if callable(getter):
                        current = getter()
                        print(f"[WorkerCreateSequence]   Camera binding id now: {current}")
                except Exception:
                    pass
                return
            except Exception:
                continue

    # Try setting the property directly
    try:
        camera_cut_section.set_editor_property("camera_binding_id", binding_id)
        print("[WorkerCreateSequence] ✓ Bound camera via set_editor_property(camera_binding_id)")
        try:
            getter = getattr(camera_cut_section, "get_camera_binding_id", None)
            if callable(getter):
                current = getter()
                print(f"[WorkerCreateSequence]   Camera binding id now: {current}")
        except Exception:
            pass
        return
    except Exception:
        pass

    _debug_list_methods(camera_cut_section, "CameraCutSection", "camera")
    _debug_list_methods(camera_cut_section, "CameraCutSection", "bind")
    print("[WorkerCreateSequence] WARNING: No compatible camera binding setter found on section")


def _load_map(map_asset_path: str) -> None:
    if not map_asset_path:
        return

    # Prefer LevelEditorSubsystem.load_level for consistency with other scripts
    try:
        level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if level_editor:
            print(f"[WorkerCreateSequence] Loading map via LevelEditorSubsystem: {map_asset_path}")
            ok = level_editor.load_level(map_asset_path)
            if ok:
                print("[WorkerCreateSequence] ✓ Map loaded")
                return
            print("[WorkerCreateSequence] WARNING: LevelEditorSubsystem.load_level returned False")
    except Exception as e:
        print(f"[WorkerCreateSequence] WARNING: LevelEditorSubsystem.load_level failed: {e}")

    # Fallback: EditorLevelLibrary.load_level
    load_level = getattr(unreal.EditorLevelLibrary, "load_level", None)
    if callable(load_level):
        print(f"[WorkerCreateSequence] Loading map via EditorLevelLibrary.load_level: {map_asset_path}")
        if load_level(map_asset_path):
            print("[WorkerCreateSequence] ✓ Map loaded")
            return

    raise RuntimeError(f"Failed to load map: {map_asset_path}")


def _find_actor_by_name(name_or_label: str):
    try:
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
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


def _load_blueprint_class(blueprint_asset_path: str):
    if not blueprint_asset_path:
        return None

    # Accept either '/Game/Path/BP_Name' or '/Game/Path/BP_Name.BP_Name'
    normalized = blueprint_asset_path
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]

    # Try EditorAssetLibrary.load_blueprint_class if available
    loader = getattr(unreal.EditorAssetLibrary, "load_blueprint_class", None)
    if callable(loader):
        for p in (blueprint_asset_path, normalized):
            try:
                cls = loader(p)
                if cls:
                    return cls
            except Exception:
                continue

    # Fallback: load_asset and use generated_class
    asset = unreal.load_asset(normalized)
    if asset is None:
        # As a last resort, try original path
        asset = unreal.load_asset(blueprint_asset_path)
        if asset is None:
            return None

    gen_cls = getattr(asset, "generated_class", None)
    if gen_cls:
        return gen_cls

    # Last-ditch: try loading generated class by name
    # '/Game/Path/BP_Name' -> '/Game/Path/BP_Name.BP_Name_C'
    try:
        base_name = normalized.split("/")[-1]
        generated = f"{normalized}.{base_name}_C"
        cls = unreal.load_class(None, generated)
        if cls:
            return cls
    except Exception:
        pass
    return None


def _spawn_actor_from_blueprint(blueprint_asset_path: str, desired_label: str):
    cls = _load_blueprint_class(blueprint_asset_path)
    if not cls:
        raise RuntimeError(f"Failed to load blueprint class: {blueprint_asset_path}")

    spawn = getattr(unreal.EditorLevelLibrary, "spawn_actor_from_class", None)
    if not callable(spawn):
        raise RuntimeError("EditorLevelLibrary.spawn_actor_from_class is not available")

    actor = spawn(cls, spawn_location, spawn_rotation)
    if not actor:
        raise RuntimeError("Failed to spawn actor")

    # Set label so we can find it next time
    try:
        set_label = getattr(actor, "set_actor_label", None)
        if callable(set_label) and desired_label:
            set_label(desired_label)
            print(f"[WorkerCreateSequence] ✓ Set actor label: {desired_label}")
    except Exception as e:
        print(f"[WorkerCreateSequence] WARNING: Failed to set actor label: {e}")

    try:
        # Ensure it's visible in editor
        set_hidden = getattr(actor, "set_is_temporarily_hidden_in_editor", None)
        if callable(set_hidden):
            set_hidden(False)
    except Exception:
        pass

    print(f"[WorkerCreateSequence] ✓ Spawned actor: name='{actor.get_name()}'")
    return actor


def _save_current_level_if_requested() -> None:
    try:
        save_current = getattr(unreal.EditorLevelLibrary, "save_current_level", None)
        if callable(save_current):
            ok = save_current()
            print(f"[WorkerCreateSequence] ✓ Saved current level: {ok}")
            return
    except Exception as e:
        print(f"[WorkerCreateSequence] WARNING: save_current_level failed: {e}")

    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        save_all = getattr(unreal.EditorLevelLibrary, "save_all_dirty_levels", None)
        if callable(save_all):
            ok = save_all(world)
            print(f"[WorkerCreateSequence] ✓ Saved dirty levels: {ok}")
    except Exception:
        pass


def _ensure_actor_binding(sequence, map_path: str):
    """Return (binding, level_actor_or_none).

    - actor_binding_mode='sequence_spawnable': add a spawnable from blueprint class
    - actor_binding_mode='level_possessable': find (or spawn) in level, then possess it
    """
    mode = actor_binding_mode

    if mode == "sequence_spawnable":
        cls = _load_blueprint_class(actor_blueprint_class_path)
        if not cls:
            raise RuntimeError(f"Failed to load blueprint class for spawnable: {actor_blueprint_class_path}")

        for fn_name in ("add_spawnable_from_class", "add_spawnable"):
            fn = getattr(sequence, fn_name, None)
            if callable(fn):
                try:
                    binding = fn(cls)
                    if binding:
                        print(f"[WorkerCreateSequence] ✓ Created spawnable binding from blueprint: {actor_blueprint_class_path}")
                        return binding, None
                except Exception:
                    pass

        _debug_list_methods(sequence, "LevelSequence", "spawn")
        raise RuntimeError("Unable to create spawnable from blueprint class")

    if mode in ("level_possessable", "level"):
        _load_map(map_path)
        actor = _find_actor_by_name(actor_name)
        spawned = False
        if actor is None and spawn_actor_if_missing:
            print(f"[WorkerCreateSequence] Actor '{actor_name}' not found; spawning into level from blueprint: {actor_blueprint_class_path}")
            actor = _spawn_actor_from_blueprint(actor_blueprint_class_path, actor_name)
            spawned = True

        if actor is None:
            raise RuntimeError(f"Actor not found in level: {actor_name}")

        if spawned and save_level_if_spawned:
            print("[WorkerCreateSequence] Saving level so binding is not Missing...")
            _save_current_level_if_requested()

        binding = _add_possessable(sequence, actor)
        print(f"[WorkerCreateSequence] ✓ Created possessable binding to level actor: name='{actor.get_name()}'")
        return binding, actor

    raise RuntimeError(f"Unknown actor_binding_mode: {mode}")


def _find_camera_component(actor, component_name: str):
    if actor is None:
        return None

    # Prefer explicit name match among camera-like components
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

    target_lower = (component_name or "").lower()
    for c in components:
        try:
            if c is None:
                continue
            if (c.get_name() or "").lower() == target_lower:
                return c
        except Exception:
            continue

    # Fallback: if there's exactly one camera component, use it
    if len(components) == 1:
        return components[0]

    return None


def _add_possessable(sequence, obj):
    # UE Python API varies across versions
    for fn_name in ("add_possessable", "add_possessable_object"):
        fn = getattr(sequence, fn_name, None)
        if callable(fn):
            try:
                binding = fn(obj)
                if binding:
                    return binding
            except Exception:
                pass

    _debug_list_methods(sequence, "LevelSequence", "possess")
    raise RuntimeError("Unable to add possessable binding (no compatible API found)")

try:
    # Load map first (important for level possessables, and avoids world switching mid-script)
    if map_path:
        try:
            _load_map(map_path)
        except Exception as e:
            print(f"[WorkerCreateSequence] WARNING: Map load failed early: {e}")

    # If requested, resolve startpoint now (after map load)
    start_location = None
    start_rotation = None
    if nav_roam_enabled or spawn_at_startpoint:
        start_mode = (nav_roam_cfg.get("startpoint_mode", "player_start") or "player_start")
        sp = _find_first_startpoint(start_mode)
        if sp is None:
            print(f"[WorkerCreateSequence] WARNING: No StartPoint found (mode={start_mode}); using spawn_location from config")
        else:
            try:
                start_location = sp.get_actor_location()
                start_rotation = sp.get_actor_rotation()
                print(f"[WorkerCreateSequence] ✓ StartPoint: {sp.get_name()} loc={start_location} rot={start_rotation}")
            except Exception as e:
                print(f"[WorkerCreateSequence] WARNING: Failed reading StartPoint transform: {e}")

    # If we spawn a level actor (possessable mode), optionally spawn it at the startpoint
    if spawn_at_startpoint and start_location is not None:
        try:
            spawn_location = start_location
            if start_rotation is not None:
                spawn_rotation = start_rotation
            print(f"[WorkerCreateSequence] ✓ Using StartPoint as spawn transform")
        except Exception:
            pass

    # Ensure output directory exists
    print(f"[WorkerCreateSequence] Ensuring directory exists: {output_dir}")
    if not unreal.EditorAssetLibrary.does_directory_exist(output_dir):
        unreal.EditorAssetLibrary.make_directory(output_dir)
        print(f"[WorkerCreateSequence] ✓ Created directory")
    else:
        print(f"[WorkerCreateSequence] ✓ Directory exists")

    # Create LevelSequence asset
    print(f"[WorkerCreateSequence] Creating LevelSequence asset...")
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.LevelSequenceFactoryNew()
    
    sequence = asset_tools.create_asset(
        sequence_name,
        output_dir,
        unreal.LevelSequence,
        factory
    )
    
    if not sequence:
        print("[WorkerCreateSequence] ERROR: Failed to create LevelSequence asset")
        sys.exit(1)
    
    asset_path = sequence.get_path_name()
    print(f"[WorkerCreateSequence] ✓ Created sequence: {asset_path}")
    
    # Set basic properties
    fps = sequence_config.get("fps", 30)
    duration_seconds = sequence_config.get("duration_seconds", 60.0)
    total_frames = int(fps * duration_seconds)
    
    movie_scene = sequence.get_movie_scene()
    
    # Set frame rate
    try:
        movie_scene.set_display_rate(unreal.FrameRate(fps, 1))
        print(f"[WorkerCreateSequence] ✓ Set frame rate: {fps} fps")
    except Exception as e:
        print(f"[WorkerCreateSequence] WARNING: Could not set frame rate: {e}")
    
    # Set playback range
    try:
        movie_scene.set_playback_range(0, total_frames)
        print(f"[WorkerCreateSequence] ✓ Set playback range: 0-{total_frames} ({duration_seconds}s)")
    except Exception as e:
        print(f"[WorkerCreateSequence] WARNING: Could not set playback range: {e}")
    
    # Add camera cuts bound to actor (level possessable or sequence spawnable) if requested
    actor_binding = None
    bound_level_actor = None
    needs_actor_binding = bool(sequence_config.get("add_camera", False)) or bool(write_transform_keys)
    if needs_actor_binding:
        actor_binding, bound_level_actor = _ensure_actor_binding(sequence, map_path)

    # If NavRoam is enabled, generate keys from NavMesh and override transform_keys_cfg
    if nav_roam_enabled:
        try:
            world = _get_world()
            nav = _get_nav_system(world)
            _wait_for_navigation_ready(nav, world, float(nav_roam_cfg.get("nav_build_wait_seconds", 10.0)))
            seed = nav_roam_cfg.get("seed", None)
            if seed is not None:
                try:
                    random.seed(int(seed))
                    print(f"[WorkerCreateSequence] ✓ NavRoam seed: {seed}")
                except Exception:
                    pass

            start = start_location if start_location is not None else spawn_location
            nav_points = _build_multi_leg_nav_path(nav, world, start, nav_roam_cfg)
            if len(nav_points) < 2:
                raise RuntimeError("NavRoam produced too few points")

            key_interval_seconds = float(nav_roam_cfg.get("key_interval_seconds", 0.25))
            key_interval_frames = max(1, int(round(float(fps) * key_interval_seconds)))
            key_count = max(2, int(math.floor(float(total_frames) / float(key_interval_frames))) + 1)
            samples = _resample_by_distance(nav_points, key_count)

            z_offset_cm = float(nav_roam_cfg.get("z_offset_cm", 0.0))
            if abs(z_offset_cm) > 0.001:
                samples = [unreal.Vector(p.x, p.y, p.z + z_offset_cm) for p in samples]

            # Prefer linear interpolation for safety (avoid cubic overshoot through walls)
            interp_override = nav_roam_cfg.get("interpolation", None)
            if interp_override:
                transform_key_interp = (str(interp_override) or transform_key_interp).lower()

            def yaw_degrees(a: unreal.Vector, b: unreal.Vector) -> float:
                dx = b.x - a.x
                dy = b.y - a.y
                if abs(dx) < 1e-4 and abs(dy) < 1e-4:
                    return 0.0
                return float(math.degrees(math.atan2(dy, dx)))

            keys = []
            for i, p in enumerate(samples):
                frame = i * key_interval_frames
                if frame > total_frames:
                    frame = total_frames
                t = float(frame) / float(fps)
                if i < len(samples) - 1:
                    yaw = yaw_degrees(p, samples[i + 1])
                else:
                    yaw = yaw_degrees(samples[i - 1], p) if i > 0 else 0.0

                keys.append(
                    {
                        "time_seconds": t,
                        "location": {"x": float(p.x), "y": float(p.y), "z": float(p.z)},
                        "rotation": {"pitch": 0.0, "yaw": float(yaw), "roll": 0.0},
                    }
                )

            transform_keys_cfg = keys
            write_transform_keys = True
            print(f"[WorkerCreateSequence] ✓ NavRoam generated {len(keys)} keys")
        except Exception as e:
            print(f"[WorkerCreateSequence] WARNING: NavRoam failed: {e}")
            import traceback
            traceback.print_exc()

    if sequence_config.get("add_camera", False):
        print("[WorkerCreateSequence] Adding camera cuts bound to scene actor...")

        try:
            camera_binding = actor_binding

            # If we're possessing a level actor, try binding cuts to its Camera component (more robust for renders)
            if bound_level_actor is not None and camera_component_name:
                cam_comp = _find_camera_component(bound_level_actor, camera_component_name)
                if cam_comp is not None:
                    try:
                        camera_binding = _add_possessable(sequence, cam_comp)
                        print(f"[WorkerCreateSequence] ✓ Using camera component binding: {cam_comp.get_name()}")
                    except Exception as e:
                        print(f"[WorkerCreateSequence] WARNING: Failed to bind camera component; falling back to actor binding: {e}")

            # Add Camera Cuts Track
            print("[WorkerCreateSequence]   Adding Camera Cuts Track...")
            camera_cut_track = _create_camera_cuts_track(sequence, movie_scene)
            print("[WorkerCreateSequence] ✓ Created Camera Cuts Track")

            # Add a section to the camera cut track
            print("[WorkerCreateSequence]   Adding Camera Cut Section...")
            camera_cut_section = camera_cut_track.add_section()
            if not camera_cut_section:
                raise RuntimeError("Failed to create camera cut section")

            # Set the section range to cover the entire sequence
            try:
                camera_cut_section.set_range(0, total_frames)
                print(f"[WorkerCreateSequence] ✓ Set section range: 0-{total_frames}")
            except Exception as e:
                print(f"[WorkerCreateSequence] WARNING: Could not set section range: {e}")

            # Bind the camera to the section
            # Note: We bind to the actor binding; UE will use its camera component.
            _try_bind_camera_cut_section(camera_cut_section, sequence, movie_scene, camera_binding)

        except Exception as e:
            print(f"[WorkerCreateSequence] WARNING: Failed to add camera cuts: {e}")
            import traceback
            traceback.print_exc()

    transform_keys_written = False
    if write_transform_keys:
        if not actor_binding:
            print("[WorkerCreateSequence] WARNING: write_transform_keys=true but no actor binding was created")
        else:
            print("[WorkerCreateSequence] Adding transform keys to actor binding...")
            try:
                _sanitize_rotation_keys(transform_keys_cfg, force_zero_pitch_roll, max_yaw_rate_deg_per_sec)
                _write_transform_keys(actor_binding, int(fps), int(total_frames), transform_keys_cfg)
                transform_keys_written = True
            except Exception as e:
                print(f"[WorkerCreateSequence] WARNING: Failed to write transform keys: {e}")
                import traceback
                traceback.print_exc()
    
    # Save asset
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(sequence)
        print(f"[WorkerCreateSequence] ✓ Saved asset")
    except Exception as e:
        print(f"[WorkerCreateSequence] WARNING: Save may have failed: {e}")
    
    print("[WorkerCreateSequence] ========================================")
    print(f"[WorkerCreateSequence] ✓ Job completed successfully")
    print(f"[WorkerCreateSequence] Asset: {asset_path}")
    print(f"[WorkerCreateSequence] Location: {output_dir}")
    if sequence_config.get("add_camera", False):
        print(f"[WorkerCreateSequence] Camera Cuts Track: Added")
    if write_transform_keys:
        print(f"[WorkerCreateSequence] Transform Keys: {'Written' if transform_keys_written else 'NOT written'}")
    print("[WorkerCreateSequence] ========================================")
    
    sys.exit(0)

except Exception as e:
    print(f"[WorkerCreateSequence] ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
