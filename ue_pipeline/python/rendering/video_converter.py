"""
Convert rendered frame sequences to H264 MP4 videos
Usage: python convert_frames_to_video.py --config examples/job_render_1218.json
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from ue_pipeline.python.core import tools, logger


def check_ffmpeg():
    """Check if ffmpeg is available"""
    if not shutil.which('ffmpeg'):
        logger.error("FFmpeg not found. Please install FFmpeg and add it to PATH.")
        sys.exit(1)
    
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True, 
                              check=True)
        version_line = result.stdout.split('\n')[0]
        logger.info(f"FFmpeg found: {version_line}")
    except subprocess.CalledProcessError:
        logger.error("Failed to get FFmpeg version.")
        sys.exit(1)




def find_frame_sequences(output_dir: Path, sequence_name: str) -> list:
    """Find frame sequence files"""
    if not output_dir.exists():
        logger.error(f"Output directory not found: {output_dir}")
        logger.error("Make sure rendering has completed successfully.")
        sys.exit(1)
    
    # Find frame sequences
    frame_pattern = f"{sequence_name}.*.png"
    try:
        frames = sorted(output_dir.glob(f"{sequence_name}.*.png"))
    except Exception as e:
        logger.error(f"Failed to search for frames: {e}")
        sys.exit(1)
    
    if len(frames) == 0:
        logger.error(f"No frame sequences found matching pattern: {frame_pattern}")
        logger.error(f"Directory: {output_dir}")
        sys.exit(1)
    
    return frames


def convert_to_video(output_dir: Path, sequence_name: str, framerate: int, 
                    video_codec: str, crf: str, frames: list) -> Path:
    """Convert frame sequences to video using FFmpeg"""
    output_video = output_dir / f"{sequence_name}.mp4"
    
    # Check if video already exists
    if output_video.exists():
        logger.warning(f"Video already exists: {output_video}")
        if globals().get('FORCE_YES', False):
            output_video.unlink()
        else:
            try:
                response = input("Overwrite? (y/n): ")
            except Exception:
                response = 'n'
            if response.lower() != 'y':
                logger.info("Cancelled.")
                sys.exit(0)
            output_video.unlink()
    
    # FFmpeg command to convert frames to video
    logger.info("Converting frames to video...")
    logger.info(f"  Framerate: {framerate} fps")
    logger.info(f"  Codec: {video_codec}")
    logger.info(f"  CRF: {crf}")
    logger.info(f"  Output: {output_video}")
    
    # Construct FFmpeg input pattern
    input_pattern = f"{sequence_name}.%04d.png"
    
    ffmpeg_args = [
        'ffmpeg',
        '-framerate', str(framerate),
        '-start_number', '1',
        '-i', input_pattern,
        '-c:v', video_codec,
        '-crf', crf,
        '-pix_fmt', 'yuv420p',
        '-y',
        f"{sequence_name}.mp4"
    ]
    
    logger.info("Running FFmpeg...")
    logger.info(f"Command: {' '.join(ffmpeg_args)}")
    
    try:
        # Run FFmpeg in the output directory
        result = subprocess.run(
            ffmpeg_args,
            cwd=output_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error("FFmpeg output:")
            logger.error(result.stderr)
            raise RuntimeError(f"FFmpeg failed with exit code: {result.returncode}")
        
        logger.info("Video created successfully!")
        
        # Get video info
        video_size_mb = round(output_video.stat().st_size / (1024 * 1024), 2)
        logger.info(f"  Size: {video_size_mb} MB")
        logger.info(f"  Path: {output_video}")
        
        return output_video
        
    except RuntimeError:
        # Re-raise RuntimeError from FFmpeg failure
        raise
    except Exception as e:
        raise RuntimeError(f"Error during video conversion: {e}")



def delete_frames(frames: list):
    """Delete frame sequence files
    
    Returns:
        True if all frames deleted successfully, False otherwise
    """
    logger.info("Deleting frame sequences...")
    
    deleted_count = 0
    failed_count = 0
    for frame in frames:
        try:
            frame.unlink()
            deleted_count += 1
        except Exception as e:
            logger.warning(f"Failed to delete {frame.name}: {e}")
            failed_count += 1
    
    if failed_count > 0:
        logger.warning(f"Deleted {deleted_count} frames, failed to delete {failed_count} frames")
        return False
    else:
        logger.info(f"Deleted {deleted_count} frames")
        return True


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Convert rendered frame sequences to H264 MP4 videos'
    )
    parser.add_argument(
        '--config',
        required=True,
        help='Path to the job configuration JSON file'
    )
    parser.add_argument(
        '--framerate',
        type=int,
        default=0,
        help='Video framerate (0 means read from config, default: 0)'
    )
    parser.add_argument(
        '--codec',
        default='libx264',
        help='Video codec (default: libx264)'
    )
    parser.add_argument(
        '--crf',
        default='23',
        help='Constant Rate Factor for video quality (default: 23)'
    )
    parser.add_argument(
        '--keep-frames',
        action='store_true',
        help='Keep frame sequences after conversion'
    )
    parser.add_argument(
        '--no-pause',
        action='store_true',
        help='Do not wait for user input at the end (non-interactive)'
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Automatic yes to prompts (overwrite existing video)'
    )
    
    args = parser.parse_args()
    # Set global flags for non-interactive behavior
    globals()['NO_PAUSE'] = args.no_pause
    globals()['FORCE_YES'] = args.yes
    
    # Print header
    logger.info("=" * 50)
    logger.info("Frame Sequence to Video Converter")
    logger.info("=" * 50)
    
    # Check FFmpeg
    check_ffmpeg()
    
    # Load configuration using shared function (applies auto_append_date_to_output_dirs)
    try:
        # Add repo root to sys.path
        script_dir = Path(__file__).parent.parent.parent
        repo_root = script_dir.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        
        from ue_pipeline.python.core import job_utils
        logger.info(f"Loading config: {args.config}")
        config = job_utils.load_manifest(args.config)
        
    except Exception as e:
        logger.error(f"Failed to load manifest: {e}")
        sys.exit(1)
    
    # Extract config data using shared tools
    try:
        base_output_path, project_path, map_path, sequence_path, framerate = tools.parse_rendering_config(config, args.framerate)
    except Exception as e:
        logger.error(f"Invalid manifest rendering config: {e}")
        sys.exit(1)
    
    # Get ue_config for scene lookup
    ue_config = config.get('ue_config', {})

    # Build output path using shared builder
    try:
        output_dir = tools.get_output_dir_from_manifest(config, sequence_path)
    except Exception as e:
        logger.error(f"Failed to build output directory: {e}")
        sys.exit(1)

    map_name = map_path.split('/')[-1]
    sequence_name = sequence_path.split('/')[-1]
    logger.info(f"Map: {map_name}")
    logger.info(f"Sequence: {sequence_name}")
    logger.info(f"Output directory: {output_dir}")
    
    # Find frame sequences
    frames = find_frame_sequences(output_dir, sequence_name)
    
    logger.info(f"Found {len(frames)} frames")
    logger.info(f"First frame: {frames[0].name}")
    logger.info(f"Last frame: {frames[-1].name}")
    
    # Convert to video
    try:
        output_video = convert_to_video(
            output_dir, sequence_name, framerate, args.codec, args.crf, frames
        )
    except Exception as e:
        logger.error(f"Video conversion failed: {e}")
        logger.warning("Keeping frame sequences due to conversion failure")
        sys.exit(1)
    
    # Delete frames if requested
    if not args.keep_frames:
        delete_success = delete_frames(frames)
        if not delete_success:
            logger.warning("Some frames could not be deleted")
    else:
        logger.info("Keeping frame sequences (--keep-frames flag set)")
    
    # Print summary
    logger.info("Conversion complete!")
    logger.info(f"Video: {output_video}")
    if not globals().get('NO_PAUSE', False):
        logger.info("Task finished.")



if __name__ == '__main__':
    main()
