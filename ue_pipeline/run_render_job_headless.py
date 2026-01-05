#!/usr/bin/env python3
"""
UE Render Job Executor (Headless Mode)
Execute a render job using command-line MRQ execution
"""
import argparse
import json
import os
import subprocess
import sys
import time
import psutil
from pathlib import Path


script_dir = Path(__file__).parent
repo_root = script_dir.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ue_pipeline.python.logger import logger


def load_manifest(manifest_path: str) -> dict:
    if not os.path.exists(manifest_path):
        logger.error(f"Manifest file not found: {manifest_path}")
        sys.exit(1)
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        return manifest
    except Exception as e:
        logger.error(f"Cannot parse manifest: {e}")
        sys.exit(1)


def validate_manifest(manifest: dict) -> tuple[str, str]:
    job_id = manifest.get('job_id', 'unknown')
    job_type = manifest.get('job_type', 'unknown')
    
    if job_type != 'render':
        logger.error(f"Invalid job type '{job_type}', expected 'render'")
        sys.exit(1)
    
    return job_id, job_type


def load_default_ue_config() -> dict:
    script_dir = Path(__file__).parent
    env_config_path = os.environ.get('UE_CONFIG_PATH')
    config_path = Path(env_config_path) if env_config_path else (script_dir / 'config' / 'ue_config.json')
    
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Cannot load default ue_config: {e}")
        sys.exit(1)


def get_ue_config(manifest: dict) -> tuple[str, str, str]:
    # Load default config first
    default_config = load_default_ue_config()
    
    # Merge with manifest config (manifest overrides default)
    manifest_config = manifest.get('ue_config', {})
    ue_config = {**default_config, **manifest_config}
    
    if not ue_config:
        logger.error("No ue_config found in manifest or default config file")
        sys.exit(1)
    
    editor_path = ue_config.get('editor_path')
    if not editor_path:
        logger.error("Missing 'editor_path' in ue_config")
        sys.exit(1)
    
    # Replace UnrealEditor.exe with UnrealEditor-Cmd.exe
    ue_editor = editor_path.replace('UnrealEditor.exe', 'UnrealEditor-Cmd.exe')
    
    project = ue_config.get('project_path')
    if not project:
        logger.error("Missing 'project_path' in ue_config")
        sys.exit(1)
    
    output_base_dir = ue_config.get('output_base_dir', '')
    if not output_base_dir:
        logger.error("Missing 'output_base_dir' in ue_config")
        sys.exit(1)
    
    return ue_editor, project, output_base_dir


def get_render_config(manifest: dict, ue_config: dict) -> dict:
    sequence = manifest.get('sequence', '')
    rendering = manifest.get('rendering', {})
    
    config_preset = rendering.get('preset', '')
    
    # Extract map name from sequence path
    # Format: /Game/CameraController/Generated/Lvl_FirstPerson_001
    # Sequence name: Lvl_FirstPerson_001
    # Map name: Lvl_FirstPerson
    map_path = None
    
    if sequence:
        # Get the last part of the sequence path (sequence name)
        parts = sequence.split('/')
        sequence_name = parts[-1] if parts else ''
        
        if sequence_name:
            # Extract map name by removing trailing _### pattern
            # e.g., Lvl_FirstPerson_001 -> Lvl_FirstPerson
            import re
            map_name = re.sub(r'_\d+$', '', sequence_name)
            
            # Lookup map path from ue_config scenes
            scenes = ue_config.get('scenes', {})
            for scene_name, scene_data in scenes.items():
                maps = scene_data.get('maps', [])
                for map_info in maps:
                    if map_info.get('name') == map_name:
                        map_path = map_info.get('path')
                        logger.info(f"Extracted map name '{map_name}' from sequence '{sequence_name}'")
                        logger.info(f"Found map path in config: {map_path}")
                        break
                if map_path:
                    break
            
            if not map_path:
                logger.error(f"Cannot find map '{map_name}' in ue_config scenes")
                sys.exit(1)
        else:
            logger.error(f"Cannot extract sequence name from path: {sequence}")
            sys.exit(1)
    
    return {
        'sequence': sequence,
        'map': map_path,
        'preset': config_preset
    }


