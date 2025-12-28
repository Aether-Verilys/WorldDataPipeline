# WorldDataPipeline

## 项目目标

生成500小时世界模型训练数据（15,000个2分钟视频片段），通过自动化管线实现：
- 自适应场景处理（NavMesh根据地图大小动态调整）
- 智能相机轨迹生成（基于NavMesh随机起点）
- 分布式渲染（Linux集群 + Docker + Redis）
- 动态资源管理（BOS按需下载/上传，避免磁盘过载）

---

## 架构设计

### 核心设计原则：单场景作业流 + 分布式渲染

**流程分离：**
```
[Windows控制节点]                    [Linux渲染集群]
    ↓                                      ↓
BOS下载场景 ──→ NavMesh烘焙          Docker容器(UE 5.7)
    ↓                                      ↓
生成LevelSequence ──→ 推送到Redis  ←── Worker拉取任务
    ↓                                      ↓
上传序列到BOS              渲染序列帧 → 转视频 → 上传BOS
```

### 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| **控制节点** | Windows 11/ Linux + Python 3.1x | 场景管理、序列生成、任务调度 |
| **渲染集群** | Linux + Docker + UE 5.7 | 分布式MRQ渲染 |
| **任务队列** | Redis | 渲染任务分发与状态同步 |
| **存储** | BOS (BaiduCloud Object Storage) | 场景资产、序列文件、视频输出 |
| **编码** | FFmpeg | 序列帧合成视频 |
| **监控** | Webhook + 日志 | 任务状态、失败告警 |

---

## 管线流程详解

### Step 1: 数据清洗
**输入：** BOS上的场景资产 (`bos://bucket/raw_scenes/Seaside_Town/`)  
**输出：** UE Content中的可用场景 上传到BOS Raw中

**流程：**
1. `bos_manager.py` 下载场景到本地缓存 `D:/UE_Cache/{scene_name}/`
2. `copy_scene_assets_wrapper.py` 复制.umap/.uasset到UE Content
3. 验证场景可加载，更新 `WorldData00_scenes_status.json`

**关键代码文件：**
- `ue_pipeline/bos_manager.py` (新建)
- `ue_pipeline/python/pre_copy/copy_scene_assets_wrapper.py` (修改)

---

### Step 2: NavMesh自适应烘焙 (Windows)
**输入：** UE场景地图路径  
**输出：** 带NavMeshBoundsVolume的场景 + 导航数据

**自适应策略（UE Headless模式执行）：**
1. 加载地图，遍历所有可导航组件：
   - 对每个组件检查：`comp.can_ever_affect_navigation() and comp.get_collision_enabled() != CollisionEnabled.NO_COLLISION`
   - 符合条件的StaticMeshActor/LandscapeComponent才纳入边界计算
2. 计算聚合AABB边界框（考虑Agent物理参数）：
   - XY: 所有可导航组件的 min/max XY
   - **ZMin**: 所有可导航组件的最小 Z - `AgentMaxStepHeight` (默认-50cm)
   - **ZMax**: 所有可导航组件的最大 Z + `AgentMaxJumpHeight` (默认+200cm)
   - 确保垂直空间覆盖Agent可达的所有高度层
3. **智能Volume布局策略**：
   - **小场景**（< 200m²）：单个NavMeshBoundsVolume覆盖全场景
   - **中等场景**（200-500m²）：按楼层/区域拆分2-4个Volume
   - **大场景**（> 500m²）：空间八叉树分割，每个Volume不超过250m²
   - **优势**：减少单次烘焙内存占用，支持并行烘焙，提升NavMesh精度
4. 自动设置每个Volume的scale = 子区域边界尺寸 × 1.2 (20%余量)
5. 限制范围：最小 `[20,20,5]`，最大 `[500,500,50]`（单个Volume）
6. 触发NavMesh重建 (`rebuild_navmesh()`)，支持多Volume并行烘焙
7. **等待NavMesh构建完成** (监控构建状态，Tile生成进度)
8. **保存场景文件** (`EditorLevelLibrary.save_current_level()`)
9. **严格验证NavMesh可用性**：
   - 检查 `NavigationSystemV1.GetMainNavData()` 是否存在
   - 验证 `NavData.GetNavMeshTilesCount() > 0`（确保已生成导航网格）
   - 测试随机点可达性（`GetRandomReachablePointInRadius()` 成功率 > 80%）
   - 评估可导航区域面积（需 > 场景面积的30%）

**重要：烘焙完成必须保存场景**
- NavMesh数据存储在 `.umap` 和对应的 `_BuiltData.uasset` 文件中
- 不保存则下次加载地图NavMesh丢失，导致轨迹生成失败
- 保存后上传到BOS，确保渲染节点可使用烘焙好的NavMesh

