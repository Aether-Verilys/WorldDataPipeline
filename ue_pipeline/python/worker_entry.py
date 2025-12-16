import unreal
import sys
import time
import json

# Add current directory to path for module imports
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import utilities
import take_recorder
import level_launcher

print("[WorkerEntry] Starting job execution...")

# Parse command line arguments
manifest_path = None
for i, arg in enumerate(sys.argv):
    if arg.startswith("--manifest="):
        manifest_path = arg.split("=", 1)[1]
    elif arg == "--manifest" and i + 1 < len(sys.argv):
        manifest_path = sys.argv[i + 1]

if not manifest_path:
    print("[WorkerEntry] ERROR: No manifest path provided")
    sys.exit(1)

print(f"[WorkerEntry] Manifest: {manifest_path}")

# Read manifest
try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
except Exception as e:
    print(f"[WorkerEntry] ERROR: Failed to read manifest: {e}")
    sys.exit(1)

job_id = manifest.get("job_id", "unknown")
job_type = manifest.get("job_type", "record")
map_path = manifest.get("map")

print(f"[WorkerEntry] Job ID: {job_id}")
print(f"[WorkerEntry] Job Type: {job_type}")
print(f"[WorkerEntry] Map: {map_path}")

# Validate job type
if job_type != "record":
    print(f"[WorkerEntry] ERROR: Invalid job type '{job_type}', expected 'record'")
    print(f"[WorkerEntry] For render jobs, use worker_render.py instead")
    sys.exit(1)

if not map_path:
    print("[WorkerEntry] ERROR: No map specified in manifest")
    sys.exit(1)


# ==============================================================================
# State Machine Worker - Similar to level_launcher
# ==============================================================================

