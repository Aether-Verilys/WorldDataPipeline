# NavMesh 添加方案设计文档

## 设计理念

### 核心思想：**水平优先，垂直分离，地形优先**

大多数场景是基于水平面的，因此采用以下策略：

1. **先计算 XY 轴**（水平面边界）
   - 从所有可导航几何体计算 XY 平面的边界
   - 包括建筑、道具等 StaticMesh

2. **再计算 Z 轴**（垂直边界）
   - Z_min: Landscape 地面高度（如果存在）**优先**
   - Z_max: 几何体最高点 + Agent 跳跃高度

3. **Landscape 必须被包含**
   - Landscape 是地面，**必须**作为 Z_min 基准
   - 即使其他几何体更低，也强制对齐到 Landscape

## 简化后的函数列表

### 核心函数（保留）

1. **load_map()** - 加载地图
2. **check_navmesh_exists()** - 检查 NavMesh 是否已存在
3. **add_navmesh_bounds_volume()** - 添加 NavMeshBoundsVolume
4. **wait_for_navmesh_build()** - 等待 NavMesh 构建完成
5. **verify_navmesh_data()** - 验证 NavMesh 数据
6. **enable_landscape_navigation()** - 启用 Landscape 导航
7. **calculate_map_bounds()** - 计算地图边界（XY 优先，Z 分离）
8. **calculate_navmesh_scale()** - 计算 NavMesh 缩放
9. **auto_scale_navmesh()** - 自动缩放 NavMesh（主方案）
10. **batch_add_navmesh_to_maps()** - 批量添加

### 已删除函数（过于复杂）

1. ~~configure_navmesh_settings()~~ - 很少使用
2. ~~rebuild_navmesh()~~ - 已过时，UE 5.7+ 自动构建
3. ~~sample_navmesh_coverage()~~ - 复杂的采样优化
4. ~~find_largest_connected_region()~~ - 连通区域分析
5. ~~calculate_bounds_from_points()~~ - 从点计算边界
6. ~~adaptive_navmesh_optimization()~~ - 迭代优化方案（过度工程）

## 新的 calculate_map_bounds() 设计

### 工作流程

```
[Phase 1] 检测 Landscape（地面）
  → 找到所有 Landscape actors
  → 记录最低 Z 值作为 landscape_z_min
  → Landscape 优先级最高

[Phase 2] 检测场景边界参考
  → 查找 PostProcessVolume/LightmassImportanceVolume
  → 用作过滤超大 actor 的阈值

[Phase 3] 计算 XY 边界（水平面）
  → 遍历所有可导航 actors
  → 计算 XY 平面的 min/max
  → 同时记录几何体的 Z 范围（用于后续）

[Phase 4] 计算 Z 边界（垂直）
  → 如果有 Landscape：
      Z_min = landscape_z_min - 10cm *** 强制对齐 ***
  → 如果没有 Landscape：
      Z_min = geometry_z_min - agent_max_step_height
  → Z_max = geometry_z_max + agent_max_jump_height

[Phase 5] 计算最终中心和范围
  → center = (min + max) / 2
  → extent = (max - min) / 2
```

### 关键改进点

1. **XY 和 Z 分离计算**
   - XY：水平范围，所有几何体共同决定
   - Z：垂直范围，Landscape 优先

2. **Landscape 优先级最高**
   ```python
   if landscape_z_min is not None:
       min_z = landscape_z_min - 10.0  # 强制对齐
   else:
       min_z = geometry_z_min - agent_max_step_height
   ```

3. **清晰的日志输出**
   - 分阶段输出，便于调试
   - 明确标注 Landscape 优先级

## auto_scale_navmesh() 简化

### 删除前（复杂）

- 根据场景面积分为 Small/Medium/Large 三种策略
- 每种策略有不同的 Volume 布局
- 有多余的 if-elif-else 分支

### 简化后（通用）

