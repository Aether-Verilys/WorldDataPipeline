#!/usr/bin/env python3
"""
Convert rendered frame sequences to H264 MP4 videos
Usage: python convert_frames_to_video.py --config examples/job_render_1218.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def print_error_and_exit(message: str):
    """Print error message and exit"""
    print()
    print(f"\033[91mERROR: {message}\033[0m")
    # In non-interactive mode we avoid waiting for input
    if not globals().get('NO_PAUSE', False):
        print("\033[93mPress Enter to exit...\033[0m")
        try:
            input()
        except Exception:
            pass
    sys.exit(1)


def print_header():
    """Print script header"""
    print("\033[96m" + "=" * 50 + "\033[0m")
    print("\033[96mFrame Sequence to Video Converter\033[0m")
    print("\033[96m" + "=" * 50 + "\033[0m")


def check_ffmpeg():
    """Check if ffmpeg is available"""
    if not shutil.which('ffmpeg'):
        print_error_and_exit("FFmpeg not found. Please install FFmpeg and add it to PATH.")
    
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True, 
                              check=True)
        version_line = result.stdout.split('\n')[0]
        print(f"\033[92mFFmpeg found: {version_line}\033[0m")
    except subprocess.CalledProcessError:
        print_error_and_exit("Failed to get FFmpeg version.")


def load_config(config_path: str) -> dict:
    """Load and parse configuration file"""
    config_file = Path(config_path)
    
    if not config_file.exists():
        print_error_and_exit(f"Config file not found: {config_path}")
    
    print(f"\033[93mLoading config: {config_path}\033[0m")
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except json.JSONDecodeError as e:
        print_error_and_exit(f"Failed to parse config file: {e}")
    except Exception as e:
        print_error_and_exit(f"Failed to read config file: {e}")


def extract_config_data(config: dict, framerate: int):
    """Extract required data from config"""
    try:
        rendering_cfg = config.get('rendering', {})
        ue_cfg = config.get('ue_config', {})

        base_output_path = rendering_cfg.get('output_path') or ue_cfg.get('output_base_dir')
        
        # Handle "default" value - use project directory's output folder
        if base_output_path == "default":
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            base_output_path = os.path.join(script_dir, "output")
        
        project_path = ue_cfg.get('project_path')
        
        # Handle "default" value - use ue_template project
        if project_path == "default":
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_path = os.path.join(script_dir, "ue_template", "project", "WorldData.uproject")
        
        map_path = config['map']
        sequence_path = config['sequence']
        
        # Get framerate from config if not specified
        if framerate == 0:
            if 'framerate' in config['rendering']:
                framerate = config['rendering']['framerate']
                print(f"\033[96mUsing framerate from config: {framerate} fps\033[0m")
            else:
                framerate = 30  # Default fallback
                print(f"\033[93mNo framerate in config, using default: {framerate} fps\033[0m")
        
        if not all([base_output_path, project_path, map_path, sequence_path]):
            print_error_and_exit("Config missing required fields (output_path (or ue_config.output_base_dir), project_path, map, or sequence)")
        
        return base_output_path, project_path, map_path, sequence_path, framerate
        
    except KeyError as e:
        print_error_and_exit(f"Failed to read config field: {e}")
    except Exception as e:
        print_error_and_exit(f"Failed to extract config data: {e}")


def build_output_path(base_output_path: str, project_path: str, map_path: str, sequence_path: str, ue_config: dict) -> tuple:
    """Build output directory path and extract names"""
    
    # Extract map name
    map_name = map_path.split('/')[-1]
    
    # Extract sequence name
    sequence_name = sequence_path.split('/')[-1]
    
    # Construct output directory path: base/map_name/sequence_name
    output_dir = Path(base_output_path) / map_name / sequence_name
    
    return output_dir, map_name, sequence_name


def find_frame_sequences(output_dir: Path, sequence_name: str) -> list:
    """Find frame sequence files"""
    if not output_dir.exists():
        print_error_and_exit(
            f"Output directory not found: {output_dir}\n"
            "Make sure rendering has completed successfully."
        )
    
    # Find frame sequences
    frame_pattern = f"{sequence_name}.*.png"
    try:
        frames = sorted(output_dir.glob(f"{sequence_name}.*.png"))
    except Exception as e:
        print_error_and_exit(f"Failed to search for frames: {e}")
    
    if len(frames) == 0:
        print_error_and_exit(
            f"No frame sequences found matching pattern: {frame_pattern}\n"
            f"Directory: {output_dir}"
        )
    
    return frames


def convert_to_video(output_dir: Path, sequence_name: str, framerate: int, 
                    video_codec: str, crf: str, frames: list) -> Path:
    """Convert frame sequences to video using FFmpeg"""
    output_video = output_dir / f"{sequence_name}.mp4"
    
    # Check if video already exists
    if output_video.exists():
        print(f"\033[93mWarning: Video already exists: {output_video}\033[0m")
        if globals().get('FORCE_YES', False):
            output_video.unlink()
        else:
            try:
                response = input("Overwrite? (y/n): ")
            except Exception:
                response = 'n'
            if response.lower() != 'y':
                print("\033[93mCancelled.\033[0m")
                sys.exit(0)
            output_video.unlink()
    
    # FFmpeg command to convert frames to video
    print()
    print("\033[93mConverting frames to video...\033[0m")
    print(f"\033[90m  Framerate: {framerate} fps\033[0m")
    print(f"\033[90m  Codec: {video_codec}\033[0m")
    print(f"\033[90m  CRF: {crf}\033[0m")
    print(f"\033[90m  Output: {output_video}\033[0m")
    
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
    
    print()
    print("\033[93mRunning FFmpeg...\033[0m")
    print(f"\033[90mCommand: {' '.join(ffmpeg_args)}\033[0m")
    
    try:
        # Run FFmpeg in the output directory
        result = subprocess.run(
            ffmpeg_args,
            cwd=output_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print()
            print("\033[93mFFmpeg output:\033[0m")
            print(f"\033[90m{result.stderr}\033[0m")
            print_error_and_exit(f"FFmpeg failed with exit code: {result.returncode}")
        
        print("\033[92mVideo created successfully!\033[0m")
        
        # Get video info
        video_size_mb = round(output_video.stat().st_size / (1024 * 1024), 2)
        print(f"\033[90m  Size: {video_size_mb} MB\033[0m")
        print(f"\033[90m  Path: {output_video}\033[0m")
        
        return output_video
        
    except Exception as e:
        print(f"\033[91mError during video conversion: {e}\033[0m")
        sys.exit(1)


def delete_frames(frames: list):
    """Delete frame sequence files"""
    print()
    print("\033[93mDeleting frame sequences...\033[0m")
    
    deleted_count = 0
    for frame in frames:
        try:
            frame.unlink()
            deleted_count += 1
        except Exception as e:
            print(f"\033[93mWarning: Failed to delete {frame.name}: {e}\033[0m")
    
    print(f"\033[92mDeleted {deleted_count} frames\033[0m")


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
    print_header()
    
    # Check FFmpeg
    check_ffmpeg()
    
    # Load configuration
    config = load_config(args.config)
    
    # Extract config data
    base_output_path, project_path, map_path, sequence_path, framerate = extract_config_data(
        config, args.framerate
    )
    
    # Get ue_config for scene lookup
    ue_config = config.get('ue_config', {})
    
    # Build output path
    output_dir, map_name, sequence_name = build_output_path(
        base_output_path, project_path, map_path, sequence_path, ue_config
    )
    
    print(f"\033[96mMap: {map_name}\033[0m")
    print(f"\033[96mSequence: {sequence_name}\033[0m")
    print(f"\033[96mOutput directory: {output_dir}\033[0m")
    
    # Find frame sequences
    frames = find_frame_sequences(output_dir, sequence_name)
    
    print(f"\033[92mFound {len(frames)} frames\033[0m")
    print(f"\033[90mFirst frame: {frames[0].name}\033[0m")
    print(f"\033[90mLast frame: {frames[-1].name}\033[0m")
    
    # Convert to video
    output_video = convert_to_video(
        output_dir, sequence_name, framerate, args.codec, args.crf, frames
    )
    
    # Delete frames if requested
    if not args.keep_frames:
        delete_frames(frames)
    else:
        print()
        print("\033[93mKeeping frame sequences (--keep-frames flag set)\033[0m")
    
    # Print summary
    print()
    print("\033[96m" + "=" * 50 + "\033[0m")
    print("\033[92mConversion complete!\033[0m")
    print(f"\033[96mVideo: {output_video}\033[0m")
    print("\033[96m" + "=" * 50 + "\033[0m")
    print()
    if not globals().get('NO_PAUSE', False):
        print("\033[93mPress Enter to exit...\033[0m")
        try:
            input()
        except Exception:
            pass


if __name__ == '__main__':
    main()
