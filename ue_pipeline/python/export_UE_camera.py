import unreal
import csv
import math
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from logger import logger


UE_TO_METERS = 0.01  # UE默认单位是cm，转换为m需要乘以0.01


def _split_ue_asset_path(sequence_path: str) -> tuple[str, str]:
    """Normalize UE asset paths.

    UE sometimes returns object paths like `/Game/X/Y/Asset.Asset`.
    For file naming and EditorAssetLibrary operations we want the package path:
    `/Game/X/Y/Asset`, and the asset name `Asset`.
    """
    p = (sequence_path or "").strip()
    if not p:
        return p, ""

    leaf = p.rstrip("/").split("/")[-1]
    if "." in leaf:
        package_path = p.rsplit(".", 1)[0]
        asset_name = leaf.split(".", 1)[0]
        return package_path, asset_name

    return p, leaf


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

    logger.warning(f"[Warn] Binding '{binding_name}' 未找到！")
    return None


def get_camera_component_from_blueprint(actor_blueprint_class_path):
    if not actor_blueprint_class_path:
        logger.warning("No blueprint class path provided")
        return None
    
    try:
        # 加载蓝图类
        blueprint_class = unreal.EditorAssetLibrary.load_blueprint_class(actor_blueprint_class_path)
        if not blueprint_class:
            logger.warning(f"Failed to load blueprint class: {actor_blueprint_class_path}")
            return None
        
        # 获取类的默认对象 (CDO)
        cdo = unreal.get_default_object(blueprint_class)
        if not cdo:
            logger.warning(f"Failed to get CDO from blueprint class: {actor_blueprint_class_path}")
            return None
        
        logger.info(f"Loaded blueprint CDO: {actor_blueprint_class_path}")
        
        # 从CDO中查找相机组件
        camera_component = _find_camera_component_in_actor(cdo)
        if camera_component:
            # logger.info(f"Found camera component in blueprint CDO")
            return camera_component
        else:
            logger.warning(f"No camera component found in blueprint CDO")
            return None
            
    except Exception as e:
        logger.error(f"Error loading camera from blueprint: {e}")
        import traceback
        traceback.print_exc()
        return None


def _find_camera_component_in_actor(actor):
    if actor is None:
        return None
    
    # 首先检查根组件是否是相机
    try:
        root_component = actor.get_editor_property("root_component")
        if root_component and _is_camera_component(root_component):
            return root_component
    except Exception:
        pass
    
    # 查找所有相机类型组件
    camera_classes = []
    for cls_name in ("CineCameraComponent", "CameraComponent"):
        cls = getattr(unreal, cls_name, None)
        if cls:
            camera_classes.append(cls)
    
    components = []
    for cls in camera_classes:
        try:
            getter = getattr(actor, "get_components_by_class", None)
            if callable(getter):
                components.extend(list(getter(cls)))
        except Exception:
            pass
    
    # 返回第一个找到的相机组件
    if components:
        return components[0]
    
    return None


def _is_camera_component(component):
    """检查组件是否是相机组件"""
    if component is None:
        return False
    
    camera_class_names = ["CineCameraComponent", "CameraComponent"]
    for cls_name in camera_class_names:
        cls = getattr(unreal, cls_name, None)
        if cls and isinstance(component, cls):
            return True
    return False


