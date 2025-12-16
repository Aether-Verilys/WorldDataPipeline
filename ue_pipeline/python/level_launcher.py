import time
from dataclasses import dataclass
from typing import Iterable, Optional

import unreal

DEFAULT_WAIT_INTERVAL = 0.25
DEFAULT_TIMEOUT = 30.0
DEFAULT_RUN_SECONDS = 20
MAPS_ROOT = "/Game/Maps"


@dataclass
class RunnerConfig:
    wait_interval: float = DEFAULT_WAIT_INTERVAL
    begin_play_timeout: float = DEFAULT_TIMEOUT
    run_seconds: float = DEFAULT_RUN_SECONDS
    maps_root: str = MAPS_ROOT


def discover_map_assets(root: str = MAPS_ROOT) -> Iterable[str]:
    if not unreal.EditorAssetLibrary.does_directory_exist(root):
        unreal.log_warning(f"[AutoPipeline] 目录不存在: {root}")
        return []

    assets = unreal.EditorAssetLibrary.list_assets(root, recursive=True, include_folder=False)
    world_assets = []
    for asset_path in assets:
        if asset_path.endswith("_BuiltData"):
            continue
        asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        if not asset_data:
            continue
        if asset_data.asset_class_path.asset_name != "World":
            continue
        sanitized = asset_path
        if "." in sanitized:
            sanitized = sanitized.split(".", 1)[0]
        world_assets.append(sanitized)
    return sorted(set(world_assets))


# ==============================================================================
# Utility Functions 
# ==============================================================================

def is_pie_playing() -> bool:
    """Check if PIE is currently playing - robust check across UE versions"""
    level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    
    try:
        if level_editor and level_editor.is_in_play_in_editor():
            return True
    except Exception:
        pass

    try:
        checker = getattr(editor_subsystem, "is_playing_in_editor", None)
        if callable(checker) and checker():
            return True
    except Exception:
        pass

    try:
        return bool(unreal.EditorLevelLibrary.is_playing_level())
    except Exception:
        return False

def get_pie_world() -> Optional[unreal.World]:
    """Get the PIE world if it exists"""
    try:
        editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        return editor_subsystem.get_game_world()
    except:
        return None

# ==============================================================================
# Level Launcher Class
# ==============================================================================

