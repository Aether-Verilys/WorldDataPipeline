"""Key frame track utilities for UE Level Sequence."""
from __future__ import annotations

import math
from typing import Optional

import unreal


def yaw_degrees_xy(a: unreal.Vector, b: unreal.Vector) -> float:
    """Calculate yaw angle in degrees from point a to point b on XY plane.
    
    Args:
        a: Start point
        b: End point
    
    Returns:
        Yaw angle in degrees
    """
    dx = b.x - a.x
    dy = b.y - a.y
    if abs(dx) < 1e-4 and abs(dy) < 1e-4:
        return 0.0
    return float(math.degrees(math.atan2(dy, dx)))


def calculate_pitch_from_slope(a: unreal.Vector, b: unreal.Vector, max_pitch_deg: float = 25.0) -> float:
    """Calculate camera pitch angle from slope between two points.
    
    Uphill: positive pitch (look up)
    Downhill: negative pitch (look down)
    
    Args:
        a: Start point
        b: End point
        max_pitch_deg: Maximum pitch angle clamp (default: 25 degrees)
    
    Returns:
        Pitch angle in degrees, clamped to [-max_pitch_deg, max_pitch_deg]
    """
    horizontal_dist = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2)
    if horizontal_dist < 1.0:  # Avoid division by zero
        return 0.0

    height_diff = b.z - a.z
    slope_angle = math.degrees(math.atan2(height_diff, horizontal_dist))

    if abs(slope_angle) > max_pitch_deg:
        slope_angle = max_pitch_deg if slope_angle > 0 else -max_pitch_deg

    return float(slope_angle)


def channel_add_key(channel, frame: int, value):
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


def apply_key_interpolation(scripting_key, mode: str) -> None:
    """Apply interpolation mode to a scripting key."""
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


def get_transform_channels(section):
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

    # Debug helper
    try:
        methods = [m for m in dir(section) if "channel" in m.lower()]
        methods = sorted(set(methods))
        print(f"[KeyFrameTrack] DEBUG TransformSection methods (contains='channel'): {methods}")
    except Exception:
        pass
    
    return []


def normalize_angle_continuous(angles_deg):
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


def sanitize_rotation_keys(
    keys_cfg, 
    zero_pitch_roll: bool, 
    max_yaw_rate_deg_per_sec: Optional[float], 
    preserve_pitch: bool = False, 
    max_pitch_rate_deg_per_sec: float = 20.0
) -> None:
    """Sanitize rotation keys: normalize angles, clamp rates, optionally zero pitch/roll."""
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
            # 如果preserve_pitch=True，则保留pitch，只清零roll
            if not preserve_pitch:
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
        continuous_yaws = normalize_angle_continuous(yaws)

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

    # 对pitch进行平滑处理（如果preserve_pitch=True）
    if preserve_pitch and len(rot_refs) > 0:
        pitches = []
        for rot in rot_refs:
            pitches.append(rot.get("pitch", 0.0))
        
        if len(times) == len(pitches) and len(pitches) > 1:
            smoothed_pitches = [float(pitches[0])]
            for i in range(1, len(pitches)):
                prev = smoothed_pitches[-1]
                target = float(pitches[i])
                dt = max(1e-3, times[i] - times[i - 1])
                max_delta = max_pitch_rate_deg_per_sec * dt
                delta = target - prev
                
                # 限制变化速率
                if delta > max_delta:
                    delta = max_delta
                elif delta < -max_delta:
                    delta = -max_delta
                
                new_pitch = prev + delta
                
                # 限制pitch在[-15, 15]度范围内
                new_pitch = max(-15.0, min(15.0, new_pitch))
                smoothed_pitches.append(new_pitch)
            
            # 应用平滑后的pitch值
            for rot, pitch in zip(rot_refs, smoothed_pitches):
                rot["pitch"] = float(pitch)

    msg = f"[KeyFrameTrack] ✓ Sanitized {count} keys: yaw continuous"
    if max_yaw_rate_deg_per_sec:
        msg += f", yaw rate ≤ {max_yaw_rate_deg_per_sec:.1f} deg/s"
    if preserve_pitch:
        msg += f", pitch smoothed (rate ≤ {max_pitch_rate_deg_per_sec:.1f} deg/s, range [-15, 15])"
    elif zero_pitch_roll:
        msg += ", pitch=0, roll=0"
    print(msg)