**执行方式（Headless模式）：**
```bash
# Windows控制节点执行（通过Python调用UE Cmd）
python ue_pipeline/run_bake_navmesh.py --map /Game/S0001/Scene01 --auto-scale

# 内部调用UE命令行：
UnrealEditor-Cmd.exe WorldData00.uproject \
  -run=pythonscript \
  -script=ue_pipeline/python/worker_bake_navmesh.py \
  -manifest=jobs/inbox/job_bake_001.json \
  -stdout -unattended -nothreading -NoLoadingScreen
```

**关键代码文件：**
- `ue_pipeline/python/pre_process/add_navmesh_to_scene.py`
- `ue_pipeline/python/worker_bake_navmesh.py` (添加 `auto_scale` 参数，Headless执行)
- `ue_pipeline/run_bake_navmesh.py` (Python CLI包装器)

**配置示例：**
```json
{
  "job_type": "bake_navmesh",
  "navmesh_config": {
    "auto_scale": true,
    "min_scale": [20, 20, 5],
    "max_scale": [500, 500, 50],
    "scale_margin": 1.2,
    "maps": ["/Game/S0001/Scene01.Scene01"]
  }
}
```

---

### Step 3: 相机轨迹生成 (Windows)
**输入：** 烘焙好的场景地图  
**输出：** LevelSequence资产 (`.uasset`)，包含完整的相机动画数据

**LevelSequence结构要求：**
1. **Actor Spawnable/Possessable**: 
   - 使用工程中的蓝图Character类（如 `/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter`）
   - Actor必须包含Camera Component（如 `FollowCamera` 或 `FirstPersonCamera`）
   - 可以是Spawnable（序列生成时创建）或Possessable（关卡中已存在的actor）
2. **Camera Cut Track**: 
   - 指定Camera Component作为视角源
   - 控制整个序列的相机切换（单镜头则只有一个cut）
3. **Transform Track**: 
   - 绑定到Actor的根组件或Camera Component
   - 记录每帧的Location和Rotation关键帧
   - 使用Linear或Auto插值实现平滑运动
4. **其他可选Track**: 
   - FOV Track（视野角度变化）
   - Focus Settings（景深/对焦）

**智能起点策略（确保在有效地面）：**
1. **优先级1**: 查找PlayerStart actor
   - 如果存在，验证其位置在NavMesh上（`ProjectPointToNavigation`）
   - 若不在NavMesh上，向下LineTrace投影到最近地面
2. **优先级2**: 查找TargetPoint actor（同样验证NavMesh）
3. **优先级3**: 从最优地面区域开始
   - **地面判定标准**：
     - 可导航面积最大（NavMesh Polygon面积总和）
     - 连通性最强（单个连通区域包含的导航点数量）
     - 高度变化平缓（Z轴方差 < 100cm²）
   - 在最优地面区域中随机采样起点（`get_random_reachable_point_in_radius`）
   - 确保起点在可导航地面上，高度合理（Z值在地面±100cm内）
4. **优先级4**: 若以上失败，从NavMesh的任意有效点开始随机采样
   - **不使用场景中心作为起点**（可能在空中或墙内）
   - 从场景边界内随机采样并投影到NavMesh
5. **验证**: 
   - LineTrace检测起点下方有地面（不在空中）
   - 检查起点周围有足够导航空间（半径>200cm可达区域）
   - 确保起点不在墙内或封闭空间

**轨迹生成逻辑：**
- 使用 `nav_roam` 配置进行多段随机漫游（`num_legs=6`）
- 每段在NavMesh上生成随机目标点（半径8000cm）
- PathFollowing生成平滑路径，插值关键帧（0.25秒间隔）
- Camera yaw自动计算朝向运动方向（`max_yaw_rate=60°/s`）

**路径合理性验证：**
1. **距离检测**：每段路径长度需 > `min_segment_step_cm` (默认75cm)，过短路径被拒绝
2. **可达性验证**：使用 `NavigationSystem.FindPathToLocationSynchronously()` 确保路径可导航
3. **卡住检测**：若连续40次（`max_random_point_tries`）无法找到合法目标点，判定为卡住
4. **自动重试**：检测到卡住时，自动更换seed（原seed+1000）重新生成，最多重试5次
5. **路径质量评估**：
   - 拒绝过于单调的直线路径（转角 < 15°）
   - 检测重复访问同一区域（距离历史点 < 500cm）
   - 验证路径覆盖度（分布在场景不同区域）

**外参矩阵导出：**
- 序列生成完成后，自动调用 `export_UE_camera.py` 导出相机外参矩阵表
- 输出格式：CSV文件，每帧一行包含：`frame_id, timestamp, location_x, location_y, location_z, rotation_pitch, rotation_yaw, rotation_roll, fov`
- 同时生成4x4变换矩阵（世界坐标系 → 相机坐标系）
- 上传到BOS：`bos://bucket/sequences/{scene_id}/{map_name}_seq_{id}_camera_extrinsics.csv`

