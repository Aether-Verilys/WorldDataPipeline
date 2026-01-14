import unreal
import sys
import json
import os

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from worker_common import load_json as _load_json, resolve_manifest_path_from_env as _resolve_manifest_path_from_env
from logger import logger


def scan_sequence_assets(sequence_dir: str) -> list:
    """Scan for level sequence assets in a directory."""
    logger.info(f"Scanning sequences in: {sequence_dir}")
    
    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
    
    # Scan the directory
    filter = unreal.ARFilter(
        package_paths=[sequence_dir],
        class_names=["LevelSequence"],
        recursive_files=True
    )
    
    assets = asset_registry.get_assets(filter)
    sequences = []
    
    for asset_data in assets:
        asset_path = asset_data.get_asset().get_path_name()
        sequences.append(asset_path)
        logger.info(f"  Found: {asset_path}")
        # Print to stdout for parent process to capture
        print(f"SEQUENCE:{asset_path}")
    
    return sorted(sequences)


def main(argv=None) -> int:
    logger.info("Starting sequence scan...")
    
    argv = list(argv) if argv is not None else sys.argv
    env_key = "UE_SCAN_MANIFEST"
    manifest_path = _resolve_manifest_path_from_env(env_key, argv)
    
    if not manifest_path:
        logger.error("No manifest path provided")
        return 1
    
    try:
        manifest = _load_json(manifest_path)
    except Exception as e:
        logger.error(f"Failed to read manifest: {e}")
        return 1
    
    sequence_dir = manifest.get("sequence_dir")
    if not sequence_dir:
        logger.error("No sequence_dir specified in manifest")
        return 1
    
    try:
        sequences = scan_sequence_assets(sequence_dir)
        logger.info(f"Found {len(sequences)} sequence(s)")
        return 0
    except Exception as e:
        logger.error(f"Failed to scan sequences: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