def validate_paths(ue_editor: str, project: str, worker: str):
    if not os.path.exists(ue_editor):
        logger.error(f"UE Editor not found at: {ue_editor}")
        sys.exit(1)
    
    if not os.path.exists(project):
        logger.error(f"Project not found at: {project}")
        sys.exit(1)
    
    if not os.path.exists(worker):
        logger.error(f"Worker script not found at: {worker}")
        sys.exit(1)


def ensure_output_directory(output_path: str):
    if output_path:
        abs_output_path = os.path.abspath(output_path)
        if not os.path.exists(abs_output_path):
            os.makedirs(abs_output_path, exist_ok=True)
            logger.info(f"Created output directory: {abs_output_path}")


def wait_for_ue_render_processes(timeout_minutes: int = 120) -> bool:
    logger.info("Monitoring UE render processes...")
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    check_interval = 3  # Check every 3 seconds
    
    # Give UE time to spawn the render process
    initial_wait = 10
    logger.info(f"Waiting {initial_wait}s for render process to spawn...")
    time.sleep(initial_wait)
    
    # Track UnrealEditor processes
    ue_process_names = ['UnrealEditor-Cmd.exe', 'UnrealEditor.exe', 'UnrealEditor-Win64-Shipping.exe']
    
    last_count = 0
    stable_count = 0
    max_stable_checks = 10  # If process count stays 0 for this many checks, assume done
    
    while True:
        elapsed = time.time() - start_time
        
        # Check timeout
        if elapsed > timeout_seconds:
            logger.error(f"Timeout after {timeout_minutes} minutes waiting for render processes")
            return False
        
        # Count UE processes
        ue_processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    proc_name = proc.info['name']
                    if proc_name in ue_process_names:
                        # Filter out non-render processes by checking command line
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline:
                            cmdline_str = ' '.join(cmdline)
                            # Only count processes that seem to be render-related
                            # (either have our project path or are the spawned render worker)
                            if 'WorldData00' in cmdline_str or '-Unattended' in cmdline_str:
                                ue_processes.append({
                                    'pid': proc.info['pid'],
                                    'name': proc_name
                                })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            logger.warning(f"Error checking processes: {e}")
        
        current_count = len(ue_processes)
        
        # Print status
        if current_count != last_count:
            if current_count > 0:
                logger.info(f"Active UE render processes: {current_count} ({int(elapsed)}s elapsed)")
                for p in ue_processes:
                    logger.info(f"  - PID {p['pid']}: {p['name']}")
                stable_count = 0
            else:
                logger.info(f"No active UE render processes ({int(elapsed)}s elapsed)")
                stable_count += 1
            last_count = current_count
        elif current_count == 0:
            stable_count += 1
        else:
            stable_count = 0
        
        # If no processes for several checks, assume complete
        if current_count == 0 and stable_count >= max_stable_checks:
            logger.info("All UE render processes completed")
            return True
        
        time.sleep(check_interval)