**执行方式（Headless模式）：**
```bash
# Windows控制节点执行
python ue_pipeline/run_create_sequence_job.py \
  --map /Game/Seaside_Town/Maps/Demonstration \
  --num-sequences 5 \
  --seed-start 10000 \
  --actor-blueprint /Game/FirstPerson/Blueprints/BP_FirstPersonCharacter \
  --camera-component FollowCamera

# 内部调用UE命令行：
UnrealEditor-Cmd.exe WorldData00.uproject \
  -run=pythonscript \
  -script=ue_pipeline/python/worker_create_sequence.py \
  -manifest=jobs/inbox/job_create_seq_001.json \
  -stdout -unattended -nothreading
```

**序列生成核心逻辑：**
```python
# worker_create_sequence.py 关键步骤
# 1. 创建LevelSequence资产
sequence = create_level_sequence(output_dir, sequence_name)
movie_scene = sequence.get_movie_scene()

# 2. 生成或绑定Actor
if spawn_actor:
    # Spawnable模式：序列控制actor生命周期
    actor_binding = add_spawnable_actor(sequence, actor_blueprint_path)
else:
    # Possessable模式：绑定关卡中已有actor
    actor = find_actor_in_level(actor_name)
    actor_binding = add_possessable_actor(sequence, actor)

# 3. 添加Camera Cut Track
camera_component = actor.get_component_by_class(unreal.CameraComponent)
camera_cut_track = movie_scene.add_master_track(unreal.MovieSceneCameraCutTrack)
camera_cut_section = camera_cut_track.add_section()
camera_cut_section.set_camera_binding_id(camera_component_binding)

# 4. 添加Transform Track并写入关键帧
transform_track = actor_binding.add_track(unreal.MovieScene3DTransformTrack)
transform_section = transform_track.add_section()

for i, waypoint in enumerate(path_waypoints):
    time = i * key_interval_seconds
    # 写入Location关键帧
    transform_section.get_channel_by_type(unreal.MovieSceneScriptChannel.LOCATION_X).add_key(
        unreal.FrameNumber(time * fps), waypoint.location.x
    )
    # 写入Rotation关键帧
    transform_section.get_channel_by_type(unreal.MovieSceneScriptChannel.ROTATION_YAW).add_key(
        unreal.FrameNumber(time * fps), waypoint.rotation.yaw
    )

# 5. 保存序列
unreal.EditorAssetLibrary.save_asset(sequence.get_path_name())
```

**关键代码文件：**
- `ue_pipeline/python/worker_create_sequence.py` (增强 `_find_first_startpoint()`，添加路径验证和卡住重试，Headless执行)
- `ue_pipeline/python/gen_levelsequence.py` (核心库)
- `ue_pipeline/python/export_UE_camera.py` (外参矩阵导出，已存在，需集成到序列生成流程)
- `ue_pipeline/run_create_sequence_job.py` (Python CLI包装器，替代PS1脚本)

**配置示例：**
```json
{
  "job_type": "create_sequence",
  "map": "/Game/Seaside_Town/Maps/Demonstration.Demonstration",
  "sequence_config": {
    "output_dir": "/Game/CameraController/Generated",
    "sequence_count": 1,
    "fps": 30,
    "duration_seconds": 120,
    "actor_config": {
      "actor_blueprint_class_path": "/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter.BP_FirstPersonCharacter",
      "camera_component_name": "FollowCamera",
      "actor_binding_mode": "spawnable",  // spawnable | possessable
      "spawn_location": {"x": 0, "y": 0, "z": 0},
      "spawn_rotation": {"pitch": 0, "yaw": 0, "roll": 0}
    },
    "nav_roam": {
      "enabled": true,
      "startpoint_mode": "auto",
      "seed": 12345,
      "num_legs": 6,
      "random_point_radius_cm": 8000.0,
      "key_interval_seconds": 0.25,
      "min_segment_step_cm": 75.0,
      "max_random_point_tries": 40,
      "stuck_retry_max": 5,
      "seed_increment_on_retry": 1000,
      "path_validation": {
        "min_path_length_cm": 200.0,
        "min_turn_angle_deg": 15.0,
        "min_point_distance_cm": 500.0,
        "require_path_diversity": true
      }
    },
    "camera_cut": {
      "enabled": true,
      "single_shot": true  // 单镜头模式，整个序列使用同一camera
    },
    "export_camera_extrinsics": true
  }
}
```

**输出：** 
- LevelSequence文件保存到Content
- 上传到BOS: 
  - `bos://bucket/sequences/{scene_name}/{map_name}_seq_{id}.uasset` (序列文件)
  - `bos://bucket/sequences/{scene_name}/{map_name}_seq_{id}_camera_extrinsics.csv` (相机外参矩阵)
  - `bos://bucket/sequences/{scene_name}/{map_name}_seq_{id}_metadata.json` (元数据：seed、路径统计、生成时间)

