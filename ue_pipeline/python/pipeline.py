import unreal
import time
import os
import sys
from enum import Enum, auto
from typing import Callable, Dict, Any, Optional, List
import level_launcher

# ==============================================================================
# Event System
# ==============================================================================

class PipelineEventType(Enum):
    """Pipeline event types"""
    PIPELINE_STARTED = auto()
    PIPELINE_FINISHED = auto()
    STAGE_STARTED = auto()
    STAGE_FINISHED = auto()
    STAGE_FAILED = auto()
    STATUS_UPDATE = auto()
    ERROR = auto()

class EventBus:
    """Simple event bus for broadcasting pipeline events"""
    _listeners: List[Callable[[PipelineEventType, Dict[str, Any]], None]] = []

    @classmethod
    def subscribe(cls, callback: Callable[[PipelineEventType, Dict[str, Any]], None]):
        if callback not in cls._listeners:
            cls._listeners.append(callback)

    @classmethod
    def unsubscribe(cls, callback: Callable[[PipelineEventType, Dict[str, Any]], None]):
        if callback in cls._listeners:
            cls._listeners.remove(callback)

    @classmethod
    def broadcast(cls, event_type: PipelineEventType, data: Dict[str, Any] = None):
        if data is None:
            data = {}
        data['timestamp'] = time.time()
        
        log_msg = f"[Pipeline Event] {event_type.name}: {data.get('message', '')}"
        if event_type == PipelineEventType.ERROR or event_type == PipelineEventType.STAGE_FAILED:
            unreal.log_error(log_msg)
        else:
            unreal.log(log_msg)

        for listener in cls._listeners:
            try:
                listener(event_type, data)
            except Exception as e:
                unreal.log_error(f"Error in event listener: {e}")

# ==============================================================================
# Pipeline Stages (Async)
# ==============================================================================

class StageStatus(Enum):
    RUNNING = auto()
    FINISHED = auto()
    FAILED = auto()

class PipelineStage:
    """Base class for async pipeline stages"""
    def __init__(self, name: str):
        self.name = name
        self.start_time = 0.0

    def enter(self, context: Dict[str, Any]) -> None:
        """Called when stage starts"""
        self.start_time = time.time()

    def tick(self, context: Dict[str, Any], delta_time: float) -> StageStatus:
        """Called every frame. Return FINISHED when done."""
        return StageStatus.FINISHED

    def exit(self, context: Dict[str, Any]) -> None:
        """Called when stage finishes"""
        pass

class StartPIEStage(PipelineStage):
    def __init__(self, timeout: float = 30.0):
        super().__init__("Start PIE")
        self.timeout = timeout

    def enter(self, context: Dict[str, Any]) -> None:
        super().enter(context)
        EventBus.broadcast(PipelineEventType.STATUS_UPDATE, {"message": "Requesting PIE Start..."})
        
        if not level_launcher.is_pie_playing():
            level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            level_editor.editor_request_begin_play()
        else:
            EventBus.broadcast(PipelineEventType.STATUS_UPDATE, {"message": "PIE already running"})

    def tick(self, context: Dict[str, Any], delta_time: float) -> StageStatus:
        if level_launcher.is_pie_playing():
            # Wait for world to be ready
            world = level_launcher.get_pie_world()
            if world:
                # Check has_begun_play if available (UE 5.x)
                if hasattr(world, 'has_begun_play'):
                    if world.has_begun_play():
                        return StageStatus.FINISHED
                else:
                    return StageStatus.FINISHED
        
        if time.time() - self.start_time > self.timeout:
            EventBus.broadcast(PipelineEventType.ERROR, {"message": "Timeout waiting for PIE start"})
            return StageStatus.FAILED
            
        return StageStatus.RUNNING

class StopPIEStage(PipelineStage):
    def __init__(self, timeout: float = 10.0):
        super().__init__("Stop PIE")
        self.timeout = timeout

    def enter(self, context: Dict[str, Any]) -> None:
        super().enter(context)
        EventBus.broadcast(PipelineEventType.STATUS_UPDATE, {"message": "Requesting PIE Stop..."})
        
        if level_launcher.is_pie_playing():
            level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            level_editor.editor_request_end_play()

    def tick(self, context: Dict[str, Any], delta_time: float) -> StageStatus:
        if not level_launcher.is_pie_playing():
            return StageStatus.FINISHED
            
        if time.time() - self.start_time > self.timeout:
            EventBus.broadcast(PipelineEventType.ERROR, {"message": "Timeout waiting for PIE stop"})
            return StageStatus.FAILED
            
        return StageStatus.RUNNING

