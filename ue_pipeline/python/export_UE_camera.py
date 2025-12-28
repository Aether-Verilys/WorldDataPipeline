import unreal
import csv
import math
import os
import re

# 单位转换常量
UE_TO_METERS = 0.01  # UE默认单位是cm，转换为m需要乘以0.01


# 读取 Sequencer 中某个绑定（Binding）的Transform通道
def get_transform_channels(sequence, binding_name):
    """获取binding的位置和旋转通道"""
    bindings = sequence.get_bindings()

    for b in bindings:
        if b.get_name() == binding_name:
            tracks = b.get_tracks()
            channels = {}

            for t in tracks:
                sections = t.get_sections()
                for s in sections:
                    float_channels = s.get_all_channels()

                    for ch in float_channels:
                        ch_name = ch.get_name().lower()

                        # 位置通道
                        if "location.x" in ch_name:
                            channels["loc_x"] = ch
                        elif "location.y" in ch_name:
                            channels["loc_y"] = ch
                        elif "location.z" in ch_name:
                            channels["loc_z"] = ch

                        # 旋转通道
                        elif "rotation.x" in ch_name:
                            channels["rot_x"] = ch  # Roll
                        elif "rotation.y" in ch_name:
                            channels["rot_y"] = ch  # Pitch
                        elif "rotation.z" in ch_name:
                            channels["rot_z"] = ch  # Yaw

            return channels

    unreal.log_warning(f"[Warn] Binding '{binding_name}' 未找到！")
    return None


# 从缓存的keys中采样值
def sample_channel_cached(cached_keys, frame_number):
    """
    从预缓存的keys中采样最近邻值
    cached_keys: list of (frame_number, value) tuples
    """
    if not cached_keys:
        return 0.0
    
    # 找到最接近的帧
    nearest = min(cached_keys, key=lambda kv: abs(kv[0] - frame_number))
    return nearest[1]


def cache_channel_keys(channel):
    """
    一次性获取channel的所有keys并缓存为简单的(frame, value)列表
    避免在循环中重复调用get_keys()造成UObject泄漏
    """
    if channel is None:
        return []
    
    keys = channel.get_keys()
    if not keys:
        return []
    
    # 转换为简单的Python数据结构，释放UE对象引用
    cached = [(k.get_time().frame_number.value, k.get_value()) for k in keys]
    return cached


# 矩阵转置 (3x3)
def transpose_matrix3(M):
    return [[M[j][i] for j in range(3)] for i in range(3)]


# UE Rotator → RotationMatrix（Yaw→Pitch→Roll）
def rot_to_matrix(roll_deg, pitch_deg, yaw_deg):
    roll  = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    yaw   = math.radians(yaw_deg)

    cr = math.cos(roll);  sr = math.sin(roll)
    cp = math.cos(pitch); sp = math.sin(pitch)
    cy = math.cos(yaw);   sy = math.sin(yaw)

    # Unreal Rotator order: Yaw(Z) → Pitch(Y) → Roll(X)
    R = [
        [cy*cp, cy*sp*sr - sy*cr, cy*sp*cr + sy*sr],
        [sy*cp, sy*sp*sr + cy*cr, sy*sp*cr - cy*sr],
        [-sp,   cp*sr,            cp*cr]
    ]
    return R


# 计算相机外参矩阵（视图矩阵）
def compute_camera_extrinsic(camera_loc, camera_rot):
    """
    计算相机外参矩阵
    
    camera_loc: [x, y, z] - 相机世界位置（米）
    camera_rot: [roll, pitch, yaw] - 相机世界旋转（度）
    
    Returns: 4x4外参矩阵（视图矩阵 = 世界变换矩阵的逆）
    """
    # 1. 计算相机世界旋转矩阵
    R_world = rot_to_matrix(camera_rot[0], camera_rot[1], camera_rot[2])
    
    # 2. 计算外参矩阵 (视图矩阵) = 世界矩阵的逆
    # R^T (旋转的转置)
    RT = transpose_matrix3(R_world)
    
    # -R^T * T (平移的变换)
    tx = -(RT[0][0]*camera_loc[0] + RT[0][1]*camera_loc[1] + RT[0][2]*camera_loc[2])
    ty = -(RT[1][0]*camera_loc[0] + RT[1][1]*camera_loc[1] + RT[1][2]*camera_loc[2])
    tz = -(RT[2][0]*camera_loc[0] + RT[2][1]*camera_loc[1] + RT[2][2]*camera_loc[2])
    
    # 外参矩阵（行主序）
    extrinsic = [
        [RT[0][0], RT[0][1], RT[0][2], tx],
        [RT[1][0], RT[1][1], RT[1][2], ty],
        [RT[2][0], RT[2][1], RT[2][2], tz],
        [0,        0,        0,        1 ]
    ]
    
    return extrinsic


