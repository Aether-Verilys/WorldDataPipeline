"""
Job Manifest Utilities
Provides functions for reading, validating, and updating job manifests and status files.
"""
import json
import os
import time
from typing import Dict, Any, Optional
from pathlib import Path


# ==============================================================================
# Manifest Schema Validation
# ==============================================================================

REQUIRED_FIELDS = {
    "job_id": str,
    "map": str,
    "sequence": str,
    "frame_range": dict,
}

OPTIONAL_FIELDS = {
    "project": str,
    "camera": dict,
    "render": dict,
    "post_process": list,
    "priority": int,
    "retries": int,
    "metadata": dict,
    "callback": dict,
}


def validate_manifest(manifest: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate job manifest structure
    
    Returns:
        (is_valid, error_message)
    """
    # Check required fields
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in manifest:
            return False, f"Missing required field: {field}"
        if not isinstance(manifest[field], expected_type):
            return False, f"Field '{field}' must be {expected_type.__name__}"
    
    # Validate frame_range
    frame_range = manifest.get("frame_range", {})
    if "start_frame" not in frame_range or "end_frame" not in frame_range:
        return False, "frame_range must contain start_frame and end_frame"
    
    if not isinstance(frame_range["start_frame"], int) or not isinstance(frame_range["end_frame"], int):
        return False, "start_frame and end_frame must be integers"
    
    if frame_range["start_frame"] > frame_range["end_frame"]:
        return False, "start_frame must be <= end_frame"
    
    # Validate optional camera field
    if "camera" in manifest:
        camera = manifest["camera"]
        if not isinstance(camera, dict):
            return False, "camera must be a dict"
    
    # Validate optional render field
    if "render" in manifest:
        render = manifest["render"]
        if not isinstance(render, dict):
            return False, "render must be a dict"
        if "enabled" in render and not isinstance(render["enabled"], bool):
            return False, "render.enabled must be a boolean"
    
    return True, None


# ==============================================================================
# Manifest I/O
# ==============================================================================

def read_manifest(manifest_path: str) -> Dict[str, Any]:
    """
    Read and parse job manifest from JSON file
    
    Raises:
        FileNotFoundError: if manifest file doesn't exist
        json.JSONDecodeError: if manifest is not valid JSON
        ValueError: if manifest fails validation
    """
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    is_valid, error = validate_manifest(manifest)
    if not is_valid:
        raise ValueError(f"Invalid manifest: {error}")
    
    return manifest


def write_manifest(manifest: Dict[str, Any], output_path: str, atomic: bool = True) -> str:
    """
    Write manifest to JSON file
    
    Args:
        manifest: manifest dict
        output_path: output file path
        atomic: if True, write to temp file then rename (atomic)
    
    Returns:
        final file path
    """
    is_valid, error = validate_manifest(manifest)
    if not is_valid:
        raise ValueError(f"Invalid manifest: {error}")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    if atomic:
        temp_path = output_path + ".tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, output_path)
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    return output_path


# ==============================================================================
# Status File Management
# ==============================================================================

class JobStatus:
    """Job status constants"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def get_status_path(job_id: str, base_dir: str = None) -> str:
    """Get status file path for a job"""
    if base_dir is None:
        base_dir = os.path.join(os.path.dirname(__file__), "..", "jobs", "status")
    
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, f"{job_id}.status.json")


