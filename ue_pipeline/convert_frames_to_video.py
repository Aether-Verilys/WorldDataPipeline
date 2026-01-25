#!/usr/bin/env python3
"""
Wrapper script for video converter
Calls the actual video_converter module from python/rendering/
"""

import sys
from pathlib import Path

# Add repo root to path
script_dir = Path(__file__).parent
repo_root = script_dir.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Import and run the actual converter
from ue_pipeline.python.rendering import video_converter

if __name__ == "__main__":
    video_converter.main()
