import math
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import unreal

try:
	import level_launcher
except Exception:
	level_launcher = None


@dataclass
class NavSequenceConfig:
	# Asset output
	output_dir: str = "/Game/CameraController/Generated"
	sequence_name_prefix: str = "NavCam"

	# Timeline
	fps: int = 30
	duration_seconds: float = 60.0

	# Navigation
	random_point_radius_cm: float = 8000.0
	num_legs: int = 6
	max_random_point_tries: int = 40

	# Camera
	z_offset_cm: float = 170.0
	look_ahead_cm: float = 200.0

	# Sampling / smoothing
	key_interval_seconds: float = 0.25
	min_segment_step_cm: float = 75.0
	interpolation: str = "auto"  # "auto" or "linear"


def _get_world(prefer_pie: bool = True) -> unreal.World:
	if prefer_pie and level_launcher is not None:
		world = level_launcher.get_pie_world()
		if world:
			return world

	# Fallback: editor world
	try:
		return unreal.EditorLevelLibrary.get_editor_world()
	except Exception as e:
		raise RuntimeError(f"Failed to acquire a World (PIE/editor): {e}")


def _get_nav_system(world: unreal.World):
	nav_cls = getattr(unreal, "NavigationSystemV1", None)
	if not nav_cls:
		raise RuntimeError("NavigationSystemV1 is not available. Is the NavigationSystem enabled?")

	# UE versions expose either get_current(world) or get_navigation_system(world)
	getter_names = ["get_current", "get_navigation_system", "get_default_nav_system"]
	for name in getter_names:
		getter = getattr(nav_cls, name, None)
		if callable(getter):
			try:
				nav = getter(world)
				if nav:
					return nav
			except Exception:
				pass

	# As a last resort, some versions allow calling static blueprint-style functions directly
	return nav_cls


def _call_maybe(obj, method_names: Sequence[str], *args, **kwargs):
	last_err = None
	for name in method_names:
		fn = getattr(obj, name, None)
		if callable(fn):
			try:
				return fn(*args, **kwargs)
			except Exception as e:
				last_err = e
	if last_err:
		raise last_err
	raise AttributeError(f"None of these methods exist: {method_names}")


