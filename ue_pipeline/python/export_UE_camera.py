import unreal
import csv
import math
import os

# 配置区域 - 在此处修改所有路径和参数
SEQUENCE_PATH = "/Game/CameraController/2025-11-25/Scene_1_10_Subscenes/BP_FirstPersonCharacter0_Scene_1_10"
BINDING_NAME_TRANSFORM = "BP_FirstPersonCharacter0"
BINDING_NAME_CAMERA = "FirstPersonCamera"
OUTPUT_DIR = "F:/Backup_Data"  # 输出目录

# 相机默认位置（当LevelSequence中没有关键帧时使用）
DEFAULT_CAMERA_LOC = [0.0, 0.0, 80.0]  # [X, Y, Z] 单位：cm
DEFAULT_CAMERA_ROT = [0.0, 0.0, 0.0]  # [Roll, Pitch, Yaw] 单位：度

# 单位转换常量
UE_TO_METERS = 0.01  # UE默认单位是cm，转换为m需要乘以0.01


# 读取 Sequencer 中某个绑定（Binding）对应的通道
def get_channels_from_binding(sequence, binding_name):
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

                        # 位置 channel
                        if "location.x" in ch_name:
                            channels["loc_x"] = ch
                        elif "location.y" in ch_name:
                            channels["loc_y"] = ch
                        elif "location.z" in ch_name:
                            channels["loc_z"] = ch

                        # 旋转 channel
                        elif "rotation.x" in ch_name:
                            channels["rot_x"] = ch  # Roll
                        elif "rotation.y" in ch_name:
                            channels["rot_y"] = ch  # Pitch
                        elif "rotation.z" in ch_name:
                            channels["rot_z"] = ch  # Yaw

            return channels

    unreal.log_warning(f"[Warn] Binding '{binding_name}' 未找到！")
    return None


# 最近邻取值 - 使用预缓存的keys避免重复调用get_keys()
def sample_channel_cached(cached_keys, frame_number, default_value=0.0):
    """
    从预缓存的keys中采样
    cached_keys: list of (frame_number, value) tuples
    default_value: 当没有关键帧数据时返回的默认值
    """
    if not cached_keys:
        return default_value
    
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


