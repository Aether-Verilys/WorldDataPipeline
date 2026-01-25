"""
场景状态注册表管理器
使用SQLite存储大量场景的元数据和处理状态
"""

import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from contextlib import contextmanager


class SceneRegistry:
    def __init__(self, db_path: str = "database/scene_registry.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            # 先检查是否需要迁移（在创建表之前）
            self._migrate_database(conn)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scenes (
                    scene_name TEXT PRIMARY KEY,
                    bos_baked_path TEXT NOT NULL,
                    local_path TEXT,
                    content_hash TEXT,
                    file_count INTEGER DEFAULT 0,
                    total_size_bytes INTEGER DEFAULT 0,
                    bos_exists BOOLEAN DEFAULT 1,
                    bos_last_verified TEXT,
                    downloaded_at TEXT,
                    last_updated TEXT,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS maps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_name TEXT NOT NULL,
                    map_name TEXT NOT NULL,
                    map_path TEXT NOT NULL,
                    navmesh_baked BOOLEAN DEFAULT 0,
                    navmesh_hash TEXT,
                    navmesh_baked_at TEXT,
                    navmesh_auto_scale BOOLEAN DEFAULT 0,
                    navmesh_bounds TEXT,
                    metadata TEXT,
                    FOREIGN KEY (scene_name) REFERENCES scenes(scene_name),
                    UNIQUE(scene_name, map_name)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sequences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_name TEXT NOT NULL,
                    map_name TEXT NOT NULL,
                    sequence_name TEXT NOT NULL,
                    sequence_path TEXT NOT NULL,
                    bos_path TEXT,
                    seed INTEGER,
                    duration_seconds REAL,
                    created_at TEXT,
                    uploaded_at TEXT,
                    metadata TEXT,
                    FOREIGN KEY (scene_name) REFERENCES scenes(scene_name),
                    UNIQUE(scene_name, map_name, sequence_name)
                )
            """)
            
            # 创建索引加速查询
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_hash ON scenes(content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_maps_navmesh ON maps(navmesh_baked)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sequences_created ON sequences(created_at)")
            
            conn.commit()
    
    def _migrate_database(self, conn):
        # 检查 scenes 表是否存在
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scenes'")
        if not cursor.fetchone():
            return  # 表不存在，由 CREATE TABLE IF NOT EXISTS 创建
        
        # 获取现有列信息
        cursor = conn.execute("PRAGMA table_info(scenes)")
        columns = {row[1]: {'type': row[2], 'notnull': row[3], 'pk': row[5]} for row in cursor.fetchall()}
        
        # 需要迁移：旧表有 bos_path，新表需要 bos_baked_path
        # 处理两种情况：
        # 1. 只有 bos_path，没有 bos_baked_path（完全旧版本）
        # 2. 同时有 bos_path 和 bos_baked_path（部分迁移）
        if 'bos_path' in columns:
            print("🔄 迁移数据库: 重建 scenes 表结构 (移除旧的 bos_path 列)...")
            
            # 重建表（SQLite 不支持删除/修改列，只能重建）
            conn.execute("""
                CREATE TABLE scenes_new (
                    scene_name TEXT PRIMARY KEY,
                    bos_baked_path TEXT NOT NULL,
                    local_path TEXT,
                    content_hash TEXT,
                    file_count INTEGER DEFAULT 0,
                    total_size_bytes INTEGER DEFAULT 0,
                    bos_exists BOOLEAN DEFAULT 1,
                    bos_last_verified TEXT,
                    downloaded_at TEXT,
                    last_updated TEXT,
                    metadata TEXT
                )
            """)
            
            # 复制旧数据
            # 优先使用 bos_baked_path（如果存在），否则使用 bos_path
            # 如果两者都为 NULL，使用默认值
            if 'bos_baked_path' in columns:
                # 同时有两列的情况
                conn.execute("""
                    INSERT INTO scenes_new (scene_name, bos_baked_path, local_path, content_hash, 
                                           file_count, total_size_bytes, bos_exists, bos_last_verified,
                                           downloaded_at, last_updated, metadata)
                    SELECT scene_name, 
                           COALESCE(bos_baked_path, bos_path, 'bos://unknown/'),
                           local_path, 
                           content_hash,
                           COALESCE(file_count, 0),
                           COALESCE(total_size_bytes, 0),
                           COALESCE(bos_exists, 1),
                           bos_last_verified,
                           downloaded_at,
                           last_updated,
                           metadata
                    FROM scenes
                """)
            else:
                # 只有 bos_path 的情况
                conn.execute("""
                    INSERT INTO scenes_new (scene_name, bos_baked_path, local_path, content_hash, 
                                           file_count, total_size_bytes, bos_exists, bos_last_verified,
                                           downloaded_at, last_updated, metadata)
                    SELECT scene_name, 
                           COALESCE(bos_path, 'bos://unknown/'),
                           local_path, 
                           content_hash,
                           COALESCE(file_count, 0),
                           COALESCE(total_size_bytes, 0),
                           COALESCE(bos_exists, 1),
                           bos_last_verified,
                           downloaded_at,
                           last_updated,
                           metadata
                    FROM scenes
                """)
            
            # 删除旧表，重命名新表
            conn.execute("DROP TABLE scenes")
            conn.execute("ALTER TABLE scenes_new RENAME TO scenes")
            
            # 重建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenes_hash ON scenes(content_hash)")
            
            print("✓ 数据库迁移完成")
            conn.commit()
            return  # 迁移完成，退出
        
        # 如果是新数据库但缺少某些列，添加它们
        elif 'bos_baked_path' not in columns:
            conn.execute("ALTER TABLE scenes ADD COLUMN bos_baked_path TEXT DEFAULT ''")
        
        if 'file_count' not in columns:
            conn.execute("ALTER TABLE scenes ADD COLUMN file_count INTEGER DEFAULT 0")
        
        if 'total_size_bytes' not in columns:
            conn.execute("ALTER TABLE scenes ADD COLUMN total_size_bytes INTEGER DEFAULT 0")
        
        if 'bos_exists' not in columns:
            conn.execute("ALTER TABLE scenes ADD COLUMN bos_exists BOOLEAN DEFAULT 1")
        
        if 'bos_last_verified' not in columns:
            conn.execute("ALTER TABLE scenes ADD COLUMN bos_last_verified TEXT")
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 允许字典式访问
        try:
            yield conn
        finally:
            conn.close()
    
    # ==================== Scene Operations ====================
    
    def add_scene(self, scene_name: str, bos_baked_path: str, 
                  content_hash: Optional[str] = None,
                  local_path: Optional[str] = None,
                  bos_exists: bool = True,
                  is_downloaded: bool = False,
                  metadata: Optional[Dict] = None) -> bool:
        """
        添加或更新场景记录（仅限已烘焙场景）
        
        Args:
            scene_name: 场景名称（唯一标识）
            bos_baked_path: BOS上已烘焙场景的路径（如 bos://world-data/baked/Seaside_Town/）
            content_hash: 内容哈希（用于检测变化）
            local_path: 本地路径
            bos_exists: BOS中是否存在（默认True）
            is_downloaded: 是否已下载到本地（默认False）
            metadata: 额外元数据（JSON格式）
        
        Returns:
            是否成功
        """
        with self._get_connection() as conn:
            now = datetime.utcnow().isoformat()
            downloaded_at = now if is_downloaded else None
            conn.execute("""
                INSERT INTO scenes (scene_name, bos_baked_path, local_path, content_hash, 
                                   bos_exists, bos_last_verified, downloaded_at, last_updated, metadata)
                ON CONFLICT(scene_name) DO UPDATE SET
                    bos_baked_path = excluded.bos_baked_path,
                    local_path = excluded.local_path,
                    content_hash = excluded.content_hash,
                    bos_exists = excluded.bos_exists,
                    bos_last_verified = excluded.bos_last_verified,
                    last_updated = excluded.last_updated,
                    metadata = excluded.metadata
            """, (scene_name, bos_baked_path, local_path, content_hash, 
                  bos_exists, now if bos_exists else None,
                  downloaded_at, now, json.dumps(metadata) if metadata else None))
            conn.commit()
            return True
    
    def get_scene(self, scene_name: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM scenes WHERE scene_name = ?", 
                (scene_name,)
            ).fetchone()
            if row:
                result = dict(row)
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                return result
            return None
    
    def is_scene_downloaded(self, scene_name: str, expected_hash: Optional[str] = None) -> bool:
        scene = self.get_scene(scene_name)
        if not scene or not scene['downloaded_at']:
            return False
        
        if expected_hash:
            return scene['content_hash'] == expected_hash
        
        return True
    
    def update_scene_stats(self, scene_name: str, file_count: int, total_size_bytes: int):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE scenes 
                SET file_count = ?, total_size_bytes = ?, last_updated = ?
                WHERE scene_name = ?
            """, (file_count, total_size_bytes, datetime.utcnow().isoformat(), scene_name))
            conn.commit()
    
    def list_scenes(self, downloaded_only: bool = False) -> List[Dict]:
        with self._get_connection() as conn:
            query = "SELECT * FROM scenes"
            if downloaded_only:
                query += " WHERE downloaded_at IS NOT NULL"
            query += " ORDER BY scene_name"
            
            rows = conn.execute(query).fetchall()
            results = []
            for row in rows:
                result = dict(row)
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                results.append(result)
            return results
    
    def delete_scene(self, scene_name: str) -> bool:
        with self._get_connection() as conn:
            # 删除关联的序列
            conn.execute("DELETE FROM sequences WHERE scene_name = ?", (scene_name,))
            # 删除关联的地图
            conn.execute("DELETE FROM maps WHERE scene_name = ?", (scene_name,))
            # 删除场景
            cursor = conn.execute("DELETE FROM scenes WHERE scene_name = ?", (scene_name,))
            conn.commit()
            return cursor.rowcount > 0
    
    # ==================== Map Operations ====================
    
    def add_map(self, scene_name: str, map_name: str, map_path: str,
                metadata: Optional[Dict] = None) -> bool:
        """添加地图记录"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO maps (scene_name, map_name, map_path, metadata)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scene_name, map_name) DO UPDATE SET
                    map_path = excluded.map_path,
                    metadata = excluded.metadata
            """, (scene_name, map_name, map_path, json.dumps(metadata) if metadata else None))
            conn.commit()
            return True
    
    def update_navmesh_status(self, scene_name: str, map_name: str,
                             navmesh_hash: str,
                             auto_scale: bool = False,
                             bounds: Optional[Dict] = None):
        """更新地图的NavMesh烘焙状态"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE maps 
                SET navmesh_baked = 1,
                    navmesh_hash = ?,
                    navmesh_baked_at = ?,
                    navmesh_auto_scale = ?,
                    navmesh_bounds = ?
                WHERE scene_name = ? AND map_name = ?
            """, (navmesh_hash, datetime.utcnow().isoformat(), auto_scale,
                  json.dumps(bounds) if bounds else None, scene_name, map_name))
            conn.commit()
    
    def is_navmesh_baked(self, scene_name: str, map_name: str, 
                        expected_hash: Optional[str] = None) -> bool:
        """检查地图是否已烘焙NavMesh"""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT navmesh_baked, navmesh_hash 
                FROM maps 
                WHERE scene_name = ? AND map_name = ?
            """, (scene_name, map_name)).fetchone()
            
            if not row or not row['navmesh_baked']:
                return False
            
            if expected_hash:
                return row['navmesh_hash'] == expected_hash
            
            return True
    
    def list_maps(self, scene_name: Optional[str] = None, 
                  navmesh_baked: Optional[bool] = None) -> List[Dict]:
        """列出地图"""
        with self._get_connection() as conn:
            query = "SELECT * FROM maps WHERE 1=1"
            params = []
            
            if scene_name:
                query += " AND scene_name = ?"
                params.append(scene_name)
            
            if navmesh_baked is not None:
                query += " AND navmesh_baked = ?"
                params.append(1 if navmesh_baked else 0)
            
            query += " ORDER BY scene_name, map_name"
            
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                result = dict(row)
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                if result['navmesh_bounds']:
                    result['navmesh_bounds'] = json.loads(result['navmesh_bounds'])
                results.append(result)
            return results
    
    # ==================== Sequence Operations ====================
    
    def add_sequence(self, scene_name: str, map_name: str, 
                    sequence_name: str, sequence_path: str,
                    seed: Optional[int] = None,
                    duration_seconds: Optional[float] = None,
                    bos_path: Optional[str] = None,
                    metadata: Optional[Dict] = None) -> bool:
        """添加序列记录"""
        with self._get_connection() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute("""
                INSERT INTO sequences (scene_name, map_name, sequence_name, sequence_path,
                                      seed, duration_seconds, bos_path, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scene_name, map_name, sequence_name) DO UPDATE SET
                    sequence_path = excluded.sequence_path,
                    seed = excluded.seed,
                    duration_seconds = excluded.duration_seconds,
                    bos_path = excluded.bos_path,
                    metadata = excluded.metadata
            """, (scene_name, map_name, sequence_name, sequence_path, 
                  seed, duration_seconds, bos_path, now, json.dumps(metadata) if metadata else None))
            conn.commit()
            return True
    
    def mark_sequence_uploaded(self, scene_name: str, map_name: str, 
                              sequence_name: str, bos_path: str):
        """标记序列已上传到BOS"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE sequences 
                SET bos_path = ?, uploaded_at = ?
                WHERE scene_name = ? AND map_name = ? AND sequence_name = ?
            """, (bos_path, datetime.utcnow().isoformat(), scene_name, map_name, sequence_name))
            conn.commit()
    
    def list_sequences(self, scene_name: Optional[str] = None,
                      map_name: Optional[str] = None,
                      uploaded_only: bool = False) -> List[Dict]:
        """列出序列"""
        with self._get_connection() as conn:
            query = "SELECT * FROM sequences WHERE 1=1"
            params = []
            
            if scene_name:
                query += " AND scene_name = ?"
                params.append(scene_name)
            
            if map_name:
                query += " AND map_name = ?"
                params.append(map_name)
            
            if uploaded_only:
                query += " AND uploaded_at IS NOT NULL"
            
            query += " ORDER BY created_at DESC"
            
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                result = dict(row)
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                results.append(result)
            return results
    
    # ==================== BOS Synchronization ====================
    
    def mark_scene_bos_status(self, scene_name: str, exists: bool):
        """
        更新场景在BOS中的存在状态
        
        Args:
            scene_name: 场景名称
            exists: 在BOS中是否存在
        """
        with self._get_connection() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute("""
                UPDATE scenes 
                SET bos_exists = ?, bos_last_verified = ?, last_updated = ?
                WHERE scene_name = ?
            """, (exists, now, now, scene_name))
            conn.commit()
    
    def sync_with_bos(self, bos_client, bucket: str = "world-data", prefix: str = "baked/"):
        """
        同步数据库与BOS状态
        
        检查数据库中记录的所有场景，验证它们在BOS中是否仍然存在
        
        Args:
            bos_client: BOS客户端实例（bce-python-sdk的BosClient）
            bucket: BOS bucket名称
            prefix: 前缀路径（如 "baked/"）
        
        Returns:
            Dict: 同步结果统计
                - verified: 验证存在的场景数
                - missing: 发现丢失的场景数
                - updated: 更新状态的场景数
        """
        stats = {
            'verified': 0,
            'missing': 0,
            'updated': 0,
            'errors': []
        }
        
        # 获取数据库中的所有场景
        scenes = self.list_scenes()
        
        for scene in scenes:
            scene_name = scene['scene_name']
            old_status = scene['bos_exists']
            
            try:
                # 构建BOS路径（从bos_baked_path提取）
                # 例如: "bos://world-data/baked/Seaside_Town/" -> "baked/Seaside_Town/"
                bos_path = scene['bos_baked_path']
                if bos_path.startswith('bos://'):
                    path_parts = bos_path.replace('bos://', '').split('/', 1)
                    if len(path_parts) > 1:
                        object_prefix = path_parts[1].rstrip('/')
                    else:
                        object_prefix = f"{prefix}{scene_name}"
                else:
                    object_prefix = f"{prefix}{scene_name}"
                
                # 检查BOS中是否存在该路径下的文件
                # 列出前几个对象即可（不需要全部列出）
                response = bos_client.list_objects(
                    bucket_name=bucket,
                    prefix=object_prefix,
                    max_keys=1
                )
                
                # 如果有内容，说明场景存在
                exists = len(response.contents) > 0
                
                # 更新状态
                if exists != old_status:
                    self.mark_scene_bos_status(scene_name, exists)
                    stats['updated'] += 1
                    
                    if not exists:
                        stats['missing'] += 1
                        print(f"⚠ 场景 '{scene_name}' 在BOS中已丢失")
                    else:
                        print(f"✓ 场景 '{scene_name}' 在BOS中已恢复")
                else:
                    if exists:
                        self.mark_scene_bos_status(scene_name, True)  # 更新验证时间
                        stats['verified'] += 1
                    else:
                        stats['missing'] += 1
                
            except Exception as e:
                stats['errors'].append({
                    'scene': scene_name,
                    'error': str(e)
                })
                print(f"✗ 检查场景 '{scene_name}' 时出错: {e}")
        
        return stats
    
    def list_missing_scenes(self) -> List[Dict]:
        """列出在BOS中已丢失的场景"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM scenes 
                WHERE bos_exists = 0
                ORDER BY scene_name
            """).fetchall()
            
            results = []
            for row in rows:
                result = dict(row)
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                results.append(result)
            return results
    
    # ==================== Statistics ====================
    
    def get_statistics(self) -> Dict:
        """获取全局统计信息"""
        with self._get_connection() as conn:
            stats = {}
            
            # 场景统计
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN downloaded_at IS NOT NULL THEN 1 END) as downloaded,
                    SUM(file_count) as total_files,
                    SUM(total_size_bytes) as total_bytes
                FROM scenes
            """).fetchone()
            stats['scenes'] = dict(row)
            
            # 地图统计
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN navmesh_baked = 1 THEN 1 END) as navmesh_baked
                FROM maps
            """).fetchone()
            stats['maps'] = dict(row)
            
            # 序列统计
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN uploaded_at IS NOT NULL THEN 1 END) as uploaded,
                    SUM(duration_seconds) as total_duration_seconds
                FROM sequences
            """).fetchone()
            stats['sequences'] = dict(row)
            stats['sequences']['total_duration_hours'] = (
                stats['sequences']['total_duration_seconds'] / 3600 
                if stats['sequences']['total_duration_seconds'] else 0
            )
            
            return stats