# 主导出函数
def export_camera_data(sequence_path, binding_name_camera, output_dir):
    """
    导出相机数据（Transform和外参矩阵）
    
    Args:
        sequence_path: Level Sequence路径
        binding_name_camera: Camera binding名称（如BP_Cameraman0）
        output_dir: 输出目录
    """
    # 首先检查asset是否存在
    if not unreal.EditorAssetLibrary.does_asset_exist(sequence_path):
        unreal.log_error(f"[ExportCamera] Asset不存在: {sequence_path}")
        return
    
    # 使用EditorAssetLibrary加载asset
    asset_data = unreal.EditorAssetLibrary.find_asset_data(sequence_path)
    if not asset_data:
        unreal.log_error(f"[ExportCamera] 无法获取asset data: {sequence_path}")
        return
    
    # 检查是否是LevelSequence
    if asset_data.asset_class_path.asset_name != "LevelSequence":
        unreal.log_error(f"[ExportCamera] Asset不是LevelSequence: {sequence_path}")
        return
    
    # 加载asset
    sequence = unreal.EditorAssetLibrary.load_asset(sequence_path)
    if sequence is None:
        unreal.log_error(f"[ExportCamera] 无法加载 Level Sequence: {sequence_path}")
        return

    # 获取相机的transform通道
    camera_channels = get_transform_channels(sequence, binding_name_camera)
    if not camera_channels:
        unreal.log_error(f"无法获取Binding '{binding_name_camera}' 的通道")
        return

    start_frame = sequence.get_playback_start()
    end_frame = sequence.get_playback_end()

    # 预先缓存所有channel的keys，避免循环中重复调用get_keys()
    unreal.log("[ExportCamera] Caching channel keys...")
    camera_cache = {
        "loc_x": cache_channel_keys(camera_channels.get("loc_x")),
        "loc_y": cache_channel_keys(camera_channels.get("loc_y")),
        "loc_z": cache_channel_keys(camera_channels.get("loc_z")),
        "rot_x": cache_channel_keys(camera_channels.get("rot_x")),
        "rot_y": cache_channel_keys(camera_channels.get("rot_y")),
        "rot_z": cache_channel_keys(camera_channels.get("rot_z"))
    }
    unreal.log(f"[ExportCamera] Keys cached. Processing {end_frame - start_frame + 1} frames...")

    # 规范化输出目录路径
    output_dir = os.path.normpath(output_dir)
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 从序列路径中提取序列名称
    sequence_name = sequence_path.rstrip('/').split('/')[-1]
    output_extrinsic_csv = os.path.join(output_dir, f"{sequence_name}_extrinsic.csv")
    output_transform_csv = os.path.join(output_dir, f"{sequence_name}_transform.csv")
    
    unreal.log(f"[ExportCamera] Output directory: {output_dir}")
    unreal.log(f"[ExportCamera] Extrinsic CSV: {output_extrinsic_csv}")
    unreal.log(f"[ExportCamera] Transform CSV: {output_transform_csv}")

    # 同时打开两个CSV文件，在一次循环中写入所有数据
    with open(output_extrinsic_csv, 'w', newline='') as f_ext, \
         open(output_transform_csv, 'w', newline='') as f_trans:
        
        # 外参CSV writer
        writer_ext = csv.writer(f_ext)
        writer_ext.writerow(["frame", "m00","m01","m02","m03",
                                       "m10","m11","m12","m13",
                                       "m20","m21","m22","m23",
                                       "m30","m31","m32","m33"])
        
        # Transform CSV writer
        writer_trans = csv.writer(f_trans)
        writer_trans.writerow(["frame", "loc_x", "loc_y", "loc_z", 
                              "rot_x", "rot_y", "rot_z"])

        # 循环每一帧
        for frame in range(start_frame, end_frame + 1):
            # 采样相机位置和旋转
            loc_x = sample_channel_cached(camera_cache["loc_x"], frame) * UE_TO_METERS  
            loc_y = sample_channel_cached(camera_cache["loc_y"], frame) * UE_TO_METERS  
            loc_z = sample_channel_cached(camera_cache["loc_z"], frame) * UE_TO_METERS 
            rot_x = sample_channel_cached(camera_cache["rot_x"], frame)  # Roll
            rot_y = sample_channel_cached(camera_cache["rot_y"], frame)  # Pitch
            rot_z = sample_channel_cached(camera_cache["rot_z"], frame)  # Yaw
            
            camera_loc = [loc_x, loc_y, loc_z] 
            camera_rot = [rot_x, rot_y, rot_z] 

            # 计算外参矩阵
            M = compute_camera_extrinsic(camera_loc, camera_rot)
            
            # 写入外参 CSV
            row_data = [frame]
            for i in range(4):
                for j in range(4):
                    row_data.append(M[i][j])
            writer_ext.writerow(row_data)
            
            # 写入 Transform CSV
            writer_trans.writerow([frame, loc_x, loc_y, loc_z, rot_x, rot_y, rot_z])

    unreal.log(f"✓ 外参矩阵导出完成 → {output_extrinsic_csv}")
    unreal.log(f"✓ Transform数据导出完成 → {output_transform_csv}")


