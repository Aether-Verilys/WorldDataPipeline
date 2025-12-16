"""
Orchestrator Submit Tool
External Python script to submit jobs to the UE worker pipeline

This script runs OUTSIDE the UE Editor and writes job manifests to a watch directory.
The in-editor worker daemon picks up the manifests and processes them.

Usage:
    python orchestrator_submit.py --job-file=my_job.json --watch-dir=d:/jobs/inbox
    
Or programmatically:
    from orchestrator_submit import submit_job
    job_manifest = {...}
    submit_job(job_manifest, watch_dir="d:/jobs/inbox")
"""
import json
import os
import sys
import time
import argparse
from typing import Dict, Any, Optional
from pathlib import Path
import uuid


def submit_job(
    manifest: Dict[str, Any],
    watch_dir: str,
    job_id: Optional[str] = None
) -> str:
    """
    Submit a job manifest to the watch directory
    
    Args:
        manifest: job manifest dict
        watch_dir: directory where worker daemon watches for jobs
        job_id: optional job ID (generated if not provided)
    
    Returns:
        job_id of submitted job
    """
    # Ensure job_id is set
    if job_id is None:
        job_id = manifest.get("job_id")
    
    if job_id is None:
        job_id = f"job-{uuid.uuid4().hex[:12]}-{int(time.time())}"
        manifest["job_id"] = job_id
    
    # Ensure watch directory exists
    os.makedirs(watch_dir, exist_ok=True)
    
    # Write manifest atomically (write to .tmp then rename)
    manifest_filename = f"{job_id}.json"
    manifest_path = os.path.join(watch_dir, manifest_filename)
    temp_path = os.path.join(watch_dir, f"{manifest_filename}.tmp")
    
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    # Atomic rename
    os.replace(temp_path, manifest_path)
    
    print(f"✓ Job submitted: {job_id}")
    print(f"  Manifest: {manifest_path}")
    
    return job_id