def get_camera_intrinsics(camera_component):
    if camera_component is None:
        logger.warning("Camera component is None, using default intrinsics")
        return {
            "fov": 90.0,
            "aspect_ratio": 16.0/9.0,
            "width": 1920,
            "height": 1080,
            "sensor_width": 24.576,
        }
    
    intrinsics = {}
    
    try:
        # FOV (Field of View)
        fov = camera_component.get_editor_property("field_of_view")
        intrinsics["fov"] = float(fov) if fov is not None else 90.0
    except Exception:
        intrinsics["fov"] = 90.0
    
    try:
        # Aspect Ratio
        aspect_ratio = camera_component.get_editor_property("aspect_ratio")
        intrinsics["aspect_ratio"] = float(aspect_ratio) if aspect_ratio is not None else 16.0/9.0
    except Exception:
        intrinsics["aspect_ratio"] = 16.0/9.0
    
    # 从PostProcess设置中获取sensor_width (Depth of Field -> Sensor Width)
    try:
        post_process_settings = camera_component.get_editor_property("post_process_settings")
        if post_process_settings:
            sensor_width = post_process_settings.get_editor_property("depth_of_field_sensor_width")
            intrinsics["sensor_width"] = float(sensor_width) if sensor_width is not None else 24.576
        else:
            intrinsics["sensor_width"] = 24.576
    except Exception:
        intrinsics["sensor_width"] = 24.576
    
    # 默认分辨率
    intrinsics["width"] = 1920
    intrinsics["height"] = 1080
    
    return intrinsics


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
def export_camera_data(sequence_path, binding_name_camera, output_dir, actor_blueprint_class_path=None):
    """
    导出相机数据（Transform和外参矩阵）
    
    Args:
        sequence_path: Level Sequence路径
        binding_name_camera: Camera binding名称（如BP_Cameraman0）
        output_dir: 输出目录
        actor_blueprint_class_path: Actor蓝图类路径（用于读取内参）
    """
    package_path, sequence_name = _split_ue_asset_path(sequence_path)

    if not unreal.EditorAssetLibrary.does_asset_exist(package_path):
        logger.error(f"[ExportCamera] Asset不存在: {package_path}")
        return
    
    # 使用EditorAssetLibrary加载asset
    asset_data = unreal.EditorAssetLibrary.find_asset_data(package_path)
    if not asset_data:
        logger.error(f"[ExportCamera] 无法获取asset data: {package_path}")
        return
    
    # 检查是否是LevelSequence
    if asset_data.asset_class_path.asset_name != "LevelSequence":
        logger.error(f"[ExportCamera] Asset不是LevelSequence: {sequence_path}")
        return
    
    # 加载asset
    sequence = unreal.EditorAssetLibrary.load_asset(package_path)
    if sequence is None:
        logger.error(f"[ExportCamera] 无法加载 Level Sequence: {package_path}")
        return

    # 获取相机的transform通道
    camera_channels = get_transform_channels(sequence, binding_name_camera)
    if not camera_channels:
        logger.error(f"无法获取Binding '{binding_name_camera}' 的通道")
        return

    start_frame = sequence.get_playback_start()
    end_frame = sequence.get_playback_end()

    # 预先缓存所有channel的keys，避免循环中重复调用get_keys()
    camera_cache = {
        "loc_x": cache_channel_keys(camera_channels.get("loc_x")),
        "loc_y": cache_channel_keys(camera_channels.get("loc_y")),
        "loc_z": cache_channel_keys(camera_channels.get("loc_z")),
        "rot_x": cache_channel_keys(camera_channels.get("rot_x")),
        "rot_y": cache_channel_keys(camera_channels.get("rot_y")),
        "rot_z": cache_channel_keys(camera_channels.get("rot_z"))
    }
    # logger.info(f"[ExportCamera] Keys cached. Processing {end_frame - start_frame + 1} frames...")

    # 规范化输出目录路径
    output_dir = os.path.normpath(output_dir)
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    output_extrinsic_csv = os.path.join(output_dir, f"{sequence_name}_extrinsic.csv")
    output_transform_csv = os.path.join(output_dir, f"{sequence_name}_transform.csv")
    output_intrinsic_csv = os.path.join(output_dir, f"{sequence_name}_intrinsic.csv")

    # 从蓝图类的CDO获取相机组件并读取内参
    camera_component = None
    if actor_blueprint_class_path:
        camera_component = get_camera_component_from_blueprint(actor_blueprint_class_path)
    else:
        logger.warning("No actor_blueprint_class_path provided, using default intrinsics")
    
    intrinsics = get_camera_intrinsics(camera_component)

    # 导出内参表（单行CSV，包含所有内参）
    with open(output_intrinsic_csv, 'w', newline='') as f_intr:
        writer_intr = csv.writer(f_intr)
        writer_intr.writerow(["fov", "aspect_ratio", "width", "height", "sensor_width"])
        writer_intr.writerow([
            intrinsics["fov"],
            intrinsics["aspect_ratio"],
            intrinsics["width"],
            intrinsics["height"],
            intrinsics["sensor_width"]
        ])
    
    logger.info(f"内参表导出完成 → {output_intrinsic_csv}")

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

    logger.info(f"外参矩阵导出完成 → {output_extrinsic_csv}")
    logger.info(f"Transform数据导出完成 → {output_transform_csv}")


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

    package_path, sequence_name = _split_ue_asset_path(sequence_path)
    
    # 获取相机配置
    camera_config = manifest.get("camera_export", {})
    
    # 确定输出目录
    output_dir = camera_config.get("output_path") or camera_config.get("export_path")
    if not output_dir:
        # 从sequence路径自动计算：output/场景名/序列名
        # 从manifest读取ue_config
        ue_config = manifest.get("ue_config", {})
        output_base = ue_config.get("output_base_dir", "output")
        
        # Handle "default" value - use project root's output folder
        if output_base == "default":
            script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            output_base = os.path.join(script_dir, "output")
            logger.info(f"[ExportCamera] Using default output directory: {output_base}")
        elif not output_base or output_base == "output":
            logger.warning("[ExportCamera] No output_base_dir in manifest.ue_config, using default 'output'")
        
        # 从sequence路径提取场景名（倒数第三个部分）
        # /Game/SecretBase/Levelsequence/SecretBase_003 -> SecretBase
        path_parts = package_path.rstrip('/').split('/')
        if len(path_parts) >= 3:
            scene_name = path_parts[-3]  # 取 /Game/[SecretBase]/Levelsequence/SecretBase_003
        else:
            # 如果路径太短，从序列名提取场景名（去除后缀数字）
            import re
            scene_name = re.sub(r'_\d+$', '', sequence_name)
        
        # 构建输出路径：output/场景名/序列名
        output_dir = os.path.join(output_base, scene_name, sequence_name)
    
    output_dir = os.path.normpath(output_dir)
    
    binding_camera = camera_config.get("binding_camera") or camera_config.get("binding_transform")
    if not binding_camera:
        raise ValueError("No camera binding specified in manifest")
    
    # 获取蓝图路径（用于读取相机内参）
    actor_blueprint_path = None
    sequence_config = manifest.get("sequence_config", {})
    if sequence_config:
        actor_blueprint_path = sequence_config.get("actor_blueprint_class_path")
    
    if actor_blueprint_path:
        logger.info(f"[ExportCamera] Blueprint path: {actor_blueprint_path}")
    else:
        logger.warning("[ExportCamera] No actor_blueprint_class_path in manifest, will use default intrinsics")
    
    logger.info(f"[ExportCamera] Output directory: {output_dir}")
    
    export_camera_data(package_path, binding_camera, output_dir, actor_blueprint_path)
    
    return {
        "status": "success",
        "sequence": package_path,
        "output_dir": output_dir,
        "extrinsic_csv": os.path.normpath(os.path.join(output_dir, f"{sequence_name}_extrinsic.csv")),
        "transform_csv": os.path.normpath(os.path.join(output_dir, f"{sequence_name}_transform.csv")),
        "intrinsic_csv": os.path.normpath(os.path.join(output_dir, f"{sequence_name}_intrinsic.csv"))
    }


if __name__ == "__main__":
    logger.error("This script should be called through export_camera_from_manifest() with a job manifest")
    logger.error("Example: python -c \"import export_UE_camera; export_UE_camera.export_camera_from_manifest(manifest)\"")
