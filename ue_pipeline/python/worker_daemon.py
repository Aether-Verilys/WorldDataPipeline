"""
Worker Daemon
Long-running in-editor worker that polls a watch directory for job manifests

Usage:
    1. Start UE Editor with this script:
       UnrealEditor.exe Project.uproject -ExecutePythonScript="worker_daemon.py" -ScriptArgs="--watch-dir=path/to/jobs/inbox"
    
    2. Or execute inside running editor:
       import worker_daemon
       worker_daemon.run_worker("path/to/jobs/inbox")
"""
import sys
import os
import time
import traceback
from typing import Optional

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import job_utils
from job_utils import JobStatus

# Global daemon instance to prevent garbage collection
_daemon_instance = None


def handle_job(manifest_path: str) -> bool:
    """
    Handle a single job manifest
    
    Args:
        manifest_path: path to job manifest JSON file
    
    Returns:
        True if job succeeded, False if failed
    """
    manifest = None
    job_id = None
    processing_path = manifest_path
    
    try:
        import unreal
        
        # Move to processing directory
        processing_path = job_utils.mark_job_processing(manifest_path)
        unreal.log(f"[WorkerDaemon] Processing job: {processing_path}")
        
        # Read manifest
        manifest = job_utils.read_manifest(processing_path)
        job_id = manifest["job_id"]
        
        unreal.log(f"[WorkerDaemon] Job ID: {job_id}")
        
        # Write initial status
        job_utils.write_status(job_id, JobStatus.IN_PROGRESS, "Job started by daemon")
        
        # Ensure output directories
        output_paths = job_utils.ensure_output_dirs(manifest)
        unreal.log(f"[WorkerDaemon] Output paths: {output_paths}")
        
        # Execute job steps
        results = {}
        
        # Step 1: Load map
        if "map" in manifest and manifest["map"]:
            unreal.log(f"[WorkerDaemon] Loading map: {manifest['map']}")
            import level_launcher
            success = level_launcher.load_level_from_manifest(manifest)
            if not success:
                raise RuntimeError(f"Failed to load map: {manifest['map']}")
            results["map_loaded"] = manifest["map"]
        
        # Step 2: Render sequence
        if "render" in manifest:
            render_config = manifest["render"]
            if render_config.get("enabled", True):
                unreal.log("[WorkerDaemon] Starting render...")
                import rendering
                render_result = rendering.render_sequence_from_manifest(manifest)
                results["render"] = render_result
                unreal.log(f"[WorkerDaemon] Render completed: {render_result}")
        
        # Step 3: Export camera
        if "camera" in manifest:
            camera_config = manifest["camera"]
            if camera_config.get("export_enabled", True):
                unreal.log("[WorkerDaemon] Exporting camera data...")
                import export_UE_camera
                camera_result = export_UE_camera.export_camera_from_manifest(manifest)
                results["camera_export"] = camera_result
                unreal.log(f"[WorkerDaemon] Camera export completed: {camera_result}")
        
        # Step 4: Post-process
        if "post_process" in manifest:
            for step in manifest["post_process"]:
                unreal.log(f"[WorkerDaemon] Post-process step: {step}")
                # TODO: implement post-process handlers
        
        # Write success status
        job_utils.write_status(
            job_id,
            JobStatus.SUCCESS,
            "Job completed successfully",
            {"results": results}
        )
        
        # Move to completed
        job_utils.mark_job_completed(processing_path, success=True)
        unreal.log(f"[WorkerDaemon] ✓ Job {job_id} completed successfully")
        
        return True
    
    except Exception as e:
        error_msg = f"Job failed: {str(e)}"
        error_trace = traceback.format_exc()
        
        try:
            import unreal
            unreal.log_error(f"[WorkerDaemon] {error_msg}")
            unreal.log_error(error_trace)
        except ImportError:
            print(f"[WorkerDaemon] ERROR: {error_msg}", file=sys.stderr)
            print(error_trace, file=sys.stderr)
        
        # Write failure status
        if job_id:
            try:
                job_utils.write_status(
                    job_id,
                    JobStatus.FAILED,
                    error_msg,
                    {"error": str(e), "traceback": error_trace}
                )
            except Exception as status_error:
                print(f"[WorkerDaemon] Failed to write status: {status_error}", file=sys.stderr)
        
        # Move to failed
        try:
            job_utils.mark_job_completed(processing_path, success=False)
        except Exception:
            pass
        
        return False