def wait_for_render_completion_legacy(output_base_dir: str, manifest: dict, timeout_minutes: int = 120) -> bool:
    if not output_base_dir:
        logger.error("No output directory specified, cannot monitor render status")
        return False
    
    # Construct status file path based on manifest
    try:
        # Extract scene ID and map name from map_path
        map_path = manifest.get('map', '')
        sequence_path = manifest.get('sequence', '')
        
        scene_id = "UnknownScene"
        map_name = "UnknownMap"
        
        if map_path:
            map_name = map_path.split("/")[-1]
            
            # Extract scene ID from map path
            import re
            path_parts = map_path.split("/")
            for part in path_parts:
                if re.match(r'^S\d{4}$', part):
                    scene_id = part
                    break
        
        sequence_name = sequence_path.split("/")[-1] if sequence_path else "UnknownSequence"
        
        # Construct output directory path
        render_output_dir = os.path.join(output_base_dir, scene_id, map_name, sequence_name)
        status_file = os.path.join(render_output_dir, ".render_status.json")
        
        logger.info(f"Monitoring status file: {status_file}")
        logger.info(f"Render output directory: {render_output_dir}")
        
    except Exception as e:
        logger.error(f"Failed to construct status file path: {e}")
        return False
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    check_interval = 5  # Check every 5 seconds
    
    last_status = None
    wait_count = 0
    last_frame_count = 0
    no_progress_count = 0
    max_no_progress = 60  # 5 minutes without new frames (60 * 5 seconds)
    
    while True:
        elapsed = time.time() - start_time
        
        # Check timeout
        if elapsed > timeout_seconds:
            logger.error(f"Timeout after {timeout_minutes} minutes waiting for render to complete")
            return False
        
        # Check if status file exists
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                
                current_status = status_data.get('status', 'unknown')
                
                # Print status update if changed
                if current_status != last_status:
                    logger.info(f"Render status: {current_status}")
                    last_status = current_status
                
                # Check if completed
                if current_status == 'completed':
                    success = status_data.get('success', False)
                    if success:
                        logger.info("Render completed successfully")
                        return True
                    else:
                        logger.error("Render completed but marked as failed")
                        return False
                
                elif current_status == 'failed':
                    logger.error("Render failed")
                    return False
                
                # Still rendering, continue waiting
                
            except json.JSONDecodeError as e:
                logger.warning(f"Status file exists but cannot parse JSON: {e}")
            except Exception as e:
                logger.warning(f"Error reading status file: {e}")
        else:
            # Fallback: Monitor output directory for rendered frames
            if os.path.exists(render_output_dir):
                try:
                    # Count rendered frames (common extensions: .png, .exr, .jpg)
                    frame_files = []
                    for ext in ['.png', '.exr', '.jpg', '.jpeg']:
                        frame_files.extend([f for f in os.listdir(render_output_dir) if f.lower().endswith(ext)])
                    
                    current_frame_count = len(frame_files)
                    
                    if current_frame_count > last_frame_count:
                        logger.info(f"Progress: {current_frame_count} frames rendered ({int(elapsed)}s elapsed)")
                        last_frame_count = current_frame_count
                        no_progress_count = 0
                    else:
                        no_progress_count += 1
                        
                        # If we have frames but no progress for a while, assume complete
                        if current_frame_count > 0 and no_progress_count >= max_no_progress:
                            logger.info(f"No new frames for {max_no_progress * check_interval}s, assuming render complete")
                            logger.info(f"Total frames rendered: {current_frame_count}")
                            return True
                    
                except Exception as e:
                    logger.warning(f"Error checking frame files: {e}")
            else:
                # Output directory doesn't exist yet
                if wait_count % 12 == 0:  # Print every minute
                    logger.info(f"Waiting for render to start... ({int(elapsed)}s elapsed)")
        
        wait_count += 1
        time.sleep(check_interval)


