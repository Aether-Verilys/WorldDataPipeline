from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class GenerationContext:
    """Shared context for sequence generation (UE world, navigation, paths)."""
    
    nav: Any
    """Navigation system instance."""
    
    world: Any
    """Unreal Engine world instance."""
    
    map_path: str
    """Path to the UE map asset (e.g., '/Game/Maps/MyMap')."""
    
    map_name: str
    """Name of the map (extracted from map_path)."""
    
    output_dir: str
    """Output directory for generated sequences."""
    
    actor_blueprint_class_path: str
    """Path to the actor blueprint class."""


@dataclass(frozen=True)
class TimingConfig:
    """Timing and speed configuration for sequences."""
    
    fps: int
    """Frames per second for the sequence."""
    
    base_duration_seconds: float
    """Base duration of the sequence in seconds."""
    
    fixed_speed_cfg: Optional[float]
    """Fixed speed in cm/s (None = variable speed based on duration)."""
    
    strict_duration: bool
    """If True with fixed_speed, may not complete full path to maintain duration."""


@dataclass(frozen=True)
class CameraConfig:
    """Camera behavior configuration."""
    
    camera_pitch_from_slope: bool
    """Calculate camera pitch from terrain slope."""
    
    max_camera_pitch: float
    """Maximum camera pitch angle in degrees."""
    
    max_pitch_rate: float
    """Maximum pitch change rate in degrees/second."""
    
    force_zero_pitch_roll: bool
    """Force pitch and roll to zero (override calculated values)."""
    
    max_yaw_rate_deg_per_sec: Optional[float]
    """Maximum yaw change rate in degrees/second (None = unlimited)."""


@dataclass(frozen=True)
class PathConfig:
    """Path generation and interpolation configuration."""
    
    roam_cfg: Dict[str, Any]
    """Navigation roam configuration (seed, radius, z_offset, etc)."""
    
    seq_cfg: Dict[str, Any]
    """Sequence configuration (parent config for nav path generation)."""
    
    z_offset_cm: float
    """Vertical offset in centimeters to apply to path points."""
    
    interp_override: Optional[str]
    """Interpolation mode override ('linear', 'cubic', etc)."""
    
    base_transform_key_interp: str
    """Base interpolation mode for transform keys."""


@dataclass(frozen=True)
class ExportConfig:
    """Camera export configuration."""
    
    camera_export_cfg: Optional[Dict[str, Any]]
    """Camera export settings (enabled, binding_camera, etc)."""
    
    ue_config: Dict[str, Any]
    """UE configuration (output paths, project settings, etc)."""