---

### Step 4: 渲染任务调度 (Windows → Redis)
**输入：** 生成的LevelSequence列表  
**输出：** Redis队列中的渲染任务

**架构：**
```
Windows控制节点                    Redis Server           Linux渲染节点 (N台)
     |                                |                          |
     |-- 扫描生成的序列 ----------→   |                          |
     |-- 为每个序列创建任务 -------→  | LPUSH render_queue      |
     |                                |  ← BRPOP -------------- Worker 1
     |                                |  ← BRPOP -------------- Worker 2
     |                                |  ← BRPOP -------------- Worker N
     |                                |                          |
     |← 监控任务状态 (HGET) --------  | HSET task:{id} status   |
```

**任务数据结构（Redis Hash）：**
```json
{
  "task_id": "render_Seaside_Town_Demonstration_seq_001",
  "scene_bos_path": "bos://bucket/raw_scenes/Seaside_Town/",
  "sequence_bos_path": "bos://bucket/sequences/Seaside_Town/Demonstration_seq_001.uasset",
  "map_path": "/Game/Seaside_Town/Maps/Demonstration.Demonstration",
  "sequence_path": "/Game/CameraController/Generated/Demonstration_seq_001",
  "output_bos_path": "bos://bucket/output/{scene_name}/{map_name}/seq_{id}/",
  "render_config": {
    "fps": 30,
    "resolution": [1920, 1080],
    "quality_preset": "high",
    "format": "png"
  },
  "status": "pending",  // pending | processing | rendering | encoding | completed | failed
  "worker_id": null,
  "created_at": "2025-12-25T10:00:00Z",
  "started_at": null,
  "completed_at": null,
  "retry_count": 0,
  "error_message": null
}
```

**关键代码文件：**
- `ue_pipeline/task_dispatcher.py` (新建，扫描序列 → 推送Redis)
- `ue_pipeline/redis_client.py` (新建，Redis封装)

---

### Step 5: Linux集群渲染 (Docker + UE)
**环境：** Linux服务器 + NVIDIA GPU + Docker

**Docker容器配置：**
```dockerfile
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# 安装UE 5.7 + 依赖
RUN apt-get update && apt-get install -y \
    unzip wget python3 python3-pip ffmpeg \
    libgl1 libglu1 libxrandr2 libxi6

# 复制UE引擎（预编译）
COPY UnrealEngine-5.7/ /opt/UnrealEngine/

# Python依赖
COPY requirements.txt /app/
RUN pip3 install -r /app/requirements.txt

# 渲染Worker脚本
COPY ue_pipeline/ /app/ue_pipeline/
WORKDIR /app

ENTRYPOINT ["python3", "ue_pipeline/linux/render_worker.py"]
```

**Worker流程 (`render_worker.py` 新建):**
```python
while True:
    # 1. 从Redis拉取任务
    task = redis.brpop('render_queue', timeout=60)
    if not task:
        continue
    
    task_data = json.loads(task[1])
    task_id = task_data['task_id']
    redis.hset(f'task:{task_id}', 'status', 'processing')
    
    try:
        # 2. 下载场景和序列从BOS
        download_scene(task_data['scene_bos_path'])
        download_sequence(task_data['sequence_bos_path'])
        
        # 3. 启动UE Headless渲染
        cmd = [
            '/opt/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd',
            '/app/WorldData00/WorldData00.uproject',
            '-game', '-MoviePipelineConfig=...', '-NoLoadingScreen',
            '-unattended', '-nothreading', '-StdOut', '-FullStdOutLogOutput'
        ]
        subprocess.run(cmd, check=True)
        
        # 4. FFmpeg合成视频
        convert_frames_to_video(output_dir, f'{task_id}.mp4')
        
        # 5. 上传视频到BOS
        upload_to_bos(f'{task_id}.mp4', task_data['output_bos_path'])
        
        # 6. 更新状态
        redis.hset(f'task:{task_id}', 'status', 'completed')
        
        # 7. 清理本地文件
        cleanup_temp_files()
        
    except Exception as e:
        redis.hset(f'task:{task_id}', 'status', 'failed')
        redis.hset(f'task:{task_id}', 'error_message', str(e))
        # 重试逻辑
        if task_data['retry_count'] < 3:
            task_data['retry_count'] += 1
            redis.lpush('render_queue', json.dumps(task_data))
```

**关键代码文件：**
- `ue_pipeline/linux/render_worker.py` (新建)
- `ue_pipeline/linux/Dockerfile` (新建)
- `ue_pipeline/linux/run_render_job_headless.sh` (修改，适配Docker环境)

