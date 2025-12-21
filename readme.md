# WorldModel-DataPipeline

## 项目简介

本项目是一个用于大规模生成世界模型（World Model）训练数据的自动化管线。
旨在解决海量 UE 场景素材的处理瓶颈，实现从 **Raw 资产导入 -> NavMesh 自动烘焙 -> 相机轨迹生成 -> 离线批量渲染** 的全无人值守流程。

## 环境依赖

OS: Windows 11 / Linux
Engine: Unreal Engine 5.7
Hardware:
GPU: -
Storage: NVMe SSD 用于缓存渲染序列帧
Python 3.x
FFmpeg

### 核心特性

* **分块管理**：自动将海量 Raw 场景按每 100 个一组分发到工程，避免单项目资源过载。
* **自动烘焙**：利用 Commandlet 批量构建 NavMesh，无需人工打开编辑器。
* **程序化生成**：基于 NavMesh 随机生成防穿模的相机轨迹（Level Sequence）。
* **Headless 渲染**：基于 Movie Render Queue (MRQ) 的命令行渲染。

### 数据要求

每个场景多个片段，一个片段2分钟

第一批数据：500小时

---

## 管线架构 (Pipeline Architecture)

    A -->|1. [Raw] 分发脚本 (Distribute)| B[UE Project (Content/Scenes)]
    B -->|2. Commandlet| C[NavMesh Baking]
    C -->|3. Python Script| D[Generate LevelSequences]
    D -->|4. MRQ Batch| E[Render Image Sequence]
    E -->|5. FFmpeg| F[MP4 Video & Upload]

## 目录结构

todo...

## TODO

集成 BOS/S3 云存储上传 SDK

支持多机分布式任务调度 (Deadline 集成)
