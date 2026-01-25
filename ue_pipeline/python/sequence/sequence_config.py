from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class GenerationContext:
    nav: Any
    world: Any
    map_path: str
    map_name: str
    output_dir: str
    actor_blueprint_class_path: str


@dataclass(frozen=True)
class TimingConfig:
    fps: int
    base_duration_seconds: float
    fixed_speed_cfg: Optional[float]
    strict_duration: bool


@dataclass(frozen=True)
class CameraConfig:
    camera_pitch_from_slope: bool
    max_camera_pitch: float
    max_pitch_rate: float
    max_yaw_rate_deg_per_sec: Optional[float]


@dataclass(frozen=True)
class PathConfig:
    roam_cfg: Dict[str, Any]
    seq_cfg: Dict[str, Any]
    z_offset_cm: float
    base_transform_key_interp: str


@dataclass(frozen=True)
class ExportConfig:
    camera_export_cfg: Optional[Dict[str, Any]]
    ue_config: Dict[str, Any]