**部署命令：**
```bash
# 构建镜像
docker build -t ue-render-worker:5.7 -f ue_pipeline/linux/Dockerfile .

# 启动Worker (每台GPU机器运行1个容器)
docker run --gpus all \
  -e REDIS_HOST=192.168.1.100 \
  -e REDIS_PORT=6379 \
  -e BOS_AK=xxx \
  -e BOS_SK=xxx \
  -v /mnt/cache:/tmp/ue_cache \
  ue-render-worker:5.7
```

---

### Step 6: 视频合成与上传 (Linux Worker内部)
**输入：** 序列帧目录（PNG/EXR）  
**输出：** MP4视频

**FFmpeg配置：**
```python
# ue_pipeline/convert_frames_to_video.py (已存在)
ffmpeg_cmd = [
    'ffmpeg', '-y',
    '-framerate', str(fps),
    '-i', f'{frame_dir}/Frame_%05d.png',
    '-c:v', 'libx264',
    '-preset', 'medium',
    '-crf', '18',  # 高质量
    '-pix_fmt', 'yuv420p',
    output_video
]
```

**上传BOS：**
- 路径：`bos://bucket/world_model_data/{scene_name}/{map_name}/seq_{id}.mp4`
- 元数据：同时上传 `seq_{id}_metadata.json` 包含fps、分辨率、帧数、文件大小

**清理策略：**
- 序列帧：上传视频后立即删除（节省磁盘）
- 场景缓存：LRU策略，容器磁盘<100GB时清理
- 日志：保留7天

---

## 3天开发计划

### Day 1: 自适应场景处理 + 序列生成完整流程 (Windows)

**目标：** 单场景从BOS下载 → NavMesh烘焙 → 序列生成 → 上传BOS

#### Tasks:

**1. NavMesh自适应系统** (4小时)
- 修改 `ue_pipeline/python/pre_process/add_navmesh_to_scene.py`
  - 新增 `calculate_map_bounds()` 方法
  - 支持 `auto_scale=True` 参数
  - 添加边界验证与限制
  - **实现NavMesh构建完成等待逻辑**
  - **确保场景保存成功**（验证文件修改时间）
- 新建 `ue_pipeline/run_bake_navmesh.py` (Python CLI，替代PS1脚本)
  - 解析命令行参数
  - 生成job manifest JSON
  - 调用UE Cmd模式执行worker脚本
  - 监控进程输出，解析成功/失败状态

**2. 智能起点生成与路径验证** (4小时)
- 修改 `ue_pipeline/python/worker_create_sequence.py`
  - 增强 `_find_first_startpoint()` 支持fallback策略
  - **重点修改起点验证逻辑**：
    - 使用 `ProjectPointToNavigation()` 确保起点在NavMesh上
    - LineTrace向下检测地面距离（Z轴偏移 < 100cm）
    - 避免使用场景中心（可能在空中/墙内）
    - 验证起点周围有足够导航空间（200cm半径可达）
  - 新增 `startpoint_mode: auto` 配置
  - **新增路径合理性检测**：
    - 实现 `validate_path_segment()` 检测路径长度、转角、重复区域
    - 实现 `detect_stuck_and_retry()` 检测卡住并自动更换seed重试
    - 添加路径质量评分（多样性、覆盖度）
  - **集成外参导出**：调用 `export_UE_camera.py` 生成CSV
- 新建 `ue_pipeline/run_create_sequence_job.py` (Python CLI，替代PS1脚本)
  - 批量生成多个序列（不同seed）
  - Headless模式调用UE
  - 解析执行结果

**3. 单场景流程编排器** (5小时)
- 新建 `ue_pipeline/run_single_scene_pipeline.py`
  - 串联：验证场景 → 烘焙 → 生成序列（多个seed）
  - 支持 `--num-sequences N` 参数
  - 错误处理与日志记录

**4. 状态持久化** (2小时)
- 修改 `ue_pipeline/scenes/WorldData00_scenes_status.json` schema
  - 统一格式：scene → maps → sequences结构
  - 添加写入锁避免并发冲突

**5. BOS上传序列文件** (2小时)
- 新建 `ue_pipeline/bos_manager.py` (基础版)
  - 实现 `upload_sequence()` 方法
  - 集成 `bce-python-sdk`

**Deliverable:** 
```bash
python run_single_scene_pipeline.py \
  --scene-name Seaside_Town \
  --map-path /Game/Seaside_Town/Maps/Demonstration \
  --num-sequences 3 \
  --upload-bos
```
输出：3个LevelSequence上传到BOS，本地status.json更新

---

### Day 2: Redis任务队列 + Docker渲染环境 (Linux)

**目标：** Linux集群从Redis拉取任务，在Docker中完成渲染

#### Tasks:

