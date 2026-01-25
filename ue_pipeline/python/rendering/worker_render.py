
import unreal
import sys
import json

# 修正模块加载路径，确保 rendering.py 可用
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add workspace root to path for ue_pipeline imports
workspace_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from ue_pipeline.python.core import logger, job_utils


def main(argv=None) -> int:
    from ue_pipeline.python.rendering import render_engine

    logger.info("Starting render job execution...")

    argv = list(argv) if argv is not None else sys.argv
    env_key = "UE_RENDER_MANIFEST"
    manifest_path = job_utils.resolve_manifest_path_from_env(env_key, argv)

    if not manifest_path:
        logger.error("No manifest path provided")
        logger.info(f"sys.argv: {sys.argv}")
        logger.info(f"Environment vars: {env_key}={os.environ.get(env_key)}")
        return 1

    logger.info(f"Manifest: {manifest_path}")

    try:
        manifest = job_utils.load_manifest(manifest_path)
    except Exception as e:
        logger.error(f"Failed to read manifest: {e}")
        return 1

    job_id = manifest.get("job_id", "unknown")
    job_type = manifest.get("job_type", "unknown")
    sequence_path = manifest.get("sequence")

    logger.info(f"Job ID: {job_id}")
    logger.info(f"Job Type: {job_type}")
    logger.info(f"Sequence: {sequence_path}")

    if job_type != "render":
        logger.error(f"Invalid job type '{job_type}', expected 'render'")
        return 1

    if not sequence_path:
        logger.error("No sequence specified in manifest")
        return 1

    try:
        logger.info("Starting render job...")
        result = render_engine.render_sequence_from_manifest(manifest)

        status = result.get("status")
        if status == "started":
            logger.info("✓ Render job started successfully")
            logger.info(f"Sequence: {result.get('sequence')}")
            logger.info(f"Job Name: {result.get('job_name')}")
            logger.info(f"Output: {result.get('output_directory')}")
            logger.info("Note: Render will continue in background process")
            return 0

        if status == "skipped":
            logger.info(f"Job skipped: {result.get('reason')}")
            return 0

        logger.error(f"Unknown result status: {result}")
        return 1

    except Exception as e:
        logger.error(f"Failed to execute render job: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