def write_transform_keys(
    binding, 
    fps: int, 
    total_frames: int, 
    keys_cfg, 
    transform_key_interp: str = "auto"
):
    """Write transform keys on the binding so the sequence animates the actor."""
    track_class = getattr(unreal, "MovieScene3DTransformTrack", None)
    if track_class is None:
        raise RuntimeError("MovieScene3DTransformTrack class not found in unreal module")

    # Create transform track on the binding
    add_track = getattr(binding, "add_track", None)
    if not callable(add_track):
        # Debug helper
        try:
            methods = [m for m in dir(binding) if "track" in m.lower()]
            methods = sorted(set(methods))
            print(f"[KeyFrameTrack] DEBUG Binding methods (contains='track'): {methods}")
        except Exception:
            pass
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

    channels = get_transform_channels(section)
    if len(channels) < 6:
        raise RuntimeError(f"Unable to access transform section channels (got {len(channels)})")

    # Typical order: loc(x,y,z), rot(x,y,z), scale(x,y,z)
    # Rotation channels in UE are usually: X=Roll, Y=Pitch, Z=Yaw
    loc = channels[0:3]
    rot = channels[3:6]  # rot[0]=X(Roll), rot[1]=Y(Pitch), rot[2]=Z(Yaw)
    scl = channels[6:9] if len(channels) >= 9 else []

    def _as_float(v, default=0.0) -> float:
        try:
            return float(v)
        except Exception:
            return float(default)

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

    print(f"[KeyFrameTrack] Writing {len(keys_cfg)} transform keys...")

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
        
        # Rotation: sanitize already happened via sanitize_rotation_keys if needed
        rp = _as_float(rot_cfg.get("pitch", 0.0))
        ry = _as_float(rot_cfg.get("yaw", 0.0))
        rr = _as_float(rot_cfg.get("roll", 0.0))

        sx = sy = sz = 1.0
        if isinstance(scl_cfg, dict):
            sx = _as_float(scl_cfg.get("x", 1.0), 1.0)
            sy = _as_float(scl_cfg.get("y", 1.0), 1.0)
            sz = _as_float(scl_cfg.get("z", 1.0), 1.0)

        try:
            kx = channel_add_key(loc[0], frame, lx)
            ky = channel_add_key(loc[1], frame, ly)
            kz = channel_add_key(loc[2], frame, lz)
            apply_key_interpolation(kx, transform_key_interp)
            apply_key_interpolation(ky, transform_key_interp)
            apply_key_interpolation(kz, transform_key_interp)
        except Exception as e:
            raise RuntimeError(f"Failed adding location keys at frame {frame}: {e}")

        try:
            # UE rotation channel order: X=Roll, Y=Pitch, Z=Yaw
            kr = channel_add_key(rot[0], frame, rr)      # X = Roll
            kp = channel_add_key(rot[1], frame, rp)      # Y = Pitch
            kyaw = channel_add_key(rot[2], frame, ry)    # Z = Yaw
            apply_key_interpolation(kr, transform_key_interp)
            apply_key_interpolation(kp, transform_key_interp)
            apply_key_interpolation(kyaw, transform_key_interp)
        except Exception as e:
            raise RuntimeError(f"Failed adding rotation keys at frame {frame}: {e}")

        if scl:
            try:
                ksx = channel_add_key(scl[0], frame, sx)
                ksy = channel_add_key(scl[1], frame, sy)
                ksz = channel_add_key(scl[2], frame, sz)
                apply_key_interpolation(ksx, transform_key_interp)
                apply_key_interpolation(ksy, transform_key_interp)
                apply_key_interpolation(ksz, transform_key_interp)
            except Exception:
                # Scale isn't essential for this test
                pass

    print("[KeyFrameTrack] ✓ Wrote transform keys")