**1. Redis任务系统** (4小时)
- 新建 `ue_pipeline/redis_client.py`
  - 封装Redis连接、任务CRUD操作
  - 实现任务状态机（pending → processing → completed/failed）
- 新建 `ue_pipeline/task_dispatcher.py`
  - 扫描BOS上传的序列文件
  - 为每个序列创建渲染任务推送Redis

**2. Docker渲染环境** (5小时)
- 新建 `ue_pipeline/linux/Dockerfile`
  - 基于 `nvidia/cuda:11.8.0`
  - 安装UE 5.7 + Python + FFmpeg
  - 复制worker脚本和UE工程模板
- 测试本地构建与GPU访问

**3. Linux渲染Worker** (6小时)
- 新建 `ue_pipeline/linux/render_worker.py`
  - Redis任务拉取循环
  - BOS下载场景+序列
  - 调用UE Headless渲染（复用 `run_render_job_headless.py` 逻辑）
  - FFmpeg转视频
  - 上传BOS + 更新Redis状态
  - 清理临时文件

**4. 监控与重试** (3小时)
- 修改 `ue_pipeline/monitor_render.py`
  - 集成Redis状态监控
  - 检测卡住任务（processing超过30分钟）
  - 自动重试失败任务（最多3次）

**Deliverable:**
```bash
# Windows控制节点
python task_dispatcher.py --scan-bos

# Linux渲染节点
docker run --gpus all -e REDIS_HOST=x.x.x.x ue-render-worker:5.7
```
成功渲染1个序列，视频上传BOS，Redis状态 = completed

---

### Day 3: 批量处理 + 生产优化

**目标：** 端到端处理10个场景，验证500小时数据生成能力

#### Tasks:

**1. BOS场景下载** (3小时)
- 完善 `ue_pipeline/bos_manager.py`
  - 实现 `download_scene()` 断点续传
  - MD5校验
  - 本地LRU缓存管理

**2. 批量作业生成器** (3小时)
- 新建 `ue_pipeline/batch_generate_jobs.py`
  - 读取 `ue_config.json` 所有场景
  - 循环调用 `run_single_scene_pipeline.py`
  - 支持 `--scenes-per-batch 10` 参数

**3. 分布式协调** (4小时)
- 新建 `ue_pipeline/cluster_manager.py`
  - 检测Redis队列长度
  - 监控Worker健康状态（心跳）
  - 动态调整任务优先级

**4. 性能测试** (3小时)
- 端到端测试：处理10个真实场景
  - 测量：单序列渲染时间、磁盘占用、GPU利用率
  - 计算：达成15,000序列所需时间
  - 生成报告：`performance_report.json`

**5. 清理与文档** (3小时)
- 新建 `ue_pipeline/cleanup_scenes.py`
  - 删除已上传场景的本地缓存
  - 磁盘空间监控
- 新建 `ue_pipeline/docs/deployment_guide.md`
  - 环境搭建步骤
  - Redis/BOS配置
  - Docker部署命令
  - 监控dashboard配置

**Deliverable:**
- 成功处理10个场景（每个5序列 = 50个视频）
- 性能报告显示单序列渲染时间 ≤ 10分钟
- 估算：15,000序列需要 X 小时，需要 Y 台GPU服务器

---

## 技术细节与配置

### UE Headless执行模式

**所有UE操作通过Python在Cmd模式执行：**
```python
# 示例：Python调用UE Headless执行脚本
import subprocess

def run_ue_python_script(script_path, manifest_path):
    cmd = [
        "D:/UE_5.7/Engine/Binaries/Win64/UnrealEditor-Cmd.exe",
        "D:/WorldDataPipeline/ue_template/WorldData00/WorldData00.uproject",
        "-run=pythonscript",
        f"-script={script_path}",
        f"-manifest={manifest_path}",
        "-stdout",
        "-unattended",
        "-nothreading",
        "-NoLoadingScreen"
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=3600  # 1小时超时
    )
    
    return result.returncode == 0, result.stdout, result.stderr
```

**NavMesh场景保存关键点：**
- 烘焙后必须调用 `unreal.EditorLevelLibrary.save_current_level()` 保存
- NavMesh数据存储在2个文件：
  - `.umap` (主场景文件)
  - `_BuiltData.uasset` (导航网格数据)
- 保存成功验证：检查文件修改时间 > 执行开始时间
- **上传到BOS时需要同时上传两个文件**，否则渲染节点NavMesh缺失

