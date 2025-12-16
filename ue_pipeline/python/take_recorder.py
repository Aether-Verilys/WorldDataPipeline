import unreal
import time

def setup_take_recorder(preset_path: str = "/Game/CameraController/RecorderPreset"):
    """
    Setup Take Recorder with preset
    Returns: panel if successful, None otherwise
    """
    # 检查 Take Recorder 是否启用
    if not unreal.TakeRecorderBlueprintLibrary.is_take_recorder_enabled():
        unreal.log_error("Take Recorder 未启用")
        return None
    
    # 打开 Take Recorder Panel（如果未打开）
    unreal.TakeRecorderBlueprintLibrary.open_take_recorder_panel()
    
    # 获取 Take Recorder Panel
    panel = unreal.TakeRecorderBlueprintLibrary.get_take_recorder_panel()
    if not panel:
        unreal.log_error("无法获取 Take Recorder Panel")
        return None
    
    # 加载 Preset
    preset = unreal.load_asset(preset_path)
    if preset:
        panel.setup_for_recording_take_preset(preset)
        unreal.log(f"✓ Take Recorder Preset 已应用: {preset_path}")
    else:
        unreal.log_warning(f"Preset 未找到: {preset_path}")
    
    return panel

def start_recording(panel=None):
    """Start recording with Take Recorder"""
    if not panel:
        panel = unreal.TakeRecorderBlueprintLibrary.get_take_recorder_panel()
    
    if not panel:
        unreal.log_error("无法获取 Take Recorder Panel")
        return False
    
    if unreal.TakeRecorderBlueprintLibrary.is_recording():
        unreal.log_warning("已经在录制中")
        return False
    
    panel.start_recording()
    unreal.log("▶ 开始录制...")
    return True

def stop_recording():
    """Stop recording"""
    if unreal.TakeRecorderBlueprintLibrary.is_recording():
        unreal.TakeRecorderBlueprintLibrary.stop_recording()
        unreal.log("■ 停止录制")
        return True
    return False

def is_recording():
    """Check if currently recording"""
    return unreal.TakeRecorderBlueprintLibrary.is_recording()

def get_last_recorded_sequence(panel=None):
    """Get the last recorded sequence"""
    if not panel:
        panel = unreal.TakeRecorderBlueprintLibrary.get_take_recorder_panel()
    
    if panel:
        return panel.get_last_recorded_level_sequence()
    return None


# ==============================================================================
# Manifest-driven API
# ==============================================================================

def record_take_from_manifest(manifest: dict) -> dict:
    """
    Record a take based on job manifest
    
    Args:
        manifest: job manifest dict containing:
            - take_recorder: config with preset_path, duration, etc. (optional)
    
    Returns:
        dict with recording results
    """
    take_config = manifest.get("take_recorder", {})
    
    if not take_config.get("enabled", False):
        unreal.log("[TakeRecorder] Take recording not enabled in manifest")
        return {"status": "skipped", "reason": "not enabled"}
    
    preset_path = take_config.get("preset_path", "/Game/CameraController/RecorderPreset")
    duration = take_config.get("duration", 5.0)
    
    unreal.log(f"[TakeRecorder] Setting up with preset: {preset_path}")
    
    # Setup recorder
    panel = setup_take_recorder(preset_path)
    if not panel:
        raise RuntimeError("Failed to setup Take Recorder")
    
    # Start recording
    if not start_recording(panel):
        raise RuntimeError("Failed to start recording")
    
    unreal.log(f"[TakeRecorder] Recording for {duration} seconds...")
    time.sleep(duration)
    
    # Stop recording
    stop_recording()
    
    # Get recorded sequence
    sequence = get_last_recorded_sequence(panel)
    sequence_path = sequence.get_path_name() if sequence else None
    
    unreal.log(f"[TakeRecorder] ✓ Recording completed: {sequence_path}")
    
    return {
        "status": "success",
        "sequence": sequence_path,
        "duration": duration
    }