class LevelLauncher:
    def __init__(self, config: RunnerConfig):
        self.config = config
        self.maps = list(discover_map_assets(config.maps_root))
        self.current_map_index = -1
        self.state = "IDLE"
        self.state_start_time = 0.0
        self.tick_handle = None
        self.level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    def start(self):
        if not self.maps:
            unreal.log_warning("[LevelLauncher] 未发现任何关卡")
            return
        
        unreal.log(f"[LevelLauncher] 开始执行，共 {len(self.maps)} 个关卡")
        # 防止重复注册
        self.stop() 
        self.tick_handle = unreal.register_slate_post_tick_callback(self.on_tick)
        self.next_map()

    def stop(self):
        if self.tick_handle:
            unreal.unregister_slate_post_tick_callback(self.tick_handle)
            self.tick_handle = None
        unreal.log("[LevelLauncher] 执行结束")

    def set_state(self, new_state):
        self.state = new_state
        self.state_start_time = time.time()
        # unreal.log(f"[LevelLauncher] State -> {new_state}")

    def next_map(self):
        self.current_map_index += 1
        if self.current_map_index >= len(self.maps):
            unreal.log(f"[LevelLauncher] =================================================")
            unreal.log(f"[LevelLauncher] ✓ 所有关卡运行完成! 共处理 {len(self.maps)} 个关卡")
            unreal.log(f"[LevelLauncher] =================================================")
            self.stop()
            return
        
        map_asset = self.maps[self.current_map_index]
        unreal.log(f"[LevelLauncher] --------------------------------------------------")
        unreal.log(f"[LevelLauncher] [{self.current_map_index+1}/{len(self.maps)}] 准备运行关卡: {map_asset}")
        
        try:
            if self.level_editor.load_level(map_asset):
                unreal.log(f"[LevelLauncher] ✓ 关卡加载成功: {map_asset}")
                self.set_state("STARTING_PIE")
            else:
                unreal.log_error(f"[LevelLauncher] 加载关卡失败 {map_asset}")
                self.next_map()
        except Exception as e:
            unreal.log_error(f"[LevelLauncher] 加载关卡异常 {map_asset}: {e}")
            self.next_map()

    def is_playing(self) -> bool:
        """使用全局工具函数"""
        return is_pie_playing()

    def get_pie_world(self) -> Optional[unreal.World]:
        """使用全局工具函数"""
        return get_pie_world()

    def on_tick(self, delta_seconds):
        elapsed = time.time() - self.state_start_time
        
        if self.state == "STARTING_PIE":
            # 使用 LevelEditorSubsystem.editor_request_begin_play()
            try:
                self.level_editor.editor_request_begin_play()
                self.set_state("WAITING_PIE_START")
                unreal.log("[LevelLauncher] 通过 editor_request_begin_play() 启动PIE")
            except Exception as e:
                unreal.log_error(f"[LevelLauncher] 启动PIE失败: {e}")
                self.next_map()

        elif self.state == "WAITING_PIE_START":
            if self.is_playing():
                self.set_state("WAITING_BEGIN_PLAY")
            elif elapsed > self.config.begin_play_timeout:
                unreal.log_error("[LevelLauncher] 等待PIE启动超时")
                self.set_state("STOPPING_PIE")

        elif self.state == "WAITING_BEGIN_PLAY":
            world = self.get_pie_world()
            if world:
                try:
                    # UE5.7 中使用 has_begun_play() 方法
                    begun = world.has_begun_play() if hasattr(world, 'has_begun_play') else True
                    if begun:
                        unreal.log(f"[LevelLauncher] BeginPlay 已触发 - 世界: {world.get_name()}")
                        self.set_state("RUNNING")
                except:
                    # 如果检查失败，假设已开始播放
                    unreal.log(f"[LevelLauncher] 检测到PIE世界，假设已就绪 - 世界: {world.get_name()}")
                    self.set_state("RUNNING")
            elif elapsed > self.config.begin_play_timeout:
                unreal.log_error("[LevelLauncher] 等待 BeginPlay 超时")
                self.set_state("STOPPING_PIE")

        elif self.state == "RUNNING":
            if not self.is_playing():
                unreal.log_warning("[LevelLauncher] PIE 意外停止")
                self.next_map()
            elif elapsed > self.config.run_seconds:
                unreal.log(f"[LevelLauncher] 运行时间结束 ({self.config.run_seconds}s)")
                self.set_state("STOPPING_PIE")

        elif self.state == "STOPPING_PIE":
            if self.is_playing():
                try:
                    self.level_editor.editor_request_end_play()
                except Exception as e:
                    unreal.log_warning(f"[LevelLauncher] 请求停止PIE失败: {e}")
                self.set_state("WAITING_PIE_STOP")
            else:
                self.next_map()

        elif self.state == "WAITING_PIE_STOP":
            if not self.is_playing():
                unreal.log("[LevelLauncher] PIE已停止")
                map_asset = self.maps[self.current_map_index]
                unreal.log(f"[LevelLauncher] ✓ 关卡运行成功: {map_asset}")
                self.next_map()
            elif elapsed > self.config.begin_play_timeout:
                unreal.log_error("[LevelLauncher] 等待PIE停止超时，强制继续")
                self.next_map()


# ==============================================================================
# Manifest-driven API
# ==============================================================================

def load_level_from_manifest(manifest: dict) -> bool:
    """
    Load level/map based on job manifest
    
    Args:
        manifest: job manifest dict containing:
            - map: UE map asset path
    
    Returns:
        True if level loaded successfully
    """
    import unreal
    
    map_path = manifest.get("map")
    if not map_path:
        raise ValueError("Manifest missing 'map' field")
    
    unreal.log(f"[LevelLauncher] Loading map: {map_path}")
    
    level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    success = level_editor.load_level(map_path)
    
    if success:
        unreal.log(f"[LevelLauncher] ✓ Map loaded: {map_path}")
    else:
        unreal.log_error(f"[LevelLauncher] ✗ Failed to load map: {map_path}")
    
    return success


# 全局实例引用，防止被垃圾回收
_runner_instance = None

def main():
    global _runner_instance
    
    if _runner_instance:
        _runner_instance.stop()
    
    config = RunnerConfig()
    _runner_instance = LevelLauncher(config)
    _runner_instance.start()

if __name__ == "__main__":
    main()