**PlayerStart位置验证（避免空中/墙内）：**
```python
def validate_startpoint_on_navmesh(location):
    nav_sys = unreal.NavigationSystemV1.get_navigation_system(world)
    
    # 投影到NavMesh
    projected = nav_sys.project_point_to_navigation(world, location)
    if not projected:
        return False, "Not on NavMesh"
    
    # LineTrace检测下方是否有地面
    start = location
    end = location + unreal.Vector(0, 0, -500)  # 向下500cm
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end,
        unreal.TraceTypeQuery.VISIBILITY,
        False, [], unreal.DrawDebugTrace.NONE, True
    )
    
    if not hit:
        return False, "No ground below"
    
    # 检查高度差
    z_diff = abs(location.z - hit.location.z)
    if z_diff > 100:  # 超过1m视为悬空
        return False, f"Too high above ground: {z_diff}cm"
    
    return True, projected
```

### Redis Schema

**队列：**
- `render_queue` (List): 待渲染任务队列
- `failed_queue` (List): 失败任务队列（人工审查）

**任务数据：**
- `task:{task_id}` (Hash): 任务详情
  - `status`, `worker_id`, `created_at`, `error_message`, etc.

**Worker心跳：**
- `worker:{worker_id}:heartbeat` (String, TTL=60s): 最后活跃时间

**统计：**
- `stats:total_tasks` (Counter)
- `stats:completed_tasks` (Counter)
- `stats:failed_tasks` (Counter)

### BOS目录结构

```
bos://worldmodel-bucket/
├── raw_scenes/              # 原始场景资产
│   ├── Seaside_Town/
│   │   ├── Maps/
│   │   │   ├── Demonstration.umap
│   │   │   └── Demonstration_BuiltData.uasset
│   │   └── Content/
│   └── ModularScifiStation/
├── sequences/               # 生成的LevelSequence + 外参矩阵
│   ├── Seaside_Town/
│   │   ├── Demonstration_seq_001.uasset
│   │   ├── Demonstration_seq_001_camera_extrinsics.csv
│   │   ├── Demonstration_seq_001_metadata.json
│   │   ├── Demonstration_seq_002.uasset
│   │   └── Demonstration_seq_002_camera_extrinsics.csv
│   └── ModularScifiStation/
├── world_model_data/        # 最终视频输出
│   ├── Seaside_Town/
│   │   ├── Demonstration/
│   │   │   ├── seq_001.mp4
│   │   │   ├── seq_001_metadata.json
│   │   │   └── seq_002.mp4
│   │   └── Overview/
│   └── ModularScifiStation/
└── logs/                    # 任务日志归档
    └── 2025-12-25/
```

### 配置文件示例

**`ue_config.json` (扩展):**
```json
{
  "ue_project_path": "D:/WorldDataPipeline/ue_template/WorldData00/WorldData00.uproject",
  "ue_editor_path": "D:/UE_5.7/Engine/Binaries/Win64/UnrealEditor-Cmd.exe",
  "default_actor_blueprint": "/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter.BP_FirstPersonCharacter",
  "default_camera_component": "FollowCamera",
  "scenes": [
    {
      "scene_name": "Seaside_Town",
      "bos_path": "bos://bucket/raw_scenes/Seaside_Town/",
      "maps": [
        {
          "name": "Demonstration",
          "path": "/Game/Seaside_Town/Maps/Demonstration.Demonstration",
          "sequences_per_map": 5,
          "navmesh": {"auto_scale": true},
          "actor_config": {
            "blueprint_class": "/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter.BP_FirstPersonCharacter",
            "camera_component": "FollowCamera"
          },
          "render_config": {
            "resolution": [1920, 1080],
            "fps": 30,
            "duration_seconds": 120
          }
        },
        {
          "name": "Overview",
          "path": "/Game/Seaside_Town/Maps/Overview.Overview",
          "sequences_per_map": 3
        }
      ]
    }
  ],
  "redis": {
    "host": "192.168.1.100",
    "port": 6379,
    "db": 0
  },
  "bos": {
    "endpoint": "bj.bcebos.com",
    "bucket": "worldmodel-bucket"
  }
}
```

---

## 监控与告警

### 关键指标

| 指标 | 阈值 | 告警 |
|------|------|------|
| Redis队列长度 | > 1000 | Worker不足，需扩容 |
| 任务失败率 | > 10% | 配置问题或集群不稳定 |
| 磁盘使用率 | > 90% | 触发自动清理 |
| GPU温度 | > 85°C | 散热问题 |
| 单任务渲染时间 | > 20分钟 | 性能瓶颈或卡住 |

### Webhook告警

```python
# ue_pipeline/monitor_render.py
def send_alert(title, message):
    webhook_url = config['monitor']['webhook_url']
    payload = {
        "msgtype": "text",
        "text": {"content": f"[UE Pipeline] {title}\n{message}"}
    }
    requests.post(webhook_url, json=payload)

# 使用场景
if disk_usage > 0.9:
    send_alert("磁盘告警", f"磁盘使用率 {disk_usage*100}%，请及时清理")
```

---

## 风险与应对

### 高风险项