# 矩阵乘法 (3x3)
def multiply_matrix3(A, B):
    result = [[0]*3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            result[i][j] = sum(A[i][k] * B[k][j] for k in range(3))
    return result


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


# 计算相机世界坐标和外参矩阵
def compute_camera_extrinsic(transform_loc, transform_rot, camera_loc, camera_rot):
    """
    计算相机的世界坐标和外参矩阵
    
    transform_loc: [x, y, z] - 角色世界位置
    transform_rot: [roll, pitch, yaw] - 角色世界旋转
    camera_loc: [x, y, z] - 相机相对位置
    camera_rot: [roll, pitch, yaw] - 相机相对旋转
    """
    # 1. 角色的世界变换矩阵
    R_transform = rot_to_matrix(transform_rot[0], transform_rot[1], transform_rot[2])
    
    # 2. 相机的相对变换矩阵
    R_camera = rot_to_matrix(camera_rot[0], camera_rot[1], camera_rot[2])
    
    # 3. 计算相机世界旋转 = 角色旋转 * 相机相对旋转
    R_world = multiply_matrix3(R_transform, R_camera)
    
    # 4. 计算相机世界位置 = 角色位置 + 角色旋转 * 相机相对位置
    rotated_cam_pos = [
        R_transform[0][0]*camera_loc[0] + R_transform[0][1]*camera_loc[1] + R_transform[0][2]*camera_loc[2],
        R_transform[1][0]*camera_loc[0] + R_transform[1][1]*camera_loc[1] + R_transform[1][2]*camera_loc[2],
        R_transform[2][0]*camera_loc[0] + R_transform[2][1]*camera_loc[1] + R_transform[2][2]*camera_loc[2]
    ]
    
    cam_world_pos = [
        transform_loc[0] + rotated_cam_pos[0],
        transform_loc[1] + rotated_cam_pos[1],
        transform_loc[2] + rotated_cam_pos[2]
    ]
    
    # 5. 计算外参矩阵 (视图矩阵) = 世界矩阵的逆
    # R^T (旋转的转置)
    RT = transpose_matrix3(R_world)
    
    # -R^T * T (平移的变换)
    tx = -(RT[0][0]*cam_world_pos[0] + RT[0][1]*cam_world_pos[1] + RT[0][2]*cam_world_pos[2])
    ty = -(RT[1][0]*cam_world_pos[0] + RT[1][1]*cam_world_pos[1] + RT[1][2]*cam_world_pos[2])
    tz = -(RT[2][0]*cam_world_pos[0] + RT[2][1]*cam_world_pos[1] + RT[2][2]*cam_world_pos[2])
    
    # 外参矩阵（行主序）
    extrinsic = [
        [RT[0][0], RT[0][1], RT[0][2], tx],
        [RT[1][0], RT[1][1], RT[1][2], ty],
        [RT[2][0], RT[2][1], RT[2][2], tz],
        [0,        0,        0,        1 ]
    ]
    
    return extrinsic, cam_world_pos


# 主执行
def export_camera_data(sequence_path, binding_name_transform, binding_name_camera, output_dir,
                      default_camera_loc=None, default_camera_rot=None):
    """
    导出相机数据
    
    Args:
        sequence_path: Level Sequence路径
        binding_name_transform: Transform绑定名称
        binding_name_camera: Camera绑定名称
        output_dir: 输出目录
        default_camera_loc: 相机默认位置 [x, y, z]，当没有关键帧时使用
        default_camera_rot: 相机默认旋转 [roll, pitch, yaw]，当没有关键帧时使用
    """

    if default_camera_loc is None:
        default_camera_loc = DEFAULT_CAMERA_LOC
    if default_camera_rot is None:
        default_camera_rot = DEFAULT_CAMERA_ROT

    sequence = unreal.load_asset(sequence_path)
    if sequence is None:
        unreal.log_error("找不到 Level Sequence！")
        return

    # 获取 transform + camera 的 channel
    transform_channels = get_channels_from_binding(sequence, binding_name_transform)
    camera_channels = get_channels_from_binding(sequence, binding_name_camera)

    if not transform_channels or not camera_channels:
        unreal.log_error("Channel 获取失败")
        return

    start_frame = sequence.get_playback_start()
    end_frame = sequence.get_playback_end()

    # 预先缓存所有channel的keys，避免循环中重复调用get_keys()
    unreal.log("[ExportCamera] Caching channel keys to prevent UObject leak...")
    transform_cache = {
        "loc_x": cache_channel_keys(transform_channels.get("loc_x")),
        "loc_y": cache_channel_keys(transform_channels.get("loc_y")),
        "loc_z": cache_channel_keys(transform_channels.get("loc_z")),
        "rot_x": cache_channel_keys(transform_channels.get("rot_x")),
        "rot_y": cache_channel_keys(transform_channels.get("rot_y")),
        "rot_z": cache_channel_keys(transform_channels.get("rot_z"))
    }
    
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

    # 从序列路径中提取最后的名称（最后一个 / 后面的部分）
    sequence_name = sequence_path.rstrip('/').split('/')[-1]
    output_extrinsic_csv = os.path.join(output_dir, f"{sequence_name}_extrinsic.csv")
    output_transform_csv = os.path.join(output_dir, f"{sequence_name}_transform.csv")
    
    unreal.log(f"[ExportCamera] Output directory: {output_dir}")
    unreal.log(f"[ExportCamera] Extrinsic CSV: {output_extrinsic_csv}")
    unreal.log(f"[ExportCamera] Transform CSV: {output_transform_csv}")

    # 同时打开两个CSV文件，在一次循环中写入所有数据
    # 避免重复采样导致的UE对象访问问题
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
        writer_trans.writerow(["frame", 
                              "transform_loc_x", "transform_loc_y", "transform_loc_z",
                              "transform_rot_x", "transform_rot_y", "transform_rot_z",
                              "camera_loc_x", "camera_loc_y", "camera_loc_z",
                              "camera_rot_x", "camera_rot_y", "camera_rot_z"])

        # 只循环一次，同时写入两个文件
        for frame in range(start_frame, end_frame + 1):
            # Transform 位置和旋转
            t_loc_x = sample_channel_cached(transform_cache["loc_x"], frame) * UE_TO_METERS  
            t_loc_y = sample_channel_cached(transform_cache["loc_y"], frame) * UE_TO_METERS  
            t_loc_z = sample_channel_cached(transform_cache["loc_z"], frame) * UE_TO_METERS 
            t_rot_x = sample_channel_cached(transform_cache["rot_x"], frame)  
            t_rot_y = sample_channel_cached(transform_cache["rot_y"], frame)  
            t_rot_z = sample_channel_cached(transform_cache["rot_z"], frame) 
            
            transform_loc = [t_loc_x, t_loc_y, t_loc_z] 
            transform_rot = [t_rot_x, t_rot_y, t_rot_z] 

            # Camera 相对位置和旋转 - 使用缓存的keys采样，如果没有关键帧则使用默认值
            c_loc_x = sample_channel_cached(camera_cache["loc_x"], frame, default_camera_loc[0]) * UE_TO_METERS 
            c_loc_y = sample_channel_cached(camera_cache["loc_y"], frame, default_camera_loc[1]) * UE_TO_METERS 
            c_loc_z = sample_channel_cached(camera_cache["loc_z"], frame, default_camera_loc[2]) * UE_TO_METERS 
            c_rot_x = sample_channel_cached(camera_cache["rot_x"], frame, default_camera_rot[0]) 
            c_rot_y = sample_channel_cached(camera_cache["rot_y"], frame, default_camera_rot[1]) 
            c_rot_z = sample_channel_cached(camera_cache["rot_z"], frame, default_camera_rot[2])  
            
            camera_loc = [c_loc_x, c_loc_y, c_loc_z] 
            camera_rot = [c_rot_x, c_rot_y, c_rot_z]

            # 计算外参矩阵
            M, cam_world_pos = compute_camera_extrinsic(transform_loc, transform_rot, camera_loc, camera_rot)
            
            # 写入外参 CSV
            row_data = [frame]
            for i in range(4):
                for j in range(4):
                    row_data.append(M[i][j])
            writer_ext.writerow(row_data)
            
            # 写入 Transform CSV
            writer_trans.writerow([frame,
                                  t_loc_x, t_loc_y, t_loc_z,
                                  t_rot_x, t_rot_y, t_rot_z,
                                  c_loc_x, c_loc_y, c_loc_z,
                                  c_rot_x, c_rot_y, c_rot_z])

    unreal.log(f"外参导出完成 → {output_extrinsic_csv}")
    unreal.log(f"原始Transform数据导出完成 → {output_transform_csv}")


# Manifest-driven API
def export_camera_from_manifest(manifest: dict) -> dict:
    import unreal
    
    sequence_path = manifest.get("sequence")
    if not sequence_path:
        raise ValueError("Manifest missing 'sequence' field")
    
    # Support both "camera_export" (new format) and "camera" (legacy format)
    camera_config = manifest.get("camera_export", manifest.get("camera", {}))
    frame_range = manifest.get("frame_range", {})
    
    # Determine output directory - try multiple field names for compatibility
    output_dir = camera_config.get("output_path") or camera_config.get("export_path")
    if not output_dir:
        # Use job_utils to compute default path
        try:
            import job_utils
            paths = job_utils.get_output_paths(manifest)
            output_dir = paths.get("camera_export_dir", OUTPUT_DIR)
        except:
            output_dir = OUTPUT_DIR
    
    # Normalize output directory path
    output_dir = os.path.normpath(output_dir)
    
    # Get binding names from config or use defaults
    binding_transform = camera_config.get("binding_transform", BINDING_NAME_TRANSFORM)
    binding_camera = camera_config.get("binding_camera", BINDING_NAME_CAMERA)
    
    # Get default camera position/rotation from config or use defaults
    default_camera_loc = camera_config.get("default_camera_loc", DEFAULT_CAMERA_LOC)
    default_camera_rot = camera_config.get("default_camera_rot", DEFAULT_CAMERA_ROT)
    
    unreal.log(f"[ExportCamera] Exporting from sequence: {sequence_path}")
    unreal.log(f"[ExportCamera] Output directory: {output_dir}")
    unreal.log(f"[ExportCamera] Default camera loc: {default_camera_loc}")
    unreal.log(f"[ExportCamera] Default camera rot: {default_camera_rot}")
    
    # Call the main export function
    export_camera_data(
        sequence_path,
        binding_transform,
        binding_camera,
        output_dir,
        default_camera_loc,
        default_camera_rot
    )
    
    # Return result paths (normalized)
    sequence = unreal.load_asset(sequence_path)
    sequence_name = sequence.get_name() if sequence else "unknown"
    
    return {
        "status": "success",
        "sequence": sequence_path,
        "output_dir": output_dir,
        "extrinsic_csv": os.path.normpath(os.path.join(output_dir, f"{sequence_name}_extrinsic.csv")),
        "transform_csv": os.path.normpath(os.path.join(output_dir, f"{sequence_name}_transform.csv"))
    }


if __name__ == "__main__":
    export_camera_data(
        SEQUENCE_PATH,
        BINDING_NAME_TRANSFORM,
        BINDING_NAME_CAMERA,
        OUTPUT_DIR,
        DEFAULT_CAMERA_LOC,
        DEFAULT_CAMERA_ROT
    )