```python
def auto_scale_navmesh():
    # Step 1: 启用 Landscape 导航
    enable_landscape_navigation()
    
    # Step 2: 计算边界（XY 优先，Z 分离）
    center, extent, landscape_z_min = calculate_map_bounds()
    
    # Step 3: 计算缩放
    scale = calculate_navmesh_scale(extent, margin, min_scale, max_scale)
    
    # Step 4: 创建单个 NavMeshBoundsVolume
    navmesh = add_navmesh_bounds_volume(center, scale)
    
    return navmesh
```

**优点：**
- 单一、通用的方案
- 适用于所有场景类型和大小
- 代码简洁，易于维护

## 地形支持

### 支持的地形类型

1. **Landscape**（地形/地面）
   - 自动检测
   - 强制作为 Z_min 基准
   - 启用导航碰撞

2. **StaticMesh**（建筑、道具等）
   - 自动包含在边界计算中
   - 过滤超大装饰性物体

3. **混合场景**
   - Landscape + StaticMesh
   - Landscape 优先级始终最高

### 不支持的物体（自动过滤）

- Sky/Atmosphere 相关
- Light actors
- PostProcessVolume
- Camera actors
- Trigger volumes
- Audio volumes

## 使用示例

### 单个地图

```python
manager = NavMeshManager()

# 加载地图
manager.load_map('/Game/Maps/YourMap')

# 自动添加 NavMesh
navmesh = manager.auto_scale_navmesh(
    margin=1.2,                    # 20% 边界扩展
    min_scale=[20, 20, 5],         # 最小缩放限制
    max_scale=[500, 500, 50],      # 最大缩放限制
    agent_max_step_height=50.0,    # 50cm
    agent_max_jump_height=200.0    # 200cm
)

# 等待构建
manager.wait_for_navmesh_build(timeout_seconds=120)

# 验证
if manager.verify_navmesh_data():
    print("NavMesh 添加成功！")
```

### 批量处理

```python
manager = NavMeshManager()

map_list = [
    '/Game/Maps/Level01',
    '/Game/Maps/Level02',
    '/Game/Maps/Level03',
]

results = manager.batch_add_navmesh_to_maps(
    map_list,
    location=None,  # 自动计算
    scale=None      # 自动计算
)

print(f"成功: {results['success']}/{results['total']}")
```

## 参数说明

### agent_max_step_height
- 默认: 50.0 cm
- 含义: Agent 可以向下走的最大高度差
- 影响: Z_min 扩展范围

### agent_max_jump_height
- 默认: 200.0 cm
- 含义: Agent 可以跳跃的最大高度
- 影响: Z_max 扩展范围

### margin
- 默认: 1.2 (20% 扩展)
- 含义: NavMesh 边界相对几何体的扩展比例
- 影响: XYZ 三个方向的 extent

### min_scale / max_scale
- 默认 min: [20, 20, 5]
- 默认 max: [500, 500, 50]
- 含义: NavMeshBoundsVolume 的缩放限制
- 用途: 防止过小或过大的 Volume

## 设计优势

### 1. 简单通用
- 单一方案适用所有场景
- 无需手动选择策略

### 2. Landscape 优先
- 自动检测地形
- 确保地面始终被包含

### 3. 水平优先
- 符合场景大多是水平面的特点
- XY 和 Z 分离计算，逻辑清晰

### 4. 易于维护
- 删除了 700+ 行复杂代码
- 核心逻辑集中在少数几个函数

### 5. 可扩展
- 保留了必要的接口
- 如需高级功能可在此基础上扩展

## 后续优化方向（可选）

如果需要处理超大场景（> 1000 m²），可考虑：

1. **空间分割（Spatial Partitioning）**
   - 将大场景分割为多个小区域
   - 每个区域一个 NavMeshBoundsVolume

2. **八叉树布局（Octree Layout）**
   - 自适应分割
   - 根据几何密度调整

3. **迭代优化（Adaptive Optimization）**
   - 先大后小的收缩策略
   - 基于实际 NavMesh 生成结果调整

但对于大多数场景，当前的简单方案已足够。