**1. UE Headless在Docker中的稳定性**
- **风险**: UE可能因内存泄漏/GPU驱动问题在长时间运行时崩溃
- **应对**: 
  - Worker每渲染10个序列自动重启容器
  - 设置任务超时（30分钟），超时kill进程
  - 增加swap分区（32GB）缓解内存压力

**2. Redis单点故障**
- **风险**: Redis挂了，整个任务队列丢失
- **应对**:
  - 启用Redis持久化（AOF模式）
  - 定期备份任务列表到BOS
  - 考虑Redis Cluster（如果规模>10台Worker）

**3. BOS带宽瓶颈**
- **风险**: 上传15,000个视频（~7.5TB）可能需要数天
- **应对**:
  - 测量Day 3实际上传速度（MB/s）
  - 若瓶颈，考虑并行上传或多线程
  - 与BOS运维协调带宽扩容

### 中风险项

**4. NavMesh自动检测失败**
- **风险**: 某些特殊场景（空场景、纯程序化）边界检测异常
- **应对**: 
  - 预设10个场景手动配置bounds作为fallback
  - 添加边界合理性校验（长宽比、体积范围）

**5. 相机轨迹质量不佳**
- **风险**: 随机生成的路径可能boring（重复、墙角）
- **应对**:
  - Day 1测试多个seed，人工审查质量
  - Day 2可选实现起点评分系统
  - 收集反馈后迭代优化

---

## 成功标准

### Day 1
- ✅ 单场景完整流程跑通（S0001从烘焙到序列上传BOS）
- ✅ NavMesh自适应至少支持3种不同尺寸场景
- ✅ 生成的LevelSequence在UE中可正常播放

### Day 2
- ✅ Docker容器成功在Linux GPU机器渲染1个序列
- ✅ Redis任务队列正常工作（推送→拉取→更新状态）
- ✅ 视频质量验证（1920x1080, 30fps, 无黑帧/花屏）

### Day 3
- ✅ 端到端处理≥10个场景（50+视频）
- ✅ 性能报告生成，估算500小时数据所需资源
- ✅ 部署文档完整，其他团队成员可复现搭建

---

## 后续优化方向

### Week 2+
- **质量提升**: 相机轨迹评分系统、碰撞检测、美学筛选
- **性能优化**: GPU利用率profiling、渲染参数调优
- **扩展性**: Kubernetes部署、自动伸缩Worker
- **数据增强**: 天气/光照变化、镜头运动多样性

### 长期
- **分布式调度**: 集成Deadline / RenderMan for UE
- **监控Dashboard**: Grafana可视化任务进度、集群状态
- **数据标注**: 自动生成camera pose、depth map等标注数据

---

## 附录：关键文件清单

### 新建文件 (Day 1-3)
```
ue_pipeline/
├── run_single_scene_pipeline.py      # Day 1: 单场景编排器
├── bos_manager.py                    # Day 1-3: BOS SDK封装
├── redis_client.py                   # Day 2: Redis封装
├── task_dispatcher.py                # Day 2: 任务调度器
├── batch_generate_jobs.py            # Day 3: 批量作业生成
├── cluster_manager.py                # Day 3: 集群管理
├── cleanup_scenes.py                 # Day 3: 资源清理
├── linux/
│   ├── Dockerfile                    # Day 2: 渲染容器
│   ├── render_worker.py              # Day 2: Linux Worker
│   └── docker-compose.yml            # Day 2: 部署配置
└── docs/
    ├── deployment_guide.md           # Day 3: 部署文档
    └── performance_report.json       # Day 3: 性能测试报告
```

### 修改文件
```
ue_pipeline/
├── python/
│   ├── pre_process/
│   │   └── add_navmesh_to_scene.py   # Day 1: 添加auto_scale + NavMesh等待 + 保存验证
│   ├── pre_copy/
│   │   └── copy_scene_assets_wrapper.py  # Day 1: BOS集成
│   ├── worker_bake_navmesh.py        # Day 1: 支持auto_scale，Headless执行
│   ├── worker_create_sequence.py     # Day 1: 智能起点(NavMesh投影) + 路径验证 + 卡住重试 + 外参导出
│   └── worker_render.py              # Day 2: 适配Docker环境
├── run_bake_navmesh.py               # Day 1: Python CLI替代PS1 (batch_bake_all_navmesh.py重构)
├── run_create_sequence_job.py        # Day 1: Python CLI替代PS1 (已存在，需增强)
├── monitor_render.py                 # Day 2: Redis监控
├── config/
│   ├── ue_config.json                # Day 1-3: 添加Redis/BOS配置
│   └── monitor_config.json           # Day 2: Webhook配置
└── scenes/
    └── WorldData00_scenes_status.json # Day 1: 统一schema
```

---

**文档版本**: v1.0  
**创建日期**: 2025-12-25  
**作者**: WorldDataPipeline Team  
**预计完成**: 2025-12-28