# Manifest-driven API
def export_camera_from_manifest(manifest: dict) -> dict:
    """
    从manifest配置导出相机数据
    
    Args:
        manifest: Job配置字典
        
    Returns:
        导出结果字典
    """
    sequence_path = manifest.get("sequence")
    if not sequence_path:
        raise ValueError("Manifest missing 'sequence' field")
    
    # 获取相机配置
    camera_config = manifest.get("camera_export", {})
    
    # 确定输出目录
    output_dir = camera_config.get("output_path") or camera_config.get("export_path")
    if not output_dir:
        # 从sequence路径自动计算：output/场景名/序列名
        # 从manifest读取ue_config
        ue_config = manifest.get("ue_config", {})
        output_base = ue_config.get("output_base_dir", "output")
        if not output_base or output_base == "output":
            unreal.log_warning("[ExportCamera] No output_base_dir in manifest.ue_config, using default 'output'")
        
        # 从sequence路径提取序列名
        sequence_name = sequence_path.rstrip('/').split('/')[-1]  # Lvl_FirstPerson_007
        
        # 从序列名提取场景名（去除后缀数字）
        # Lvl_FirstPerson_007 -> Lvl_FirstPerson
        import re
        scene_name = re.sub(r'_\d+$', '', sequence_name)
        
        # 构建输出路径：output/场景名/序列名
        output_dir = os.path.join(output_base, scene_name, sequence_name)
        unreal.log(f"[ExportCamera] Auto-generated output path: {output_dir}")
    
    # 规范化输出目录路径
    output_dir = os.path.normpath(output_dir)
    
    # 获取binding名称
    binding_camera = camera_config.get("binding_camera") or camera_config.get("binding_transform")
    if not binding_camera:
        raise ValueError("No camera binding specified in manifest")
    
    unreal.log(f"[ExportCamera] Exporting from sequence: {sequence_path}")
    unreal.log(f"[ExportCamera] Camera binding: {binding_camera}")
    unreal.log(f"[ExportCamera] Output directory: {output_dir}")
    
    # 调用主导出函数
    export_camera_data(sequence_path, binding_camera, output_dir)
    
    # 返回结果路径
    sequence = unreal.EditorAssetLibrary.load_asset(sequence_path)
    sequence_name = sequence.get_name() if sequence else "unknown"
    
    return {
        "status": "success",
        "sequence": sequence_path,
        "output_dir": output_dir,
        "extrinsic_csv": os.path.normpath(os.path.join(output_dir, f"{sequence_name}_extrinsic.csv")),
        "transform_csv": os.path.normpath(os.path.join(output_dir, f"{sequence_name}_transform.csv"))
    }


if __name__ == "__main__":
    unreal.log_error("This script should be called through export_camera_from_manifest() with a job manifest")
    unreal.log_error("Example: python -c \"import export_UE_camera; export_UE_camera.export_camera_from_manifest(manifest)\"")