def read_status(job_id: str, base_dir: str = None) -> Optional[Dict[str, Any]]:
    """Read job status file, return None if not exists"""
    status_path = get_status_path(job_id, base_dir)
    if not os.path.exists(status_path):
        return None
    
    with open(status_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_status(
    job_id: str,
    status: str,
    message: str = "",
    details: Dict[str, Any] = None,
    base_dir: str = None
) -> str:
    """
    Write job status file
    
    Args:
        job_id: job identifier
        status: one of JobStatus constants
        message: human-readable message
        details: additional details dict
        base_dir: base directory for status files
    
    Returns:
        status file path
    """
    status_path = get_status_path(job_id, base_dir)
    
    status_data = {
        "job_id": job_id,
        "status": status,
        "message": message,
        "timestamp": time.time(),
        "timestamp_readable": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    if details:
        status_data["details"] = details
    
    # Atomic write
    temp_path = status_path + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(status_data, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, status_path)
    
    return status_path


def update_status_progress(
    job_id: str,
    current_frame: int,
    total_frames: int,
    base_dir: str = None
) -> str:
    """Update job progress in status file"""
    existing = read_status(job_id, base_dir)
    details = existing.get("details", {}) if existing else {}
    details["current_frame"] = current_frame
    details["total_frames"] = total_frames
    details["progress_pct"] = round(100 * current_frame / total_frames, 2)
    
    return write_status(
        job_id,
        JobStatus.IN_PROGRESS,
        f"Processing frame {current_frame}/{total_frames}",
        details,
        base_dir
    )


# ==============================================================================
# Output Path Helpers
# ==============================================================================

def get_output_paths(manifest: Dict[str, Any]) -> Dict[str, str]:
    """
    Compute output paths for camera export and render based on manifest
    
    Returns:
        dict with keys: camera_export_dir, render_output_dir
    """
    job_id = manifest["job_id"]
    
    # Default base output directory
    base_output = manifest.get("base_output_dir", os.path.join(os.path.dirname(__file__), "..", "output"))
    
    paths = {}
    
    # Camera export path
    if "camera" in manifest:
        camera_config = manifest["camera"]
        if "export_path" in camera_config:
            paths["camera_export_dir"] = camera_config["export_path"]
        else:
            paths["camera_export_dir"] = os.path.join(base_output, job_id, "camera")
    
    # Render output path
    if "render" in manifest:
        render_config = manifest["render"]
        if "output_path" in render_config:
            paths["render_output_dir"] = render_config["output_path"]
        else:
            paths["render_output_dir"] = os.path.join(base_output, job_id, "renders")
    
    return paths


def ensure_output_dirs(manifest: Dict[str, Any]) -> Dict[str, str]:
    """Create output directories and return paths"""
    paths = get_output_paths(manifest)
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    return paths


# ==============================================================================
# Job Discovery
# ==============================================================================

def discover_pending_jobs(watch_dir: str) -> list[str]:
    """
    Discover pending job manifests in watch directory
    
    Returns:
        list of manifest file paths (sorted by modification time, oldest first)
    """
    if not os.path.exists(watch_dir):
        return []
    
    manifest_files = []
    for filename in os.listdir(watch_dir):
        if filename.endswith(".json") and not filename.endswith(".tmp"):
            full_path = os.path.join(watch_dir, filename)
            if os.path.isfile(full_path):
                manifest_files.append(full_path)
    
    # Sort by modification time (oldest first)
    manifest_files.sort(key=lambda p: os.path.getmtime(p))
    return manifest_files


def mark_job_processing(manifest_path: str) -> str:
    """
    Move manifest from inbox to processing directory
    
    Returns:
        new path in processing directory
    """
    inbox_dir = os.path.dirname(manifest_path)
    processing_dir = os.path.join(os.path.dirname(inbox_dir), "processing")
    os.makedirs(processing_dir, exist_ok=True)
    
    filename = os.path.basename(manifest_path)
    processing_path = os.path.join(processing_dir, filename)
    
    os.replace(manifest_path, processing_path)
    return processing_path


def mark_job_completed(manifest_path: str, success: bool = True) -> str:
    """
    Move manifest from processing to completed/failed directory
    
    Returns:
        new path in completed/failed directory
    """
    processing_dir = os.path.dirname(manifest_path)
    target_dir = os.path.join(os.path.dirname(processing_dir), "completed" if success else "failed")
    os.makedirs(target_dir, exist_ok=True)
    
    filename = os.path.basename(manifest_path)
    target_path = os.path.join(target_dir, filename)
    
    os.replace(manifest_path, target_path)
    return target_path
