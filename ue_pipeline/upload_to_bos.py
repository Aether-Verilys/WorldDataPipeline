#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import json
import configparser
from pathlib import Path
from baidubce.bce_client_configuration import BceClientConfiguration
from baidubce.auth.bce_credentials import BceCredentials
from baidubce.services.bos.bos_client import BosClient
from baidubce.exception import BceError


class BOSUploader:
    """BOS文件上传器"""
    
    def __init__(self, access_key_id=None, secret_access_key=None, endpoint=None, config_file=None):
        """
        初始化上传器
        
        凭证获取优先级：
        1. 命令行参数（--ak, --sk）
        2. 配置文件（--config）
        3. 环境变量（BCE_ACCESS_KEY_ID, BCE_SECRET_ACCESS_KEY）
        4. 百度云CLI默认配置 (~/.bceconf/config/credentials)
        
        Args:
            access_key_id: BOS Access Key ID
            secret_access_key: BOS Secret Access Key
            endpoint: BOS endpoint (例如: bj.bcebos.com)
            config_file: 配置文件路径 (JSON格式)
        """
        # 优先级1: 从配置文件读取
        if config_file and os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                access_key_id = access_key_id or config.get('access_key_id')
                secret_access_key = secret_access_key or config.get('secret_access_key')
                endpoint = endpoint or config.get('endpoint', 'bj.bcebos.com')
        
        # 优先级2: 从环境变量读取
        if not access_key_id or not secret_access_key:
            access_key_id = access_key_id or os.environ.get('BCE_ACCESS_KEY_ID')
            secret_access_key = secret_access_key or os.environ.get('BCE_SECRET_ACCESS_KEY')
            endpoint = endpoint or os.environ.get('BCE_ENDPOINT', 'bj.bcebos.com')
            
            if access_key_id and secret_access_key:
                print("✓ 从环境变量读取BOS凭证")
        
        # 优先级3: 从百度云CLI默认配置读取
        if not access_key_id or not secret_access_key:
            bce_config_path = self._get_bce_config_path()
            if bce_config_path and os.path.exists(bce_config_path):
                ak, sk = self._read_bce_credentials(bce_config_path)
                access_key_id = access_key_id or ak
                secret_access_key = secret_access_key or sk
                
                if access_key_id and secret_access_key:
                    print(f"✓ 从百度云CLI配置读取凭证: {bce_config_path}")
        
        # 检查是否成功获取凭证
        if not access_key_id or not secret_access_key:
            print("\n❌ 错误: 未找到BOS凭证信息")
            print("\n请使用以下任一方式提供凭证：\n")
            print("方式1 - 环境变量（推荐）:")
            print("  Windows: ")
            print("    set BCE_ACCESS_KEY_ID=your_access_key")
            print("    set BCE_SECRET_ACCESS_KEY=your_secret_key")
            print("  Linux/Mac: ")
            print("    export BCE_ACCESS_KEY_ID=your_access_key")
            print("    export BCE_SECRET_ACCESS_KEY=your_secret_key")
            print("\n方式2 - 百度云CLI配置文件:")
            print(f"  配置文件位置: {self._get_bce_config_path()}")
            print("  使用 bcecmd 命令行工具配置")
            print("\n方式3 - 命令行参数:")
            print("  --ak YOUR_ACCESS_KEY --sk YOUR_SECRET_KEY")
            print("\n方式4 - JSON配置文件:")
            print("  --config config/bos_config.json")
            sys.exit(1)
        
        # 配置BOS客户端
        config = BceClientConfiguration(
            credentials=BceCredentials(access_key_id, secret_access_key),
            endpoint=endpoint or 'bj.bcebos.com'
        )
        self.client = BosClient(config)
        print(f"✓ BOS客户端初始化成功 (endpoint: {endpoint or 'bj.bcebos.com'})")
    
    def _get_bce_config_path(self):
        """获取百度云CLI配置文件路径"""
        home = Path.home()
        # Windows: C:\Users\username\.bceconf\config\credentials
        # Linux/Mac: ~/.bceconf/config/credentials
        return home / '.bceconf' / 'config' / 'credentials'
    
    def _read_bce_credentials(self, config_path):
        """
        读取百度云CLI配置文件中的凭证
        
        配置文件格式 (INI):
        [Credentials]
        ak = your_access_key
        sk = your_secret_key
        """
        try:
            config = configparser.ConfigParser()
            config.read(config_path, encoding='utf-8')
            
            if 'Credentials' in config:
                ak = config['Credentials'].get('ak')
                sk = config['Credentials'].get('sk')
                return ak, sk
            
            return None, None
        except Exception as e:
            print(f"警告: 读取百度云配置文件失败: {e}")
            return None, None
    
    def upload_file(self, local_path, bucket, bos_path, storage_class="STANDARD"):
        """
        上传单个文件到BOS
        
        Args:
            local_path: 本地文件路径
            bucket: BOS bucket名称
            bos_path: BOS目标路径 (不包含bucket，例如: world-data/raw/file.txt)
            storage_class: 存储类型，可选: STANDARD, STANDARD_IA, COLD, ARCHIVE
            
        Returns:
            bool: 上传是否成功
        """
        # 检查本地文件是否存在
        if not os.path.exists(local_path):
            print(f"错误: 本地文件不存在: {local_path}")
            return False
        
        # 处理BOS路径，确保不以/开头
        bos_path = bos_path.lstrip('/')
        
        print(f"正在上传: {local_path} -> bos://{bucket}/{bos_path}")
        
        try:
            # 获取文件大小用于显示进度
            file_size = os.path.getsize(local_path)
            size_mb = file_size / (1024 * 1024)
            print(f"  文件大小: {size_mb:.2f} MB")
            
            # 上传文件
            self.client.put_object_from_file(
                bucket_name=bucket,
                key=bos_path,
                file_name=local_path,
                storage_class=storage_class
            )
            
            print(f"✓ 上传成功: {local_path}")
            return True
            
        except BceError as e:
            print(f"✗ 上传失败: {local_path}")
            print(f"  错误信息: {e}")
            return False
        except Exception as e:
            print(f"✗ 上传出错: {local_path}")
            print(f"  错误: {e}")
            return False
    
    def upload_directory(self, local_dir, bucket, bos_base_path, 
                        recursive=True, exclude_patterns=None):
        """
        上传整个目录到BOS
        
        Args:
            local_dir: 本地目录路径
            bucket: BOS bucket名称
            bos_base_path: BOS目标基础路径 (例如: world-data/raw/)
            recursive: 是否递归上传子目录
            exclude_patterns: 要排除的文件模式列表
            
        Returns:
            tuple: (成功数量, 失败数量)
        """
        if not os.path.isdir(local_dir):
            print(f"错误: 本地目录不存在: {local_dir}")
            return 0, 0
        
        # 处理BOS路径
        bos_base_path = bos_base_path.strip('/')
        
        print(f"正在扫描目录: {local_dir}")
        
        # 收集要上传的文件
        files_to_upload = []
        local_dir_path = Path(local_dir)
        
        if recursive:
            # 递归获取所有文件
            for file_path in local_dir_path.rglob('*'):
                if file_path.is_file():
                    # 检查是否需要排除
                    if exclude_patterns:
                        skip = False
                        for pattern in exclude_patterns:
                            if file_path.match(pattern):
                                skip = True
                                break
                        if skip:
                            continue
                    files_to_upload.append(file_path)
        else:
            # 只获取当前目录的文件
            for file_path in local_dir_path.glob('*'):
                if file_path.is_file():
                    files_to_upload.append(file_path)
        
        print(f"找到 {len(files_to_upload)} 个文件待上传")
        
        # 上传文件
        success_count = 0
        fail_count = 0
        
        for file_path in files_to_upload:
            # 计算相对路径
            rel_path = file_path.relative_to(local_dir_path)
            # 使用正斜杠作为BOS路径分隔符
            bos_key = f"{bos_base_path}/{str(rel_path).replace(os.sep, '/')}"
            
            if self.upload_file(str(file_path), bucket, bos_key):
                success_count += 1
            else:
                fail_count += 1
        
        print(f"\n目录上传完成: 成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count
    
    def upload_batch(self, file_list, bucket, bos_base_path, keep_structure=False):
        """
        批量上传文件
        
        Args:
            file_list: 本地文件路径列表
            bucket: BOS bucket名称
            bos_base_path: BOS基础路径 (例如: world-data/raw/)
            keep_structure: 是否保持目录结构 (如果False，所有文件上传到同一目录)
            
        Returns:
            tuple: (成功数量, 失败数量)
        """
        success_count = 0
        fail_count = 0
        
        bos_base_path = bos_base_path.strip('/')
        
        for local_file in file_list:
            if not os.path.exists(local_file):
                print(f"跳过不存在的文件: {local_file}")
                fail_count += 1
                continue
            
            # 确定BOS目标路径
            if keep_structure:
                # 保持目录结构 (相对于当前工作目录)
                rel_path = os.path.relpath(local_file)
                bos_key = f"{bos_base_path}/{rel_path.replace(os.sep, '/')}"
            else:
                # 只使用文件名
                file_name = os.path.basename(local_file)
                bos_key = f"{bos_base_path}/{file_name}"
            
            # 上传文件
            if self.upload_file(local_file, bucket, bos_key):
                success_count += 1
            else:
                fail_count += 1
        
        print(f"\n批量上传完成: 成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count


def main():
    parser = argparse.ArgumentParser(
        description="上传本地文件到百度云BOS (使用Python SDK，跨平台支持)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用环境变量（推荐，无需配置文件）
  python upload_to_bos.py -f video.mp4 -b my-bucket -p world-data/raw/
  
  # 使用百度云CLI配置（~/.bceconf/config/credentials）
  python upload_to_bos.py -d ./output/S0001 -b my-bucket -p world-data/raw/S0001/ --recursive
  
  # 使用配置文件
  python upload_to_bos.py -f video.mp4 -b my-bucket -p world-data/raw/ --config bos_config.json
  
  # 批量上传文件
  python upload_to_bos.py -l file1.mp4 file2.json -b my-bucket -p world-data/raw/

凭证配置（按优先级）:
  1. 命令行参数: --ak YOUR_AK --sk YOUR_SK
  2. JSON配置文件: --config config/bos_config.json
  3. 环境变量: BCE_ACCESS_KEY_ID, BCE_SECRET_ACCESS_KEY
  4. 百度云CLI配置: ~/.bceconf/config/credentials

环境变量设置:
  Windows PowerShell:
    $env:BCE_ACCESS_KEY_ID="your_ak"
    $env:BCE_SECRET_ACCESS_KEY="your_sk"
  
  Windows CMD:
    set BCE_ACCESS_KEY_ID=your_ak
    set BCE_SECRET_ACCESS_KEY=your_sk
  
  Linux/Mac:
    export BCE_ACCESS_KEY_ID=your_ak
    export BCE_SECRET_ACCESS_KEY=your_sk
        """
    )
    
    # 输入参数
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-f", "--file", help="要上传的本地文件路径")
    input_group.add_argument("-d", "--directory", help="要上传的本地目录路径")
    input_group.add_argument("-l", "--list", nargs="+", help="要批量上传的文件列表")
    
    # BOS配置
    parser.add_argument("-b", "--bucket", required=True, help="BOS bucket名称")
    parser.add_argument("-p", "--path", required=True, help="BOS目标路径 (例如: world-data/raw/)")
    
    # 凭证配置（可选，优先级高于环境变量和默认配置）
    auth_group = parser.add_argument_group('认证配置（可选）')
    auth_group.add_argument("--config", help="BOS配置文件路径 (JSON格式)")
    auth_group.add_argument("--ak", help="BOS Access Key ID")
    auth_group.add_argument("--sk", help="BOS Secret Access Key")
    auth_group.add_argument("--endpoint", help="BOS endpoint (默认: bj.bcebos.com)")
    
    # 可选参数
    parser.add_argument("--storage-class", default="STANDARD", 
                       choices=["STANDARD", "STANDARD_IA", "COLD", "ARCHIVE"],
                       help="存储类型 (默认: STANDARD)")
    parser.add_argument("--recursive", action="store_true", help="递归上传目录 (仅用于目录上传)")
    parser.add_argument("--exclude", nargs="+", help="排除的文件模式 (仅用于目录上传)")
    parser.add_argument("--keep-structure", action="store_true", help="保持目录结构 (仅用于批量上传)")
    
    args = parser.parse_args()
    
    # 创建上传器（会自动从多个来源读取凭证）
    uploader = BOSUploader(
        access_key_id=args.ak,
        secret_access_key=args.sk,
        endpoint=args.endpoint,
        config_file=args.config
    )
    
    # 执行上传
    if args.file:
        # 单文件上传
        success = uploader.upload_file(
            args.file, 
            args.bucket,
            args.path + os.path.basename(args.file),
            storage_class=args.storage_class
        )
        sys.exit(0 if success else 1)
        
    elif args.directory:
        # 目录上传
        success_count, fail_count = uploader.upload_directory(
            args.directory,
            args.bucket,
            args.path,
            recursive=args.recursive,
            exclude_patterns=args.exclude
        )
        sys.exit(0 if fail_count == 0 else 1)
        
    elif args.list:
        # 批量文件上传
        success_count, fail_count = uploader.upload_batch(
            args.list,
            args.bucket,
            args.path,
            keep_structure=args.keep_structure
        )
        sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
