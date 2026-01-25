#!/usr/bin/env python3
"""
渲染进程监控脚本
监控 Unreal Engine 渲染作业的状态和进度
"""

import json
import time
import os
import sys
import psutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import argparse


class RenderMonitor:
    """渲染进程监控器"""
    
    def __init__(self, config_path: str):
        """初始化监控器"""
        self.config = self.load_config(config_path)
        self.setup_logging()
        self.running_jobs: Dict[str, Dict[str, Any]] = {}
        self.completed_jobs: List[str] = []
        self.failed_jobs: List[str] = []
        
    def load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def setup_logging(self):
        """设置日志"""
        log_file = self.config['monitor']['log_file']
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def scan_for_render_jobs(self) -> List[Path]:
        """扫描输出目录查找所有渲染状态文件"""
        output_base = self.config['rendering']['output_base_path']
        status_filename = self.config['rendering']['status_file_name']
        
        status_files = []
        if os.path.exists(output_base):
            for root, dirs, files in os.walk(output_base):
                if status_filename in files:
                    status_files.append(Path(root) / status_filename)
        
        return status_files
    
    def read_status_file(self, status_file: Path) -> Optional[Dict[str, Any]]:
        """读取状态文件"""
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"读取状态文件失败 {status_file}: {e}")
            return None
    
    def check_ue_process(self) -> List[psutil.Process]:
        """检查 UE 渲染进程"""
        process_name = self.config['rendering']['process_check']['process_name']
        ue_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'create_time']):
            try:
                if proc.info['name'] == process_name:
                    ue_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return ue_processes
    
    def get_output_frame_count(self, output_dir: str) -> int:
        """统计输出目录中的帧数"""
        if not os.path.exists(output_dir):
            return 0
        
        frame_files = [f for f in os.listdir(output_dir) 
                      if f.endswith('.png') or f.endswith('.jpg') or f.endswith('.exr')]
        return len(frame_files)
    
    def format_time_elapsed(self, start_time_str: str) -> str:
        """格式化已用时间"""
        try:
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            elapsed = datetime.now() - start_time
            hours = int(elapsed.total_seconds() // 3600)
            minutes = int((elapsed.total_seconds() % 3600) // 60)
            seconds = int(elapsed.total_seconds() % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except:
            return "未知"
    
    def check_disk_space(self, path: str) -> float:
        """检查磁盘剩余空间（GB）"""
        try:
            stat = psutil.disk_usage(path)
            return stat.free / (1024**3)
        except:
            return -1
    
    def update_job_status(self, status_file: Path, status_data: Dict[str, Any]):
        """更新作业状态"""
        job_name = status_data.get('job_name', 'Unknown')
        status = status_data.get('status', 'unknown')
        output_dir = status_data.get('output_directory', '')
        
        # 检查帧数
        frame_count = self.get_output_frame_count(output_dir) if output_dir else 0
        
        # 更新或添加到运行中的作业
        job_key = str(status_file)
        
        if status == 'rendering':
            if job_key not in self.running_jobs:
                self.running_jobs[job_key] = {
                    'name': job_name,
                    'status': status,
                    'output_dir': output_dir,
                    'start_time': status_data.get('start_time', ''),
                    'last_frame_count': frame_count,
                    'last_check_time': datetime.now(),
                    'sequence': status_data.get('sequence', '')
                }
                self.logger.info(f"🎬 检测到新渲染作业: {job_name}")
            else:
                # 更新现有作业
                job = self.running_jobs[job_key]
                previous_count = job['last_frame_count']
                job['last_frame_count'] = frame_count
                job['last_check_time'] = datetime.now()
                
                if frame_count > previous_count:
                    self.logger.info(f"📊 {job_name}: {frame_count} 帧 (+{frame_count - previous_count})")
        
        elif status == 'completed':
            if job_key in self.running_jobs:
                elapsed = self.format_time_elapsed(self.running_jobs[job_key]['start_time'])
                self.logger.info(f"✅ 作业完成: {job_name} - {frame_count} 帧，耗时 {elapsed}")
                del self.running_jobs[job_key]
                self.completed_jobs.append(job_name)
                self.send_notification(f"渲染完成: {job_name}", "success")
        
        elif status == 'failed':
            if job_key in self.running_jobs:
                self.logger.error(f"❌ 作业失败: {job_name}")
                del self.running_jobs[job_key]
                self.failed_jobs.append(job_name)
                self.send_notification(f"渲染失败: {job_name}", "error")
    
    def check_stalled_jobs(self):
        """检查停滞的作业"""
        timeout_minutes = self.config['alerts']['no_progress_timeout_minutes']
        timeout_delta = timedelta(minutes=timeout_minutes)
        
        for job_key, job in list(self.running_jobs.items()):
            time_since_check = datetime.now() - job['last_check_time']
            if time_since_check > timeout_delta:
                self.logger.warning(f"⚠️ 作业可能停滞: {job['name']} - {timeout_minutes} 分钟无进度")
    
    def send_notification(self, message: str, level: str = "info"):
        """发送通知（如果配置启用）"""
        notification_config = self.config['monitor']['notification']
        if not notification_config['enabled']:
            return
        
        # 检查是否应该发送此类型的通知
        if level == "success" and not notification_config['notify_on_complete']:
            return
        if level == "error" and not notification_config['notify_on_error']:
            return
        
        # TODO: 实现 webhook 通知
        # 可以使用钉钉、企业微信、Slack 等
        pass
    
    def print_summary(self):
        """打印监控摘要"""
        ue_processes = self.check_ue_process()
        disk_free = self.check_disk_space(self.config['rendering']['output_base_path'])
        
        print("\n" + "="*60)
        print(f"渲染监控摘要 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        print(f"🎮 UE 进程数: {len(ue_processes)}")
        
        if ue_processes:
            for proc in ue_processes:
                try:
                    memory_mb = proc.memory_info().rss / (1024**2)
                    print(f"   PID {proc.pid}: {memory_mb:.1f} MB")
                except:
                    pass
        
        print(f"💾 磁盘剩余: {disk_free:.1f} GB")
        print(f"🎬 运行中: {len(self.running_jobs)}")
        print(f"✅ 已完成: {len(self.completed_jobs)}")
        print(f"❌ 已失败: {len(self.failed_jobs)}")
        
        if self.running_jobs:
            print("\n正在运行的作业:")
            for job_key, job in self.running_jobs.items():
                elapsed = self.format_time_elapsed(job['start_time'])
                print(f"  • {job['name']}: {job['last_frame_count']} 帧, {elapsed}")
        
        print("="*60 + "\n")
    
    def run(self):
        """运行监控循环"""
        check_interval = self.config['monitor']['check_interval_seconds']
        self.logger.info("🚀 渲染监控器启动")
        
        try:
            while True:
                # 扫描状态文件
                status_files = self.scan_for_render_jobs()
                
                for status_file in status_files:
                    status_data = self.read_status_file(status_file)
                    if status_data:
                        self.update_job_status(status_file, status_data)
                
                # 检查停滞的作业
                self.check_stalled_jobs()
                
                # 每分钟打印一次摘要
                if int(time.time()) % 60 < check_interval:
                    self.print_summary()
                
                time.sleep(check_interval)
        
        except KeyboardInterrupt:
            self.logger.info("\n⏹️  监控器停止")
            self.print_summary()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='渲染进程监控器')
    parser.add_argument(
        '--config',
        default='config/monitor_config.json',
        help='监控配置文件路径'
    )
    
    args = parser.parse_args()
    
    # 检查配置文件
    if not os.path.exists(args.config):
        print(f"错误: 配置文件不存在: {args.config}")
        sys.exit(1)
    
    # 启动监控器
    monitor = RenderMonitor(args.config)
    monitor.run()


if __name__ == '__main__':
    main()