class LoadMapStage(PipelineStage):
    def __init__(self, map_path: str):
        super().__init__(f"Load Map: {map_path}")
        self.map_path = map_path

    def enter(self, context: Dict[str, Any]) -> None:
        super().enter(context)
        EventBus.broadcast(PipelineEventType.STATUS_UPDATE, {"message": f"Loading map: {self.map_path}"})
        
        level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if not level_editor.load_level(self.map_path):
            raise RuntimeError(f"Failed to load map: {self.map_path}")

    def tick(self, context: Dict[str, Any], delta_time: float) -> StageStatus:
        # Loading is blocking in UE, so if we are here, it's done
        return StageStatus.FINISHED

class WaitStage(PipelineStage):
    def __init__(self, duration: float):
        super().__init__(f"Wait {duration}s")
        self.duration = duration

    def tick(self, context: Dict[str, Any], delta_time: float) -> StageStatus:
        if time.time() - self.start_time >= self.duration:
            return StageStatus.FINISHED
        return StageStatus.RUNNING

class CallbackStage(PipelineStage):
    """Generic stage that calls a function"""
    def __init__(self, name: str, callback: Callable[[Dict[str, Any]], None]):
        super().__init__(name)
        self.callback = callback

    def enter(self, context: Dict[str, Any]) -> None:
        super().enter(context)
        EventBus.broadcast(PipelineEventType.STATUS_UPDATE, {"message": f"Executing: {self.name}"})
        try:
            self.callback(context)
        except Exception as e:
            raise RuntimeError(f"Callback failed: {e}")

# ==============================================================================
# Automation Supervisor (Async)
# ==============================================================================

class AutomationSupervisor:
    def __init__(self):
        self.stages: List[PipelineStage] = []
        self.context: Dict[str, Any] = {}
        self.is_running = False
        self.current_stage_index = -1
        self.tick_handle = None

    def add_stage(self, stage: PipelineStage):
        self.stages.append(stage)

    def run(self):
        if self.is_running:
            unreal.log_warning("Pipeline is already running")
            return

        self.is_running = True
        self.context = {}
        self.current_stage_index = -1
        
        EventBus.broadcast(PipelineEventType.PIPELINE_STARTED, {"message": "Automation Pipeline Started"})
        
        # Register Tick
        self.tick_handle = unreal.register_slate_post_tick_callback(self._on_tick)
        
        # Start first stage
        self._advance_stage()

    def stop(self):
        if self.tick_handle:
            unreal.unregister_slate_post_tick_callback(self.tick_handle)
            self.tick_handle = None
        self.is_running = False
        EventBus.broadcast(PipelineEventType.PIPELINE_FINISHED, {"message": "Pipeline Stopped"})

    def _advance_stage(self):
        self.current_stage_index += 1
        
        if self.current_stage_index < len(self.stages):
            stage = self.stages[self.current_stage_index]
            EventBus.broadcast(PipelineEventType.STAGE_STARTED, {"stage": stage.name})
            try:
                stage.enter(self.context)
            except Exception as e:
                self._handle_error(f"Error entering stage {stage.name}: {e}")
        else:
            # All done
            EventBus.broadcast(PipelineEventType.PIPELINE_FINISHED, {"message": "All stages completed successfully"})
            self.stop()

    def _on_tick(self, delta_time):
        if not self.is_running or self.current_stage_index >= len(self.stages):
            return

        stage = self.stages[self.current_stage_index]
        
        try:
            status = stage.tick(self.context, delta_time)
            
            if status == StageStatus.FINISHED:
                stage.exit(self.context)
                EventBus.broadcast(PipelineEventType.STAGE_FINISHED, {"stage": stage.name})
                self._advance_stage()
            elif status == StageStatus.FAILED:
                self._handle_error(f"Stage {stage.name} failed")
                
        except Exception as e:
            self._handle_error(f"Error ticking stage {stage.name}: {e}")

    def _handle_error(self, message):
        EventBus.broadcast(PipelineEventType.ERROR, {"message": message})
        self.stop()


# ==============================================================================
# Convenience Stage - Condition Check
# ==============================================================================

class ConditionalWaitStage(PipelineStage):
    """Wait until a condition is met or timeout"""
    def __init__(self, name: str, condition: Callable[[], bool], timeout: float = 30.0):
        super().__init__(name)
        self.condition = condition
        self.timeout = timeout

    def tick(self, context: Dict[str, Any], delta_time: float) -> StageStatus:
        if self.condition():
            return StageStatus.FINISHED
            
        if time.time() - self.start_time > self.timeout:
            EventBus.broadcast(PipelineEventType.ERROR, {"message": f"Timeout waiting for: {self.name}"})
            return StageStatus.FAILED
            
        return StageStatus.RUNNING