def _random_navigable_point(nav, world: unreal.World, origin: unreal.Vector, radius_cm: float) -> unreal.Vector:
	# Prefer instance methods, then class static methods
	candidates: List[Tuple[object, Sequence[str]]] = [
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
				# Some variants return (success, vector) while others return vector
				result = _call_maybe(target, method_names, *args)
			except Exception:
				continue
			if isinstance(result, tuple) and len(result) >= 2:
				success, point = result[0], result[1]
				if success and isinstance(point, unreal.Vector):
					return point
			if isinstance(result, unreal.Vector):
				return result


	raise RuntimeError("Failed to get random navigable point. Ensure NavMesh is built/available in this world.")


def _project_to_nav(nav, world: unreal.World, point: unreal.Vector) -> unreal.Vector:
	candidates: List[Tuple[object, Sequence[str]]] = [
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


	# If projection isn't available, return original point
	return point


def _find_path_points(nav, world: unreal.World, start: unreal.Vector, end: unreal.Vector) -> List[unreal.Vector]:
	candidates: List[Tuple[object, Sequence[str]]] = [
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

	# Extract points
	if hasattr(nav_path, "path_points"):
		pts = list(getattr(nav_path, "path_points"))
		if pts:
			return pts
	getter = getattr(nav_path, "get_path_points", None)
	if callable(getter):
		pts = list(getter())
		if pts:
			return pts

	raise RuntimeError("NavigationPath returned no points")


def _distance_cm(a: unreal.Vector, b: unreal.Vector) -> float:
	dx = a.x - b.x
	dy = a.y - b.y
	dz = a.z - b.z
	return float(math.sqrt(dx * dx + dy * dy + dz * dz))


def _subdivide_polyline(points: List[unreal.Vector], step_cm: float) -> List[unreal.Vector]:
	if len(points) < 2:
		return points

	out: List[unreal.Vector] = [points[0]]
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


def _build_multi_leg_nav_path(
	nav,
	world: unreal.World,
	cfg: NavSequenceConfig,
	start: Optional[unreal.Vector] = None,
) -> List[unreal.Vector]:
	origin = start
	if origin is None:
		# Use (0,0,0) as seed; random point search works relative to this.
		origin = unreal.Vector(0.0, 0.0, 0.0)

	# Pick a random valid start A
	a = None
	for _ in range(cfg.max_random_point_tries):
		try:
			a = _random_navigable_point(nav, world, origin, cfg.random_point_radius_cm)
			break
		except Exception:
			continue
	if a is None:
		raise RuntimeError("Failed to sample a valid start point A on NavMesh")

	all_points: List[unreal.Vector] = [a]
	current = a

	# Chain multiple legs to make the 1-minute path more complex
	for leg in range(max(1, cfg.num_legs)):
		b = None
		for _ in range(cfg.max_random_point_tries):
			try:
				b = _random_navigable_point(nav, world, current, cfg.random_point_radius_cm)
				if _distance_cm(current, b) > 300.0:
					break
			except Exception:
				continue
		if b is None:
			unreal.log_warning(f"[GenLevelSequence] Leg {leg}: failed to sample destination; stopping early")
			break

		pts = _find_path_points(nav, world, current, b)
		if len(pts) >= 2:
			# Avoid duplicating the first point of each leg
			if _distance_cm(all_points[-1], pts[0]) < 0.1:
				pts = pts[1:]
			all_points.extend(pts)
			current = pts[-1]
		else:
			unreal.log_warning(f"[GenLevelSequence] Leg {leg}: path too short; skipping")

	# Densify for smoother curve editing without risking spline overshoot too much
	all_points = _subdivide_polyline(all_points, cfg.min_segment_step_cm)

	# Project points back to NavMesh (extra safety after subdivision)
	all_points = [_project_to_nav(nav, world, p) for p in all_points]
	return all_points


def _resample_by_distance(points: List[unreal.Vector], sample_count: int) -> List[unreal.Vector]:
	if len(points) < 2:
		return points
	if sample_count <= 2:
		return [points[0], points[-1]]

	# Build cumulative distance
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


def _ensure_directory(dir_path: str) -> None:
	if unreal.EditorAssetLibrary.does_directory_exist(dir_path):
		return
	unreal.EditorAssetLibrary.make_directory(dir_path)


def _create_level_sequence_asset(directory: str, asset_name: str) -> unreal.LevelSequence:
	_ensure_directory(directory)

	asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
	factory = unreal.LevelSequenceFactoryNew()
	seq = asset_tools.create_asset(asset_name, directory, unreal.LevelSequence, factory)
	if not seq:
		raise RuntimeError(f"Failed to create LevelSequence asset: {directory}/{asset_name}")
	return seq


def _set_sequence_timing(sequence: unreal.LevelSequence, fps: int, duration_seconds: float) -> int:
	total_frames = int(round(duration_seconds * fps))
	movie_scene = sequence.get_movie_scene()

	try:
		movie_scene.set_display_rate(unreal.FrameRate(fps, 1))
	except Exception:
		try:
			sequence.set_display_rate(unreal.FrameRate(fps, 1))
		except Exception:
			pass

	# Playback range is [0, total_frames)
	try:
		movie_scene.set_playback_range(0, total_frames)
	except Exception:
		try:
			movie_scene.set_working_range(0.0, float(duration_seconds))
		except Exception:
			pass
	return total_frames


def _add_spawnable_cine_camera(sequence: unreal.LevelSequence):
	# Try the common API first
	adders = [
		(sequence, "add_spawnable_from_class"),
		(sequence, "add_spawnable"),
	]
	for target, name in adders:
		fn = getattr(target, name, None)
		if callable(fn):
			try:
				binding = fn(unreal.CineCameraActor)
				if binding:
					return binding
			except Exception:
				pass
	raise RuntimeError("Failed to add CineCameraActor as a spawnable to the sequence")


def _interp_enum(mode: str):
	mode = (mode or "").strip().lower()
	# Prefer MovieSceneKeyInterpolation when available, else fall back to RichCurveInterpMode
	m = getattr(unreal, "MovieSceneKeyInterpolation", None)
	if m:
		if mode == "linear":
			return getattr(m, "LINEAR", None) or getattr(m, "Linear", None) or m.LINEAR
		return getattr(m, "AUTO", None) or getattr(m, "Auto", None) or m.AUTO

	r = getattr(unreal, "RichCurveInterpMode", None)
	if r:
		if mode == "linear":
			return getattr(r, "RCIM_LINEAR", None) or r.RCIM_LINEAR
		return getattr(r, "RCIM_CUBIC", None) or r.RCIM_CUBIC
	return None


def _set_key_interp(key_obj, interp) -> None:
	if interp is None or key_obj is None:
		return
	for setter in ("set_interpolation_mode", "set_interp_mode", "set_interpolation", "set_interpolation_mode_enum"):
		fn = getattr(key_obj, setter, None)
		if callable(fn):
			try:
				fn(interp)
				return
			except Exception:
				continue


def _seconds_to_frame(fps: int, seconds: float) -> int:
	return int(round(seconds * fps))


def _write_camera_track(
	binding,
	sequence: unreal.LevelSequence,
	nav_points: List[unreal.Vector],
	cfg: NavSequenceConfig,
) -> None:
	total_frames = _set_sequence_timing(sequence, cfg.fps, cfg.duration_seconds)

	# Convert nav polyline into time-sampled points
	key_interval_frames = max(1, _seconds_to_frame(cfg.fps, cfg.key_interval_seconds))
	key_count = max(2, int(math.floor(total_frames / key_interval_frames)) + 1)
	samples = _resample_by_distance(nav_points, key_count)

	# Add Z offset (eye height)
	samples = [unreal.Vector(p.x, p.y, p.z + cfg.z_offset_cm) for p in samples]

	# Create transform track + section
	transform_track = binding.add_track(unreal.MovieScene3DTransformTrack)
	section = transform_track.add_section()
	try:
		section.set_range(0, total_frames)
	except Exception:
		pass

	channels = None
	getter = getattr(section, "get_channels", None)
	if callable(getter):
		channels = list(getter())
	if not channels or len(channels) < 6:
		raise RuntimeError("Unable to access transform section channels; enable Sequencer Scripting plugin")

	tx, ty, tz = channels[0], channels[1], channels[2]
	rx, ry, rz = channels[3], channels[4], channels[5]
	interp = _interp_enum(cfg.interpolation)

	# Compute yaw to face along movement direction
	def yaw_degrees(a: unreal.Vector, b: unreal.Vector) -> float:
		dx = b.x - a.x
		dy = b.y - a.y
		if abs(dx) < 1e-4 and abs(dy) < 1e-4:
			return 0.0
		return float(math.degrees(math.atan2(dy, dx)))

	for i, p in enumerate(samples):
		frame = i * key_interval_frames
		if frame > total_frames:
			frame = total_frames
		frame_number = unreal.FrameNumber(int(frame))

		# Translation
		kx = tx.add_key(frame_number, float(p.x))
		ky = ty.add_key(frame_number, float(p.y))
		kz = tz.add_key(frame_number, float(p.z))
		_set_key_interp(kx, interp)
		_set_key_interp(ky, interp)
		_set_key_interp(kz, interp)

		# Rotation (X=Roll, Y=Pitch, Z=Yaw)
		if i < len(samples) - 1:
			yaw = yaw_degrees(p, samples[i + 1])
		else:
			yaw = yaw_degrees(samples[i - 1], p) if i > 0 else 0.0

		krx = rx.add_key(frame_number, 0.0)
		kry = ry.add_key(frame_number, 0.0)
		krz = rz.add_key(frame_number, yaw)
		_set_key_interp(krx, interp)
		_set_key_interp(kry, interp)
		_set_key_interp(krz, interp)

	# Persist asset
	try:
		unreal.EditorAssetLibrary.save_loaded_asset(sequence)
	except Exception:
		try:
			unreal.EditorAssetLibrary.save_asset(sequence.get_path_name())
		except Exception:
			pass


def generate_nav_camera_sequence(cfg: Optional[NavSequenceConfig] = None, prefer_pie: bool = True) -> str:
	"""Generate a LevelSequence asset with a 60s camera path sampled from NavMesh.

	Returns: sequence asset path (e.g. /Game/CameraController/Generated/NavCam_...)
	"""
	cfg = cfg or NavSequenceConfig()

	world = _get_world(prefer_pie=prefer_pie)
	nav = _get_nav_system(world)

	unreal.log(f"[GenLevelSequence] World: {world.get_name()}")
	unreal.log(f"[GenLevelSequence] Sampling NavMesh path: legs={cfg.num_legs} radius_cm={cfg.random_point_radius_cm}")

	nav_points = _build_multi_leg_nav_path(nav, world, cfg)
	if len(nav_points) < 2:
		raise RuntimeError("Nav path generation returned too few points")

	timestamp = time.strftime("%Y%m%d_%H%M%S")
	asset_name = f"{cfg.sequence_name_prefix}_{timestamp}" if cfg.sequence_name_prefix else f"NavCam_{timestamp}"

	sequence = _create_level_sequence_asset(cfg.output_dir, asset_name)
	binding = _add_spawnable_cine_camera(sequence)

	_write_camera_track(binding, sequence, nav_points, cfg)

	asset_path = sequence.get_path_name()
	unreal.log(f"[GenLevelSequence] ✓ Generated LevelSequence: {asset_path}")
	return asset_path


# ============================================================================
# Manifest-driven API
# ============================================================================

def generate_nav_camera_sequence_from_manifest(manifest: dict) -> dict:
	"""Manifest format (suggested):

	{
	  "nav_sequence": {
		"output_dir": "/Game/CameraController/Generated",
		"sequence_name_prefix": "NavCam",
		"fps": 30,
		"duration_seconds": 60.0,
		"random_point_radius_cm": 8000,
		"num_legs": 6,
		"z_offset_cm": 170,
		"key_interval_seconds": 0.25,
		"min_segment_step_cm": 75,
		"interpolation": "auto"
	  }
	}
	"""
	cfg_dict = manifest.get("nav_sequence", {}) or {}
	allowed = set(getattr(NavSequenceConfig, "__dataclass_fields__", {}).keys())
	cfg = NavSequenceConfig(**{k: v for k, v in cfg_dict.items() if k in allowed})
	prefer_pie = bool(manifest.get("prefer_pie", True))

	seq_path = generate_nav_camera_sequence(cfg, prefer_pie=prefer_pie)
	return {
		"status": "success",
		"sequence": seq_path,
		"fps": cfg.fps,
		"duration_seconds": cfg.duration_seconds,
	}


def main():
	generate_nav_camera_sequence()


if __name__ == "__main__":
	main()