class WorkerDaemon:
    """Worker daemon that polls for jobs"""
    
    def __init__(self, watch_dir: str, poll_interval: float = 1.0):
        self.watch_dir = watch_dir
        self.poll_interval = poll_interval
        self.is_running = False
        self.tick_handle = None
        self.last_check_time = 0.0
        
        # Ensure watch directory exists
        os.makedirs(watch_dir, exist_ok=True)
        
        try:
            import unreal
            unreal.log(f"[WorkerDaemon] Initialized with watch_dir: {watch_dir}")
            unreal.log(f"[WorkerDaemon] Poll interval: {poll_interval}s")
        except ImportError:
            print(f"[WorkerDaemon] Initialized with watch_dir: {watch_dir}")
            print(f"[WorkerDaemon] Poll interval: {poll_interval}s")
    
    def start(self):
        """Start the daemon"""
        if self.is_running:
            try:
                import unreal
                unreal.log_warning("[WorkerDaemon] Already running")
            except ImportError:
                print("[WorkerDaemon] Already running")
            return
        
        self.is_running = True
        
        try:
            import unreal
            unreal.log("[WorkerDaemon] Starting worker daemon...")
            
            # Register tick callback
            self.tick_handle = unreal.register_slate_post_tick_callback(self._on_tick)
            
            unreal.log("[WorkerDaemon] ✓ Worker daemon started")
            unreal.log(f"[WorkerDaemon] Watching directory: {self.watch_dir}")
        except ImportError:
            print("[WorkerDaemon] ERROR: Must run inside UE Editor")
            self.is_running = False
    
    def stop(self):
        """Stop the daemon"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        try:
            import unreal
            if self.tick_handle:
                unreal.unregister_slate_post_tick_callback(self.tick_handle)
                self.tick_handle = None
            unreal.log("[WorkerDaemon] Worker daemon stopped")
        except ImportError:
            print("[WorkerDaemon] Worker daemon stopped")
    
    def _on_tick(self, delta_time: float):
        """Tick callback - check for new jobs"""
        if not self.is_running:
            return
        
        current_time = time.time()
        
        # Only check at poll_interval
        if current_time - self.last_check_time < self.poll_interval:
            return
        
        self.last_check_time = current_time
        
        try:
            # Discover pending jobs
            pending_jobs = job_utils.discover_pending_jobs(self.watch_dir)
            
            if pending_jobs:
                import unreal
                unreal.log(f"[WorkerDaemon] Found {len(pending_jobs)} pending job(s)")
                
                # Process first job (FIFO)
                manifest_path = pending_jobs[0]
                unreal.log(f"[WorkerDaemon] Processing: {os.path.basename(manifest_path)}")
                
                success = handle_job(manifest_path)
                
                if success:
                    unreal.log(f"[WorkerDaemon] ✓ Job completed successfully")
                else:
                    unreal.log_error(f"[WorkerDaemon] ✗ Job failed")
        
        except Exception as e:
            try:
                import unreal
                unreal.log_error(f"[WorkerDaemon] Error in tick: {e}")
                unreal.log_error(traceback.format_exc())
            except ImportError:
                print(f"[WorkerDaemon] Error in tick: {e}", file=sys.stderr)


def run_worker(watch_dir: str, poll_interval: float = 1.0) -> None:
    """
    Start worker daemon (convenience function)
    
    Args:
        watch_dir: directory to watch for job manifests
        poll_interval: seconds between checks
    """
    global _daemon_instance
    
    # Stop existing daemon if any
    if _daemon_instance:
        _daemon_instance.stop()
    
    # Create and start new daemon
    _daemon_instance = WorkerDaemon(watch_dir, poll_interval)
    _daemon_instance.start()


def stop_worker() -> None:
    """Stop worker daemon"""
    global _daemon_instance
    if _daemon_instance:
        _daemon_instance.stop()
        _daemon_instance = None


def main():
    """Main entry point for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="UE Worker Daemon")
    parser.add_argument("--watch-dir", required=True, help="Directory to watch for job manifests")
    parser.add_argument("--poll", type=float, default=1.0, help="Poll interval in seconds")
    
    # Parse args
    args = None
    try:
        args = parser.parse_args()
    except SystemExit:
        # Try parsing from UE's format if standard parsing fails
        if len(sys.argv) > 1:
            watch_dir = None
            poll_interval = 1.0
            
            for arg in sys.argv[1:]:
                if arg.startswith("--watch-dir="):
                    watch_dir = arg.split("=", 1)[1]
                elif arg.startswith("--poll="):
                    try:
                        poll_interval = float(arg.split("=", 1)[1])
                    except ValueError:
                        pass
            
            if watch_dir:
                class Args:
                    pass
                args = Args()
                args.watch_dir = watch_dir
                args.poll = poll_interval
    
    if not args or not hasattr(args, 'watch_dir'):
        print("ERROR: --watch-dir argument is required", file=sys.stderr)
        return 1
    
    run_worker(args.watch_dir, args.poll)
    
    try:
        import unreal
        unreal.log("[WorkerDaemon] Daemon is running. Use stop_worker() to stop.")
    except ImportError:
        print("[WorkerDaemon] Daemon is running. Use stop_worker() to stop.")
    
    return 0


if __name__ == "__main__":
    main()
