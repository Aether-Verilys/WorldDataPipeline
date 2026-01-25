import unreal
import sys
import json

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
    from . import camera_exporter

    logger.info("Starting camera export job execution...")

    argv = list(argv) if argv is not None else sys.argv
    env_key = "UE_MANIFEST_PATH"
    manifest_path = job_utils.resolve_manifest_path_from_env(env_key, argv)
    if not manifest_path:
        logger.error("No manifest path provided")
        logger.info(f"Usage: Set {env_key} environment variable or use --manifest=<path>")
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

    try:
        from pathlib import Path

        project_content_dir = unreal.Paths.project_content_dir()
        project_path = Path(project_content_dir).parent
        project_saved_dir = project_path / "Saved"

        logger.info("========== Current UE Project Info ==========")
        logger.info(f"Project Root: {project_path}")
        logger.info(f"Content Directory: {project_content_dir}")
        logger.info(f"Saved Directory: {project_saved_dir}")
        logger.info("=============================================")
    except Exception as e:
        logger.warning(f"Failed to get project directories: {e}")

    if job_type != "export":
        logger.error(f"Invalid job type '{job_type}', expected 'export'")
        return 1

    if not sequence_path:
        logger.error("No sequence specified in manifest")
        return 1

    try:
        logger.info("Starting camera export...")
        result = camera_exporter.export_camera_from_manifest(manifest)

        if result.get("status") == "success":
            logger.info("✓ Camera export completed successfully")
            logger.info(f"Sequence: {result.get('sequence')}")
            logger.info(f"Output directory: {result.get('output_dir')}")
            logger.info(f"Extrinsic CSV: {result.get('extrinsic_csv')}")
            logger.info(f"Transform CSV: {result.get('transform_csv')}")

            try:
                import datetime

                log_entry = {
                    "job_type": "export",
                    "job_id": job_id,
                    "sequence": sequence_path,
                    "output_path": result.get("output_dir"),
                    "extrinsic_csv": result.get("extrinsic_csv"),
                    "transform_csv": result.get("transform_csv"),
                    "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                }
                script_dir = os.path.dirname(os.path.abspath(__file__))
                pipeline_dir = os.path.dirname(script_dir)
                log_file = os.path.join(pipeline_dir, "job_history.log")
                with open(log_file, "a", encoding="utf-8") as logf:
                    logf.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except Exception as logerr:
                logger.warning(f"Failed to write job_history.log: {logerr}")

            return 0

        logger.error(f"Export returned unexpected status: {result}")
        return 1

    except Exception as e:
        logger.error(f"Failed to execute export job: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