def create_job_manifest(
    sequence_path: str,
    map_path: str,
    start_frame: int,
    end_frame: int,
    job_id: Optional[str] = None,
    render_enabled: bool = True,
    camera_export_enabled: bool = True,
    output_base_dir: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Create a job manifest with common parameters
    
    Args:
        sequence_path: UE sequence asset path (e.g., /Game/Sequences/MySeq)
        map_path: UE map asset path (e.g., /Game/Maps/MyMap)
        start_frame: start frame number
        end_frame: end frame number
        job_id: optional job identifier
        render_enabled: whether to render frames
        camera_export_enabled: whether to export camera data
        output_base_dir: base output directory for all outputs
        **kwargs: additional fields to add to manifest
    
    Returns:
        job manifest dict
    """
    if job_id is None:
        job_id = f"job-{uuid.uuid4().hex[:12]}-{int(time.time())}"
    
    manifest = {
        "job_id": job_id,
        "map": map_path,
        "sequence": sequence_path,
        "frame_range": {
            "start_frame": start_frame,
            "end_frame": end_frame,
            "step": 1
        }
    }
    
    if output_base_dir:
        manifest["base_output_dir"] = output_base_dir
    
    # Camera export config
    if camera_export_enabled:
        manifest["camera"] = {
            "export_enabled": True,
            "export_format": "csv"
        }
    
    # Render config
    if render_enabled:
        manifest["render"] = {
            "enabled": True,
            "output_format": "exr",
            "resolution": {"x": 1920, "y": 1080}
        }
    
    # Merge additional fields
    manifest.update(kwargs)
    
    return manifest


def submit_job_from_file(
    job_file: str,
    watch_dir: str
) -> str:
    """
    Load job manifest from file and submit
    
    Args:
        job_file: path to job manifest JSON file
        watch_dir: directory where worker daemon watches for jobs
    
    Returns:
        job_id of submitted job
    """
    with open(job_file, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    return submit_job(manifest, watch_dir)


def check_job_status(
    job_id: str,
    status_dir: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Check job status by reading status file
    
    Args:
        job_id: job identifier
        status_dir: directory containing status files (default: ../jobs/status)
    
    Returns:
        status dict or None if not found
    """
    if status_dir is None:
        # Default status directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        status_dir = os.path.join(os.path.dirname(current_dir), "jobs", "status")
    
    status_path = os.path.join(status_dir, f"{job_id}.status.json")
    
    if not os.path.exists(status_path):
        return None
    
    with open(status_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def wait_for_job_completion(
    job_id: str,
    status_dir: Optional[str] = None,
    timeout: float = 3600.0,
    poll_interval: float = 2.0
) -> Dict[str, Any]:
    """
    Wait for job to complete and return final status
    
    Args:
        job_id: job identifier
        status_dir: directory containing status files
        timeout: maximum wait time in seconds
        poll_interval: seconds between status checks
    
    Returns:
        final status dict
    
    Raises:
        TimeoutError: if job doesn't complete within timeout
    """
    start_time = time.time()
    
    print(f"Waiting for job {job_id} to complete...")
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
        
        status = check_job_status(job_id, status_dir)
        
        if status:
            job_status = status.get("status")
            print(f"  [{elapsed:.1f}s] Status: {job_status} - {status.get('message', '')}")
            
            if job_status in ["SUCCESS", "FAILED", "CANCELLED"]:
                return status
        
        time.sleep(poll_interval)


def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(
        description="Submit jobs to UE worker pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Submit from existing manifest file
  python orchestrator_submit.py --job-file=my_job.json --watch-dir=d:/jobs/inbox
  
  # Create and submit a new job
  python orchestrator_submit.py \\
    --sequence=/Game/Sequences/Shot01 \\
    --map=/Game/Maps/Forest \\
    --start-frame=0 \\
    --end-frame=120 \\
    --watch-dir=d:/jobs/inbox
  
  # Check job status
  python orchestrator_submit.py --check-status=job-abc123
"""
    )
    
    parser.add_argument("--job-file", help="Path to existing job manifest JSON file")
    parser.add_argument("--watch-dir", default=None, help="Watch directory for job submission")
    parser.add_argument("--sequence", help="UE sequence asset path")
    parser.add_argument("--map", help="UE map asset path")
    parser.add_argument("--start-frame", type=int, help="Start frame")
    parser.add_argument("--end-frame", type=int, help="End frame")
    parser.add_argument("--output-dir", help="Output base directory")
    parser.add_argument("--check-status", help="Check status of job ID")
    parser.add_argument("--wait", action="store_true", help="Wait for job completion")
    
    args = parser.parse_args()
    
    # Default watch directory
    if args.watch_dir is None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        args.watch_dir = os.path.join(os.path.dirname(current_dir), "jobs", "inbox")
    
    # Check status mode
    if args.check_status:
        status = check_job_status(args.check_status)
        if status:
            print(f"Job {args.check_status}:")
            print(f"  Status: {status.get('status')}")
            print(f"  Message: {status.get('message')}")
            print(f"  Time: {status.get('timestamp_readable')}")
            if "details" in status:
                print(f"  Details: {json.dumps(status['details'], indent=4)}")
        else:
            print(f"No status found for job: {args.check_status}")
        return 0
    
    # Submit from file
    if args.job_file:
        job_id = submit_job_from_file(args.job_file, args.watch_dir)
    
    # Create and submit new job
    elif args.sequence and args.map and args.start_frame is not None and args.end_frame is not None:
        manifest = create_job_manifest(
            sequence_path=args.sequence,
            map_path=args.map,
            start_frame=args.start_frame,
            end_frame=args.end_frame,
            output_base_dir=args.output_dir
        )
        job_id = submit_job(manifest, args.watch_dir)
    
    else:
        parser.print_help()
        return 1
    
    # Wait for completion if requested
    if args.wait:
        try:
            final_status = wait_for_job_completion(job_id)
            print(f"\nFinal status: {final_status.get('status')}")
            return 0 if final_status.get('status') == 'SUCCESS' else 1
        except TimeoutError as e:
            print(f"ERROR: {e}")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
