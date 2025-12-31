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
- `ue_pipeline/bos_manager.py`
- `ue_pipeline/python/pre_copy/copy_scene_assets_wrapper.py`

---

### Step 2: NavMesh自适应烘焙
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

## 后续优化方向

### Week 2+
- **质量提升**: 相机轨迹评分系统、碰撞检测
- **性能优化**: GPU利用率profiling、渲染参数调优
- **扩展性**: Kubernetes部署、自动伸缩Worker
- **数据增强**: 天气/光照变化、镜头运动多样性

### 长期
- **分布式调度**: 集成Deadline / RenderMan for UE
- **监控Dashboard**: Grafana可视化任务进度、集群状态
- **数据标注**: 自动生成camera pose、depth map等标注数据

---