def calculate_directory_hash(directory: Path, extensions: List[str] = None) -> str:
    """
    计算目录内容哈希（用于检测场景变化）
    
    Args:
        directory: 目录路径
        extensions: 需要包含的文件扩展名列表（如 ['.umap', '.uasset']）
    
    Returns:
        SHA256哈希值
    """
    if not directory.exists():
        return ""
    
    hasher = hashlib.sha256()
    
    # 收集所有文件路径并排序（确保哈希稳定）
    files = []
    for file_path in directory.rglob('*'):
        if file_path.is_file():
            if extensions is None or file_path.suffix.lower() in extensions:
                files.append(file_path)
    
    files.sort()
    
    # 计算哈希
    for file_path in files:
        # 添加相对路径到哈希
        rel_path = file_path.relative_to(directory)
        hasher.update(str(rel_path).encode())
        
        # 添加文件大小和修改时间
        stat = file_path.stat()
        hasher.update(str(stat.st_size).encode())
        hasher.update(str(int(stat.st_mtime)).encode())
    
    return hasher.hexdigest()


if __name__ == "__main__":
    # 使用示例
    registry = SceneRegistry()
    
    # 添加场景
    registry.add_scene(
        scene_name="Seaside_Town",
        bos_baked_path="bos://world-data/baked/Seaside_Town/",
        content_hash="abc123...",
        local_path="D:/UE_Cache/Seaside_Town/",
        metadata={"source": "marketplace", "version": "1.0"}
    )
    
    # 添加地图
    registry.add_map(
        scene_name="Seaside_Town",
        map_name="Demonstration",
        map_path="/Game/Seaside_Town/Maps/Demonstration.Demonstration"
    )
    
    # 更新NavMesh状态
    registry.update_navmesh_status(
        scene_name="Seaside_Town",
        map_name="Demonstration",
        navmesh_hash="xyz789...",
        auto_scale=True,
        bounds={"min": [-1000, -1000, 0], "max": [1000, 1000, 500]}
    )
    
    # 查询
    if registry.is_scene_downloaded("Seaside_Town"):
        print("场景已下载")
    
    if registry.is_navmesh_baked("Seaside_Town", "Demonstration"):
        print("NavMesh已烘焙")
    
    # 统计
    stats = registry.get_statistics()
    print(f"总计: {stats['scenes']['total']} 场景, {stats['sequences']['total_duration_hours']:.1f} 小时视频")
