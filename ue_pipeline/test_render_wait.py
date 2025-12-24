#!/usr/bin/env python3
"""
测试脚本：演示MRQ渲染等待机制
模拟渲染过程和状态文件更新
"""
import json
import os
import time
from pathlib import Path


def simulate_render_process():
    """模拟MRQ渲染进程行为"""
    
    # 模拟输出目录
    output_dir = Path("./test_render_output/S0001/Lvl_FirstPerson/Lvl_FirstPerson_001")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    status_file = output_dir / ".render_status.json"
    
    print("=" * 50)
    print("模拟MRQ渲染进程")
    print("=" * 50)
    print()
    
    # 1. 创建初始状态文件
    print("1. 创建状态文件 (status: rendering)...")
    status_data = {
        "status": "rendering",
        "sequence": "/Game/CameraController/Generated/Lvl_FirstPerson_001",
        "job_name": "TestRenderJob",
        "output_directory": str(output_dir),
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    with open(status_file, 'w', encoding='utf-8') as f:
        json.dump(status_data, f, indent=2)
    
    print(f"   状态文件已创建: {status_file}")
    print()
    
    # 2. 模拟渲染帧生成
    print("2. 模拟渲染帧生成...")
    total_frames = 300
    
    for i in range(1, total_frames + 1):
        # 创建假的帧文件
        frame_file = output_dir / f"frame_{i:04d}.png"
        frame_file.touch()
        
        if i % 50 == 0:
            print(f"   渲染进度: {i}/{total_frames} 帧")
            time.sleep(1)  # 模拟渲染耗时
    
    print(f"   ✓ 完成渲染 {total_frames} 帧")
    print()
    
    # 3. 更新状态为完成
    print("3. 更新状态文件 (status: completed)...")
    time.sleep(2)  # 模拟最终处理时间
    
    status_data["status"] = "completed"
    status_data["success"] = True
    status_data["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    with open(status_file, 'w', encoding='utf-8') as f:
        json.dump(status_data, f, indent=2)
    
    print(f"   状态文件已更新为 'completed'")
    print()
    
    print("=" * 50)
    print("模拟渲染完成")
    print("=" * 50)


def test_wait_mechanism():
    """测试等待机制"""
    
    print("\n" + "=" * 50)
    print("测试等待机制")
    print("=" * 50)
    print()
    
    output_dir = Path("./test_render_output/S0001/Lvl_FirstPerson/Lvl_FirstPerson_001")
    status_file = output_dir / ".render_status.json"
    
    start_time = time.time()
    check_interval = 2  # 每2秒检查一次
    last_frame_count = 0
    
    print(f"监控状态文件: {status_file}")
    print()
    
    while True:
        elapsed = time.time() - start_time
        
        # 检查状态文件
        if status_file.exists():
            with open(status_file, 'r', encoding='utf-8') as f:
                status_data = json.load(f)
            
            current_status = status_data.get('status')
            print(f"[{elapsed:.1f}s] 状态: {current_status}")
            
            if current_status == 'completed':
                success = status_data.get('success', False)
                if success:
                    print()
                    print("✓ 渲染完成，可以开始后处理")
                    break
        
        # 备用：检查帧文件
        if output_dir.exists():
            frame_files = [f for f in output_dir.iterdir() if f.suffix == '.png']
            current_frame_count = len(frame_files)
            
            if current_frame_count > last_frame_count:
                print(f"[{elapsed:.1f}s] 进度: {current_frame_count} 帧已渲染")
                last_frame_count = current_frame_count
        
        time.sleep(check_interval)
    
    print()
    print("=" * 50)
    print("等待机制测试完成")
    print("=" * 50)


if __name__ == "__main__":
    import sys
    import threading
    
    # 清理旧的测试输出
    import shutil
    test_dir = Path("./test_render_output")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    
    print("\n\n")
    print("╔" + "=" * 60 + "╗")
    print("║  MRQ渲染等待机制测试                                         ║")
    print("╚" + "=" * 60 + "╝")
    print()
    
    # 在后台线程中启动模拟渲染进程
    render_thread = threading.Thread(target=simulate_render_process)
    render_thread.daemon = True
    render_thread.start()
    
    # 等待一小段时间让渲染进程启动
    time.sleep(1)
    
    # 测试等待机制
    test_wait_mechanism()
    
    # 清理
    print()
    print("清理测试文件...")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    print("✓ 清理完成")
