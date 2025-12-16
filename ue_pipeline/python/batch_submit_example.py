"""
快速提交任务脚本
用于快速生成并提交批量任务到 worker
"""
import sys
import os

# 添加当前目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator_submit import create_job_manifest, submit_job


def submit_batch_sequences(
    sequences,
    map_path,
    start_frame=0,
    end_frame=120,
    watch_dir=None,
    render_enabled=True,
    camera_export_enabled=True
):
    """
    批量提交多个序列
    
    Args:
        sequences: 序列路径列表
        map_path: 地图路径
        start_frame: 起始帧
        end_frame: 结束帧
        watch_dir: 监听目录
        render_enabled: 是否渲染
        camera_export_enabled: 是否导出相机
    """
    if watch_dir is None:
        # 默认使用当前脚本目录的 jobs/inbox
        current_dir = os.path.dirname(os.path.abspath(__file__))
        watch_dir = os.path.join(os.path.dirname(current_dir), "jobs", "inbox")
    
    print(f"批量提交 {len(sequences)} 个序列到: {watch_dir}")
    print(f"地图: {map_path}")
    print(f"帧范围: {start_frame} - {end_frame}")
    print(f"渲染: {'开启' if render_enabled else '关闭'}")
    print(f"相机导出: {'开启' if camera_export_enabled else '关闭'}")
    print("=" * 60)
    
    submitted_jobs = []
    
    for i, sequence in enumerate(sequences, 1):
        print(f"\n[{i}/{len(sequences)}] 提交: {sequence}")
        
        try:
            manifest = create_job_manifest(
                sequence_path=sequence,
                map_path=map_path,
                start_frame=start_frame,
                end_frame=end_frame,
                render_enabled=render_enabled,
                camera_export_enabled=camera_export_enabled
            )
            
            job_id = submit_job(manifest, watch_dir)
            submitted_jobs.append(job_id)
            print(f"  ✓ Job ID: {job_id}")
        
        except Exception as e:
            print(f"  ✗ 失败: {e}")
    
    print("\n" + "=" * 60)
    print(f"完成! 成功提交 {len(submitted_jobs)}/{len(sequences)} 个任务")
    print("\n已提交任务 ID:")
    for job_id in submitted_jobs:
        print(f"  - {job_id}")
    
    return submitted_jobs


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    # 示例 1: 批量提交多个序列
    sequences = [
        "/Game/CameraController/2025-12-04/Scene_1",
        "/Game/CameraController/2025-12-04/Scene_2",
        "/Game/CameraController/2025-12-04/Scene_3",
    ]
    
    # 修改为你的实际地图路径
    map_path = "/Game/Maps/NorthernForest"
    
    # 提交（仅导出相机数据，不渲染）
    submit_batch_sequences(
        sequences=sequences,
        map_path=map_path,
        start_frame=0,
        end_frame=120,
        render_enabled=False,      # 关闭渲染
        camera_export_enabled=True  # 仅导出相机
    )
    
    # 示例 2: 单个任务（完整渲染+相机导出）
    # manifest = create_job_manifest(
    #     sequence_path="/Game/CameraController/2025-12-04/Scene_1",
    #     map_path="/Game/Maps/NorthernForest",
    #     start_frame=0,
    #     end_frame=240,
    #     render_enabled=True,
    #     camera_export_enabled=True,
    #     output_base_dir="F:/Exports"
    # )
    # submit_job(manifest, watch_dir="jobs/inbox")
