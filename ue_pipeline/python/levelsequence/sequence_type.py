from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SequenceJobConfig:
    # Leave empty so worker can auto-derive from map path (e.g. /Game/LevelPrototyping/Sequence)
    output_dir: str = ""
    sequence_count: int = 1
    actor_name: str = "BP_NPC_NavMesh"
    camera_component_name: str = "Camera"
    actor_blueprint_class_path: str = "/Game/FirstPerson/Blueprints/BP_NPC_NavMesh.BP_NPC_NavMesh"
    spawn_actor_if_missing: bool = False
    actor_binding_mode: str = "sequence_spawnable"
    save_level_if_spawned: bool = False
    nav_roam: dict = field(default_factory=dict)
    force_zero_pitch_roll: bool = True
    max_yaw_rate_deg_per_sec: Optional[float] = None
    transform_keys: Optional[list] = None
    transform_key_interp: str = "auto"

    @classmethod
    def from_dict(cls, data: dict) -> "SequenceJobConfig":
        cfg = data or {}
        inst = cls()

        inst.output_dir = cfg.get("output_dir", inst.output_dir)
        inst.sequence_count = int(cfg.get("sequence_count", inst.sequence_count))
        inst.actor_name = cfg.get("actor_name", inst.actor_name)
        inst.camera_component_name = cfg.get("camera_component_name", inst.camera_component_name)
        inst.actor_blueprint_class_path = cfg.get("actor_blueprint_class_path", inst.actor_blueprint_class_path)
        inst.spawn_actor_if_missing = bool(cfg.get("spawn_actor_if_missing", inst.spawn_actor_if_missing))
        inst.actor_binding_mode = (
            cfg.get("actor_binding_mode", inst.actor_binding_mode) or inst.actor_binding_mode
        ).lower()
        inst.save_level_if_spawned = bool(cfg.get("save_level_if_spawned", inst.save_level_if_spawned))
        inst.nav_roam = cfg.get("nav_roam", {}) or {}
        inst.force_zero_pitch_roll = bool(cfg.get("force_zero_pitch_roll", inst.force_zero_pitch_roll))
        inst.transform_keys = cfg.get("transform_keys", inst.transform_keys)
        inst.transform_key_interp = (
            cfg.get("transform_key_interp", inst.transform_key_interp) or inst.transform_key_interp
        ).lower()

        max_yaw = cfg.get("max_yaw_rate_deg_per_sec", None)
        try:
            if max_yaw is not None:
                max_yaw = float(max_yaw)
                if max_yaw <= 0:
                    max_yaw = None
        except Exception:
            max_yaw = None
        inst.max_yaw_rate_deg_per_sec = max_yaw

        return inst


@dataclass
class NavPathResult:
    nav_points: list
    actual_seed: Optional[int] = None


@dataclass
class FixedSpeedResult:
    nav_points: list
    duration_seconds: float
    total_frames: int


@dataclass
class SampleResult:
    samples: list
    key_interval_frames: int


@dataclass
class KeyGenResult:
    transform_keys: list