class JobWorker:
    def __init__(self, map_path, job_id, manifest):
        self.map_path = map_path
        self.job_id = job_id
        self.manifest = manifest
        self.state = "LOAD_MAP"
        self.state_start_time = 0.0
        self.tick_handle = None
        self.level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.take_recorder_panel = None
        self.recording_start_time = 0.0
        
        # Support both old and new config format
        recording_config = manifest.get("recording", {})
        if recording_config:
            # New format: recording.* fields
            self.recording_duration = recording_config.get("recording_duration", 5.0)
            self.pre_recording_wait = recording_config.get("pre_recording_wait", 2.0)  # Default 2s wait after PIE starts
            self.post_recording_wait = recording_config.get("post_recording_wait", 0.0)
        else:
            # Old format: top-level fields (backward compatibility)
            self.recording_duration = manifest.get("recording_duration", 5.0)
            self.pre_recording_wait = manifest.get("pre_recording_wait", 2.0)
            self.post_recording_wait = manifest.get("post_recording_wait", 0.0)
        
        self.timeout = 30.0
        self.keep_playing_after_job = manifest.get("keep_playing_after_recording", False)
        
    def start(self):
        print("[WorkerEntry] Starting state machine...")
        self.set_state("LOAD_MAP")
        self.tick_handle = unreal.register_slate_post_tick_callback(self.on_tick)
        
    def stop(self):
        if self.tick_handle:
            unreal.unregister_slate_post_tick_callback(self.tick_handle)
            self.tick_handle = None
            
    def set_state(self, new_state):
        self.state = new_state
        self.state_start_time = time.time()
        print(f"[WorkerEntry] State -> {new_state}")
        
    def on_tick(self, delta_seconds):
        elapsed = time.time() - self.state_start_time
        
        if self.state == "LOAD_MAP":
            print(f"[WorkerEntry] Loading map: {self.map_path}")
            try:
                if self.level_editor.load_level(self.map_path):
                    print(f"[WorkerEntry] ✓ Map loaded")
                    self.set_state("SETUP_RECORDER")
                else:
                    print(f"[WorkerEntry] ERROR: Failed to load map")
                    self.set_state("ERROR")
            except Exception as e:
                print(f"[WorkerEntry] ERROR: Exception loading map: {e}")
                self.set_state("ERROR")
                
        elif self.state == "SETUP_RECORDER":
            print("[WorkerEntry] Setting up Take Recorder...")
            try:
                self.take_recorder_panel = take_recorder.setup_take_recorder()
                if self.take_recorder_panel:
                    print("[WorkerEntry] ✓ Take Recorder setup complete")
                    self.set_state("START_PIE")
                else:
                    print("[WorkerEntry] ERROR: Failed to setup Take Recorder")
                    self.set_state("ERROR")
            except Exception as e:
                print(f"[WorkerEntry] ERROR: Exception setting up recorder: {e}")
                self.set_state("ERROR")
                
        elif self.state == "START_PIE":
            print("[WorkerEntry] Starting PIE...")
            try:
                self.level_editor.editor_request_begin_play()
                self.set_state("WAIT_PIE_START")
            except Exception as e:
                print(f"[WorkerEntry] ERROR: Failed to start PIE: {e}")
                self.set_state("ERROR")
                
        elif self.state == "WAIT_PIE_START":
            if level_launcher.is_pie_playing():
                print("[WorkerEntry] ✓ PIE is_playing=True")
                self.set_state("WAIT_WORLD_READY")
            elif elapsed > self.timeout:
                print("[WorkerEntry] ERROR: PIE start timeout")
                self.set_state("ERROR")
            elif int(elapsed) % 2 == 0 and elapsed - int(elapsed) < 0.1:
                print(f"[WorkerEntry] Waiting for PIE... {int(elapsed)}s")
                
        elif self.state == "WAIT_WORLD_READY":
            world = level_launcher.get_pie_world()
            if world:
                world_name = world.get_name()
                print(f"[WorkerEntry] DEBUG: PIE world found: {world_name}")
                try:
                    has_begun = hasattr(world, 'has_begun_play')
                    if has_begun:
                        begun = world.has_begun_play()
                        print(f"[WorkerEntry] DEBUG: World.has_begun_play() = {begun}")
                        if begun:
                            print(f"[WorkerEntry] ✓ PIE world BeginPlay called: {world_name}")
                            if self.pre_recording_wait > 0:
                                print(f"[WorkerEntry] Waiting {self.pre_recording_wait}s before recording...")
                                self.set_state("PRE_RECORDING_WAIT")
                            else:
                                print("[WorkerEntry] Starting recording immediately (no pre-recording wait)")
                                self.set_state("START_RECORDING")
                    else:
                        # No has_begun_play method, wait longer
                        if elapsed > 8:
                            print(f"[WorkerEntry] DEBUG: No has_begun_play, assuming ready after 8s")
                            if self.pre_recording_wait > 0:
                                self.set_state("PRE_RECORDING_WAIT")
                            else:
                                self.set_state("START_RECORDING")
                except Exception as e:
                    print(f"[WorkerEntry] DEBUG: Exception checking has_begun_play: {e}")
                    # Assume ready after longer time
                    if elapsed > 8:
                        print(f"[WorkerEntry] ✓ PIE world detected (assumed ready after 8s)")
                        if self.pre_recording_wait > 0:
                            self.set_state("PRE_RECORDING_WAIT")
                        else:
                            self.set_state("START_RECORDING")
            else:
                if int(elapsed) % 2 == 0 and elapsed - int(elapsed) < 0.1:
                    print(f"[WorkerEntry] Waiting for PIE world... {int(elapsed)}s")
                    
        elif self.state == "PRE_RECORDING_WAIT":
            # Wait after PIE starts (for shader compilation, scene initialization, etc.)
            if elapsed >= self.pre_recording_wait:
                print(f"[WorkerEntry] ✓ Pre-recording wait complete ({self.pre_recording_wait}s)")
                self.set_state("START_RECORDING")
            else:
                current_second = int(elapsed)
                if current_second != int(elapsed - delta_seconds):
                    print(f"[WorkerEntry] Pre-recording wait... {current_second + 1}/{int(self.pre_recording_wait)}s")
                
        elif self.state == "START_RECORDING":
            print("[WorkerEntry] ===== STARTING RECORDING =====")
            print(f"[WorkerEntry] PIE is playing: {level_launcher.is_pie_playing()}")
            world = level_launcher.get_pie_world()
            if world:
                print(f"[WorkerEntry] PIE world: {world.get_name()}")
            else:
                print("[WorkerEntry] WARNING: No PIE world detected!")
            
            try:
                if take_recorder.start_recording(self.take_recorder_panel):
                    print("[WorkerEntry] ✓ Recording started")
                    self.recording_start_time = time.time()
                    self.set_state("RECORDING")
                else:
                    print("[WorkerEntry] ERROR: Failed to start recording")
            except Exception as e:
                print(f"[WorkerEntry] ERROR: Exception starting recording: {e}")
                
        elif self.state == "RECORDING":
            recording_elapsed = time.time() - self.recording_start_time
            if recording_elapsed >= self.recording_duration:
                print(f"[WorkerEntry] ✓ Recording duration reached ({self.recording_duration}s)")
                self.set_state("STOP_RECORDING")
            else:
                current_second = int(recording_elapsed)
                if current_second != int(recording_elapsed - delta_seconds):
                    print(f"[WorkerEntry] Recording... {current_second + 1}s")
                
        elif self.state == "STOP_RECORDING":
            print("[WorkerEntry] Stopping recording...")
            try:
                take_recorder.stop_recording()
                seq = take_recorder.get_last_recorded_sequence(self.take_recorder_panel)
                if seq:
                    print(f"[WorkerEntry] ✓ Recorded: {seq.get_path_name()}")
                else:
                    print("[WorkerEntry] WARNING: Could not get recorded sequence")
            except Exception as e:
                print(f"[WorkerEntry] ERROR: Exception stopping recording: {e}")
            
            # Check if we need to wait after recording
            if self.post_recording_wait > 0:
                print(f"[WorkerEntry] Post-recording wait: {self.post_recording_wait}s before stopping PIE")
                self.set_state("POST_RECORDING_WAIT")
            else:
                # Check if we should stop PIE or keep playing
                if self.keep_playing_after_job:
                    print("[WorkerEntry] No post-recording wait. Keeping PIE running as requested.")
                    self.set_state("COMPLETE_KEEP_PLAYING")
                else:
                    print("[WorkerEntry] No post-recording wait. Stopping PIE as requested.")
                    self.set_state("STOP_PIE")
                    
        elif self.state == "POST_RECORDING_WAIT":
            # Wait some time after recording (scene continues running)
            if elapsed >= self.post_recording_wait:
                print(f"[WorkerEntry] ✓ Post-recording wait complete ({self.post_recording_wait}s)")
                # Now decide whether to stop PIE or keep playing
                if self.keep_playing_after_job:
                    print("[WorkerEntry] Job finished: keeping PIE running as requested.")
                    self.set_state("COMPLETE_KEEP_PLAYING")
                else:
                    print("[WorkerEntry] Job finished: stopping PIE as requested.")
                    self.set_state("STOP_PIE")
            else:
                current_second = int(elapsed)
                if current_second != int(elapsed - delta_seconds):
                    print(f"[WorkerEntry] Post-recording wait... {current_second + 1}/{int(self.post_recording_wait)}s")
            
        elif self.state == "STOP_PIE":
            print("[WorkerEntry] Stopping PIE...")
            try:
                if level_launcher.is_pie_playing():
                    self.level_editor.editor_request_end_play()
                self.set_state("WAIT_PIE_STOP")
            except Exception as e:
                print(f"[WorkerEntry] ERROR: Exception stopping PIE: {e}")
                self.set_state("COMPLETE")
                
        elif self.state == "WAIT_PIE_STOP":
            if not level_launcher.is_pie_playing():
                print("[WorkerEntry] ✓ PIE stopped")
                self.set_state("COMPLETE")
            elif elapsed > self.timeout:
                print("[WorkerEntry] WARNING: PIE stop timeout")
                self.set_state("COMPLETE")
                
        elif self.state == "COMPLETE":
            print("[WorkerEntry] ✓ Job completed successfully!")
            self.stop()
            print("[WorkerEntry] Exiting UE...")
            sys.exit(0)
        
        elif self.state == "COMPLETE_KEEP_PLAYING":
            # Job finished but we intentionally keep PIE running.
            print("[WorkerEntry] ✓ Job completed. PIE will be kept running.")
            self.stop()
            print("[WorkerEntry] Leaving UE Editor open for inspection.")
            # Do NOT call sys.exit(); leave editor running.
            # The external launcher (PowerShell) will detect UE process is alive.
            return
            
        elif self.state == "ERROR":
            print("[WorkerEntry] ERROR: Job failed")
            self.stop()
            # Try to stop PIE if running
            try:
                if level_launcher.is_pie_playing():
                    self.level_editor.editor_request_end_play()
            except:
                pass
            sys.exit(1)


# Start the worker
worker = JobWorker(map_path, job_id, manifest)
worker.start()