def run_ue_job(ue_editor: str, project: str, manifest_path: str, worker: str, job_id: str, full_config: dict) -> int:
    abs_manifest_path = os.path.abspath(manifest_path)
    abs_worker = os.path.abspath(worker)
    
    # Load original manifest
    with open(abs_manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    # Inject full ue_config into manifest for worker to use
    manifest['ue_config'] = full_config
    # Ensure rendering.output_path is set so MRQ uses the expected output directory
    try:
        rendering_section = manifest.setdefault('rendering', {})
        # If manifest doesn't provide an output_path, prefer ue_config.output_base_dir
        if not rendering_section.get('output_path'):
            output_base = full_config.get('output_base_dir') if isinstance(full_config, dict) else None
            if output_base:
                rendering_section['output_path'] = output_base
                manifest['rendering'] = rendering_section
                logger.info(f"Injected rendering.output_path='{output_base}' into manifest")
        
        # Store the output directory for status file monitoring
        output_directory = rendering_section.get('output_path', '')
    except Exception:
        output_directory = ''
        pass
    
    # Create a temporary manifest with ue_config injected
    import tempfile
    temp_manifest_fd, temp_manifest_path = tempfile.mkstemp(suffix='.json', prefix='render_manifest_')
    try:
        with os.fdopen(temp_manifest_fd, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        
        # Set manifest path as environment variable for Python script to read
        os.environ['UE_RENDER_MANIFEST'] = temp_manifest_path
        
        # Build UE command-line arguments
        ue_args = [
            ue_editor,
            project,
            f'-ExecutePythonScript={abs_worker}',
            '-RenderOffscreen',
            '-ResX=1920',
            '-ResY=1080',
            '-ForceRes',
            '-Windowed',
            '-NoLoadingScreen',
            '-NoScreenMessages',
            '-NoSplash',
            '-Unattended',
            '-NoSound',
            '-AllowStdOutLogVerbosity',
            '-log',
            '-FullStdOutLogOutput',
            f'LOG=RenderLog_{job_id}.txt',
        ]
        
        logger.info(f"Command: {' '.join(ue_args)}")
        logger.blank(1)
        logger.separator(width=40, char='-')
        
        try:
            result = subprocess.run(ue_args, check=False)

            logger.blank(1)
            logger.separator(width=40, char='-')
            
            if result.returncode == 0:
                logger.info("UE主进程已退出，开始等待渲染进程...")
                
                # Wait for UE render processes to complete
                logger.blank(1)
                logger.separator(width=40, char='-')
                logger.info("等待UE渲染进程完成...")
                logger.separator(width=40, char='-')
                
                wait_success = wait_for_ue_render_processes(timeout_minutes=120)
                
                if not wait_success:
                    logger.error("渲染进程未在超时时间内完成")
                    # Fallback to legacy status file monitoring
                    logger.info("尝试备用方案：监控状态文件...")
                    wait_success = wait_for_render_completion_legacy(output_directory, manifest, timeout_minutes=120)
                    
                    if not wait_success:
                        logger.error("渲染进程检测失败")
                        return 1
                
                logger.blank(1)
                logger.separator(width=40, char='-')
                logger.info("渲染进程已完成，开始后处理...")
                logger.separator(width=40, char='-')
                
                # Run postprocess actions (ffmpeg conversion, delete, upload)
                try:
                    post_rc = run_postprocess_actions(temp_manifest_path)
                    if post_rc != 0:
                        logger.error(f"Postprocess actions failed with code: {post_rc}")
                        return post_rc
                except Exception as e:
                    logger.error(f"Postprocess exception: {e}")
                    return 1

                return 0
            else:
                logger.error(f"Render job failed with exit code: {result.returncode}")
                return result.returncode
                
        except Exception as e:
            logger.error(f"Failed to launch UE: {e}")
            return 1
    finally:
        # Clean up temporary manifest file
        try:
            if os.path.exists(temp_manifest_path):
                os.remove(temp_manifest_path)
        except:
            pass


def run_postprocess_actions(manifest_path: str):
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            m = json.load(f)
    except Exception as e:
        logger.error(f"Postprocess: failed to read manifest: {e}")
        return 1

    rendering_conf = m.get('rendering', {})
    post = rendering_conf.get('postprocess', {})
    combine = post.get('combine_to_video', False)
    delete_frames = post.get('delete_frames_after_encode', False)
    upload_conf = post.get('upload_bos', {})

    script_dir = Path(__file__).parent
    converter = script_dir / 'convert_frames_to_video.py'

    if combine:
        cmd = [sys.executable, str(converter), '--config', manifest_path, '--no-pause']
        if not delete_frames:
            cmd.append('--keep-frames')
        # run converter
        logger.kv('Post:', f"Running converter: {' '.join(cmd)}")
        try:
            res = subprocess.run(cmd, check=False)
            if res.returncode != 0:
                logger.error(f"Frame-to-video conversion failed, code {res.returncode}")
                return res.returncode
        except Exception as e:
            logger.error(f"Failed to run converter: {e}")
            return 1

    # If upload requested, attempt to upload the generated mp4
    if upload_conf and upload_conf.get('enabled'):
        try:
            # determine video path
            base_output = rendering_conf.get('output_path')
            if not base_output:
                logger.error('Post: no output_path in manifest.rendering; cannot find video to upload')
                return 1

            scene_id = 'UnknownScene'
            map_path = m.get('map', '')
            sequence = m.get('sequence', '').split('/')[-1]
            # try to extract scene id from map_path
            for part in map_path.split('/'):
                import re
                if re.match(r'^S\d{4}$', part):
                    scene_id = part
                    break

            map_name = map_path.split('/')[-1]
            video_path = os.path.abspath(os.path.join(base_output, scene_id, map_name, sequence, f"{sequence}.mp4"))
            logger.kv('Post:', f"Uploading video: {video_path}")

            # upload using Baidu BCE SDK (bce-python-sdk)
            try:
                from baidubce.services.bos.bos_client import BosClient
                from baidubce.bce_client_configuration import BceClientConfiguration
                from baidubce.auth.bce_credentials import BceCredentials
            except Exception:
                logger.error('bce-python-sdk not installed; cannot upload to BOS. Install with `pip install bce-python-sdk`.')
                return 1

            # Prefer reading credentials from environment variables to avoid storing secrets in manifests
            endpoint = upload_conf.get('endpoint') or os.environ.get('BOS_ENDPOINT')
            access_key = os.environ.get('BOS_ACCESS_KEY') or upload_conf.get('access_key')
            secret_key = os.environ.get('BOS_SECRET_KEY') or upload_conf.get('secret_key')
            bucket = upload_conf.get('bucket') or os.environ.get('BOS_BUCKET')
            dest_path = upload_conf.get('dest_path') or os.environ.get('BOS_DEST_PATH', '')

            if not all([endpoint, access_key, secret_key, bucket]):
                logger.error('upload_bos missing required fields: endpoint/access_key/secret_key/bucket (can be set via environment variables BOS_ENDPOINT/BOS_ACCESS_KEY/BOS_SECRET_KEY/BOS_BUCKET)')
                return 1

            try:
                config = BceClientConfiguration(credentials=BceCredentials(access_key, secret_key), endpoint=endpoint)
                client = BosClient(config)

                # build object key
                if dest_path:
                    key = '/'.join([p.strip('/') for p in [dest_path, os.path.basename(video_path)]])
                else:
                    key = os.path.basename(video_path)

                logger.kv('Post:', f"Uploading to bucket={bucket} key={key}")
                client.put_object_from_file(bucket, key, video_path)
                logger.kv('Post:', 'Upload completed')
            except Exception as e:
                logger.error(f"BOS upload failed: {e}")
                return 1
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return 1

    return 0


# ============================================================
# Main Function
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='UE Render Job Executor (Headless Mode)'
    )
    parser.add_argument(
        'manifest_path',
        help='Path to the job manifest JSON file'
    )
    
    args = parser.parse_args()
    
    # Get worker script path (relative to this script)
    script_dir = Path(__file__).parent
    worker = str(script_dir / 'python' / 'worker_render.py')
    
    # Print header
    logger.header("UE Render Job Executor (Headless Mode)")
    
    # Load and validate manifest
    manifest = load_manifest(args.manifest_path)
    job_id, job_type = validate_manifest(manifest)
    
    # Get UE configuration
    ue_editor, project, output_base_dir = get_ue_config(manifest)
    
    # Load full config for scene lookup
    full_config = load_default_ue_config()
    
    # Get render configuration (with map lookup)
    render_config = get_render_config(manifest, full_config)
    
    # Print job info
    logger.kv("Job ID:", job_id)
    logger.kv("Sequence:", render_config['sequence'])
    logger.kv("Map:", render_config['map'])
    logger.kv("Config:", render_config['preset'])
    logger.kv("Output:", output_base_dir)
    logger.kv("UE Editor:", ue_editor)
    logger.kv("Project:", project)
    logger.blank(1)
    
    # Validate paths
    validate_paths(ue_editor, project, worker)
    
    # Ensure output directory exists
    ensure_output_directory(output_base_dir)
    
    # Run the job
    logger.info("Starting headless render job...")
    logger.blank(1)
    
    exit_code = run_ue_job(ue_editor, project, args.manifest_path, worker, job_id, full_config)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
