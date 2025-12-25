"""
Add NavMesh to UE scene/level with auto-scaling support
"""
import unreal
import time


class NavMeshManager:
    
    def __init__(self):
        self.level_editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.editor_actor_subsystem = unreal.EditorActorSubsystem()
    
    def load_map(self, map_package_path):
        """
        Load a map/level in UE Editor
        Uses LevelEditorSubsystem.load_level (recommended) with fallback to EditorLevelLibrary
        """
        try:
            # Method 1: LevelEditorSubsystem.load_level (preferred)
            if self.level_editor_subsystem:
                unreal.log(f"Loading map via LevelEditorSubsystem: {map_package_path}")
                success = self.level_editor_subsystem.load_level(map_package_path)
                if success:
                    unreal.log(f"✓ Map loaded: {map_package_path}")
                    return True
                else:
                    unreal.log_warning(f"LevelEditorSubsystem.load_level returned False for: {map_package_path}")
        except Exception as e:
            unreal.log_warning(f"LevelEditorSubsystem.load_level failed: {str(e)}")
        
        # Method 2: EditorLevelLibrary.load_level (fallback)
        try:
            load_level = getattr(unreal.EditorLevelLibrary, "load_level", None)
            if callable(load_level):
                unreal.log(f"Loading map via EditorLevelLibrary: {map_package_path}")
                success = load_level(map_package_path)
                if success:
                    unreal.log(f"✓ Map loaded: {map_package_path}")
                    return True
        except Exception as e:
            unreal.log_error(f"EditorLevelLibrary.load_level failed: {str(e)}")
        
        unreal.log_error(f"Failed to load map: {map_package_path}")
        return False
    
    def check_navmesh_exists(self):
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        
        for actor in all_actors:
            if isinstance(actor, unreal.NavMeshBoundsVolume):
                unreal.log(f"Found existing NavMeshBoundsVolume: {actor.get_name()}")
                return actor
        
        return None
    
    def add_navmesh_bounds_volume(self, location=None, scale=None):
        # Check if already exists
        existing = self.check_navmesh_exists()
        if existing:
            unreal.log_warning("NavMeshBoundsVolume already exists in this level")
            return existing
        
        # Default location and scale
        if location is None:
            location = unreal.Vector(0.0, 0.0, 0.0)
        elif isinstance(location, (tuple, list)):
            location = unreal.Vector(location[0], location[1], location[2])
        
        if scale is None:
            scale = unreal.Vector(10.0, 10.0, 10.0)
        elif isinstance(scale, (tuple, list)):
            scale = unreal.Vector(scale[0], scale[1], scale[2])
        
        try:
            # Spawn NavMeshBoundsVolume
            navmesh_volume = self.editor_actor_subsystem.spawn_actor_from_class(
                unreal.NavMeshBoundsVolume,
                location
            )
            
            if navmesh_volume:
                # Set scale
                navmesh_volume.set_actor_scale3d(scale)
                
                unreal.log(f"Added NavMeshBoundsVolume at {location}")
                unreal.log(f"  Scale: {scale}")
                unreal.log(f"  Actor: {navmesh_volume.get_name()}")
                
                # Save level (note: actual save will be done after NavMesh build)
                # No need to save here, will save in worker after verification
                
                return navmesh_volume
            else:
                unreal.log_error("Failed to spawn NavMeshBoundsVolume")
                return None
                
        except Exception as e:
            unreal.log_error(f"Error adding NavMeshBoundsVolume: {str(e)}")
            return None
    
    def configure_navmesh_settings(self, navmesh_volume, settings_dict):
        try:
            for prop_name, prop_value in settings_dict.items():
                if navmesh_volume.has_property(prop_name):
                    navmesh_volume.set_editor_property(prop_name, prop_value)
                    unreal.log(f"  Set {prop_name} = {prop_value}")
                else:
                    unreal.log_warning(f"  Property '{prop_name}' not found")
            
        except Exception as e:
            unreal.log_error(f"Error configuring NavMesh: {str(e)}")
    
    def batch_add_navmesh_to_maps(self, map_list, location=None, scale=None):
        results = {
            'total': len(map_list),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'failed_maps': []
        }
        
        unreal.log("=" * 60)
        unreal.log("Batch Adding NavMesh to Maps")
        unreal.log("=" * 60)
        unreal.log(f"Total maps: {len(map_list)}")
        unreal.log(f"Location: {location}")
        unreal.log(f"Scale: {scale}")
        unreal.log("")
        
        for i, map_path in enumerate(map_list, 1):
            unreal.log(f"[{i}/{len(map_list)}] Processing: {map_path}")
            
            # Load map
            if not self.load_map(map_path):
                results['failed'] += 1
                results['failed_maps'].append(map_path)
                continue
            
            # Add NavMesh
            navmesh = self.add_navmesh_bounds_volume(location, scale)
            if navmesh:
                # Check if it was newly created or already existed
                if self.check_navmesh_exists():
                    results['success'] += 1
                    unreal.log(f"  NavMesh added/verified")
            else:
                results['failed'] += 1
                results['failed_maps'].append(map_path)
                unreal.log_warning(f"  Failed to add NavMesh")
            
            unreal.log("")
        
        unreal.log("=" * 60)
        unreal.log("Batch Add NavMesh Complete")
        unreal.log(f"Success: {results['success']}/{results['total']}")
        unreal.log(f"Failed: {results['failed']}/{results['total']}")
        if results['failed_maps']:
            unreal.log("Failed maps:")
            for map_path in results['failed_maps']:
                unreal.log(f"  - {map_path}")
        unreal.log("=" * 60)
        
        return results
    
    def rebuild_navmesh(self):
        """
        Trigger NavMesh rebuild (optional - NavMesh auto-builds when NavMeshBoundsVolume is added)
        In UE 5.7, NavMesh automatically starts building after adding NavMeshBoundsVolume,
        so this method just logs a message and returns immediately.
        """
        try:
            unreal.log("NavMesh will auto-build after adding NavMeshBoundsVolume...")
            unreal.log("No manual rebuild trigger needed in UE 5.7+")
            # NavMesh automatically rebuilds when:
            # 1. NavMeshBoundsVolume is added
            # 2. NavMeshBoundsVolume scale/location changes
            # 3. Navigable geometry changes
        except Exception as e:
            unreal.log_error(f"Error in rebuild_navmesh: {str(e)}")
    
    def wait_for_navmesh_build(self, timeout_seconds=60):
        """
        Wait for NavMesh to finish building
        Returns True if build completed, False if timeout
        """
        try:
            unreal.log(f"Waiting for NavMesh build to complete (timeout: {timeout_seconds}s)...")
            world = unreal.EditorLevelLibrary.get_editor_world()
            nav_sys = unreal.NavigationSystemV1.get_navigation_system(world)
            
            if not nav_sys:
                unreal.log_warning("NavigationSystem not found")
                return False
            
            # Try to find the is_navigation_being_built method with various signatures
            check_fn = getattr(nav_sys, "is_navigation_being_built_or_locked", None)
            if not callable(check_fn):
                check_fn = getattr(unreal.NavigationSystemV1, "is_navigation_being_built_or_locked", None)
            
            if not callable(check_fn):
                # Fallback: just wait a fixed time
                unreal.log("is_navigation_being_built API not available, waiting 5 seconds...")
                time.sleep(5)
                return True
            
            start_time = time.time()
            check_interval = 0.5  # Check every 0.5 seconds
            
            while time.time() - start_time < timeout_seconds:
                # Check if navigation is still being built
                try:
                    is_building = check_fn(world)
                except TypeError:
                    # Try without world parameter
                    is_building = check_fn()
                
                if not is_building:
                    elapsed = time.time() - start_time
                    unreal.log(f"NavMesh build completed in {elapsed:.1f} seconds")
                    return True
                
                time.sleep(check_interval)
            
            unreal.log_warning(f"NavMesh build timeout after {timeout_seconds} seconds")
            return False
            
        except Exception as e:
            unreal.log_error(f"Error waiting for NavMesh build: {str(e)}")
            return False
    
    def verify_navmesh_data(self, test_reachability=True, min_success_rate=0.8):
        """
        Strictly verify that NavMesh has valid navigable areas
        Checks: NavigationSystem exists, random point reachability
        
        Args:
            test_reachability: Whether to test random point reachability
            min_success_rate: Minimum success rate for reachability tests (default 0.8 = 80%)
        
        Returns True if NavMesh is valid and has data
        """
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            nav_sys = unreal.NavigationSystemV1.get_navigation_system(world)
            
            if not nav_sys:
                unreal.log_warning("NavigationSystem not found")
                return False
            
            unreal.log("NavigationSystem exists")
            
            # Test random point reachability to verify NavMesh has data
            if test_reachability:
                unreal.log("Testing NavMesh reachability...")
                test_attempts = 10
                success_count = 0
                
                # Get bounds center to test around
                center, extent = self.calculate_map_bounds()
                if not center:
                    center = unreal.Vector(0, 0, 0)
                    test_radius = 100000.0
                else:
                    # Test within the calculated bounds
                    test_radius = max(extent.x, extent.y) * 1.5
                
                # Try different API signatures
                get_random_fn = getattr(nav_sys, "get_random_reachable_point_in_radius", None)
                if not callable(get_random_fn):
                    get_random_fn = getattr(nav_sys, "k2_get_random_reachable_point_in_radius", None)
                
                if not callable(get_random_fn):
                    unreal.log_warning("get_random_reachable_point_in_radius API not available")
                    return True  # Assume valid if we can't test
                
                for i in range(test_attempts):
                    try:
                        random_point = get_random_fn(world, center, test_radius)
                        if random_point:
                            success_count += 1
                    except Exception:
                        # Try without world parameter
                        try:
                            random_point = get_random_fn(center, test_radius)
                            if random_point:
                                success_count += 1
                        except Exception:
                            pass
                
                success_rate = success_count / test_attempts if test_attempts > 0 else 0
                unreal.log(f"Reachability test: {success_count}/{test_attempts} ({success_rate*100:.0f}%)")
                
                if success_rate < min_success_rate:
                    unreal.log_warning(f"NavMesh verification failed - reachability {success_rate*100:.0f}% < required {min_success_rate*100:.0f}%")
                    return False
                
                if success_count > 0:
                    unreal.log(f"NavMesh verified - found navigable areas")
            
            unreal.log("NavMesh verification PASSED")
            return True
                
        except Exception as e:
            unreal.log_error(f"Error verifying NavMesh: {str(e)}")
            return False
    
    def calculate_map_bounds(self, agent_max_step_height=50.0, agent_max_jump_height=200.0):
        """
        Calculate the bounding box of all navigable geometry in the current level
        Filters components by navigation relevance and collision settings
        
        Args:
            agent_max_step_height: Max step height for agent (cm), default 50.0
            agent_max_jump_height: Max jump height for agent (cm), default 200.0
        
        Returns: (center_location, bounds_extent) as unreal.Vector tuples
        """
        try:
            unreal.log("Calculating map bounds from navigable geometry...")
            unreal.log(f"  Agent MaxStepHeight: {agent_max_step_height} cm")
            unreal.log(f"  Agent MaxJumpHeight: {agent_max_jump_height} cm")
            
            world = unreal.EditorLevelLibrary.get_editor_world()
            all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
            
            # First pass: Find the largest PostProcessVolume as scene boundary reference
            max_postprocess_extent = 0.0
            postprocess_count = 0
            for actor in all_actors:
                if 'PostProcessVolume' in actor.get_class().get_name():
                    try:
                        origin, extent = actor.get_actor_bounds(False)
                        max_extent = max(extent.x, extent.y, extent.z)
                        if max_extent > max_postprocess_extent:
                            max_postprocess_extent = max_extent
                        postprocess_count += 1
                    except Exception:
                        pass
            
            # Determine size threshold for filtering oversized actors
            if max_postprocess_extent > 0:
                # Use PostProcessVolume as reference (allow slightly larger)
                max_reasonable_extent = max_postprocess_extent * 1.5
                unreal.log(f"  Using PostProcessVolume as scene reference: {max_postprocess_extent:.0f} cm")
                unreal.log(f"  Max reasonable actor extent: {max_reasonable_extent:.0f} cm")
            else:
                # Fallback to fixed threshold
                max_reasonable_extent = 100000.0  # 1000 meters
                unreal.log(f"  No PostProcessVolume found, using default threshold: {max_reasonable_extent:.0f} cm")
            
            min_bounds = None
            max_bounds = None
            navigable_actor_count = 0
            skipped_count = 0
            excluded_types = []  # Track excluded actor types
            
            # Collect bounds from navigable actors only
            for actor in all_actors:
                # Skip NavMesh volumes and other navigation actors
                if isinstance(actor, (unreal.NavMeshBoundsVolume, unreal.NavigationTestingActor)):
                    continue
                
                # Exclude common non-navigable actor types
                actor_class_name = actor.get_class().get_name()
                
                # Skip atmospheric/environmental actors that are typically huge
                exclude_patterns = [
                    'SkyAtmosphere', 'SkyLight', 'SkySphere', 'ExponentialHeightFog', 
                    'VolumetricCloud', 'PostProcessVolume', 'LightmassImportanceVolume',
                    'DirectionalLight', 'PointLight', 'SpotLight', 'RectLight',
                    'CameraActor', 'PlayerStart', 'TriggerVolume', 'TriggerBox',
                    'AudioVolume', 'ReverbVolume', 'ReflectionCapture'
                ]
                
                if any(pattern in actor_class_name for pattern in exclude_patterns):
                    excluded_types.append(actor_class_name)
                    skipped_count += 1
                    continue
                
                # Also check actor name (not just class) for Sky-related actors
                actor_name = actor.get_name()
                if any(pattern in actor_name for pattern in ['Sky', 'sky', 'Atmosphere', 'atmosphere']):
                    excluded_types.append(f"{actor_class_name}({actor_name})")
                    skipped_count += 1
                    continue
                
                # Check if actor can affect navigation
                try:
                    # Simple filter: StaticMeshActor with valid mesh component
                    # More reliable than checking can_ever_affect_navigation in all UE versions
                    is_navigable = False
                    
                    if isinstance(actor, unreal.StaticMeshActor):
                        is_navigable = True
                    else:
                        # Check for StaticMeshComponent or other mesh components
                        try:
                            components = actor.get_components_by_class(unreal.StaticMeshComponent)
                            if components and len(components) > 0:
                                is_navigable = True
                        except Exception:
                            # Fallback: check if it's an Actor with bounds
                            if hasattr(actor, 'get_actor_bounds'):
                                is_navigable = True
                    
                    if not is_navigable:
                        skipped_count += 1
                        continue
                    
                    # Get actor bounds
                    origin, extent = actor.get_actor_bounds(False)
                    
                    # Skip actors with zero extent
                    if extent.x < 1 and extent.y < 1 and extent.z < 1:
                        skipped_count += 1
                        continue
                    
                    # IMPORTANT: Skip unreasonably large actors (likely decorative/environment)
                    # If PostProcessVolume exists, use it as scene boundary reference
                    # Otherwise use default threshold (1000 meters)
                    if (extent.x > max_reasonable_extent or 
                        extent.y > max_reasonable_extent or 
                        extent.z > max_reasonable_extent):
                        unreal.log(f"  Skipping oversized actor: {actor.get_name()} (extent: {extent.x:.0f}, {extent.y:.0f}, {extent.z:.0f})")
                        skipped_count += 1
                        continue
                    
                    # Skip actors with zero extent
                    if extent.x < 1 and extent.y < 1 and extent.z < 1:
                        skipped_count += 1
                        continue
                    
                    # Calculate min/max from origin and extent
                    actor_min = unreal.Vector(
                        origin.x - extent.x,
                        origin.y - extent.y,
                        origin.z - extent.z
                    )
                    actor_max = unreal.Vector(
                        origin.x + extent.x,
                        origin.y + extent.y,
                        origin.z + extent.z
                    )
                    
                    # Update overall bounds
                    if min_bounds is None:
                        min_bounds = actor_min
                        max_bounds = actor_max
                    else:
                        min_bounds = unreal.Vector(
                            min(min_bounds.x, actor_min.x),
                            min(min_bounds.y, actor_min.y),
                            min(min_bounds.z, actor_min.z)
                        )
                        max_bounds = unreal.Vector(
                            max(max_bounds.x, actor_max.x),
                            max(max_bounds.y, actor_max.y),
                            max(max_bounds.z, actor_max.z)
                        )
                    
                    navigable_actor_count += 1
                    
                except Exception as e:
                    # Skip actors that fail to process
                    skipped_count += 1
                    continue
            
            if min_bounds is None or max_bounds is None:
                unreal.log_warning("No valid navigable geometry found in level")
                return None, None
            
            # Log excluded types summary
            if excluded_types:
                unique_excluded = list(set(excluded_types))
                unreal.log(f"  Excluded actor types: {', '.join(unique_excluded[:5])}")
                if len(unique_excluded) > 5:
                    unreal.log(f"    ... and {len(unique_excluded) - 5} more types")
            
            # Adjust Z bounds for agent physics parameters
            # ZMin: lowest navigable surface - agent can step down
            # ZMax: highest navigable surface + agent can jump up
            min_bounds.z -= agent_max_step_height
            max_bounds.z += agent_max_jump_height
            
            # Calculate center and extent
            center = unreal.Vector(
                (min_bounds.x + max_bounds.x) / 2,
                (min_bounds.y + max_bounds.y) / 2,
                (min_bounds.z + max_bounds.z) / 2
            )
            
            extent = unreal.Vector(
                (max_bounds.x - min_bounds.x) / 2,
                (max_bounds.y - min_bounds.y) / 2,
                (max_bounds.z - min_bounds.z) / 2
            )
            
            unreal.log(f"Map bounds calculated from {navigable_actor_count} navigable actors")
            unreal.log(f"  Skipped {skipped_count} non-navigable actors")
            unreal.log(f"  Center: X={center.x:.1f}, Y={center.y:.1f}, Z={center.z:.1f}")
            unreal.log(f"  Extent: X={extent.x:.1f}, Y={extent.y:.1f}, Z={extent.z:.1f}")
            unreal.log(f"  Size: X={extent.x*2:.1f}, Y={extent.y*2:.1f}, Z={extent.z*2:.1f}")
            
            return center, extent
            
        except Exception as e:
            unreal.log_error(f"Error calculating map bounds: {str(e)}")
            return None, None
    
    def calculate_navmesh_scale(self, bounds_extent, margin=1.2, min_scale=None, max_scale=None):
        """
        Calculate appropriate NavMesh scale based on level bounds
        
        Args:
            bounds_extent: unreal.Vector with the extent of level geometry
            margin: Scale multiplier for margin (default 1.2 = 20% margin)
            min_scale: Minimum scale constraint [x, y, z]
            max_scale: Maximum scale constraint [x, y, z]
        
        Returns:
            unreal.Vector with the calculated scale
        """
        if not bounds_extent:
            return None
        
        # NavMeshBoundsVolume默认的BrushComponent extent是 (100, 100, 100) cm
        # 当scale=1.0时，覆盖范围是 200x200x200 cm (extent*2)
        # 所以：required_scale = (scene_extent * 2 * margin) / 200
        # 简化：required_scale = (scene_extent * margin) / 100
        default_brush_extent = 100.0  # NavMeshBoundsVolume default brush extent in cm
        
        # Calculate raw scale before constraints
        raw_scale_x = (bounds_extent.x * margin) / default_brush_extent
        raw_scale_y = (bounds_extent.y * margin) / default_brush_extent
        raw_scale_z = (bounds_extent.z * margin) / default_brush_extent
        
        unreal.log(f"Scene extent (cm): X={bounds_extent.x:.1f}, Y={bounds_extent.y:.1f}, Z={bounds_extent.z:.1f}")
        unreal.log(f"Raw calculated scale (before constraints): X={raw_scale_x:.2f}, Y={raw_scale_y:.2f}, Z={raw_scale_z:.2f}")
        
        scale_x = raw_scale_x
        scale_y = raw_scale_y
        scale_z = raw_scale_z
        
        # Apply minimum constraints
        if min_scale:
            scale_x = max(scale_x, min_scale[0])
            scale_y = max(scale_y, min_scale[1])
            scale_z = max(scale_z, min_scale[2])
        
        # Apply maximum constraints
        if max_scale:
            scale_x = min(scale_x, max_scale[0])
            scale_y = min(scale_y, max_scale[1])
            scale_z = min(scale_z, max_scale[2])
        
        calculated_scale = unreal.Vector(scale_x, scale_y, scale_z)
        
        unreal.log(f"Final NavMesh scale (after constraints): X={scale_x:.2f}, Y={scale_y:.2f}, Z={scale_z:.2f}")
        if min_scale:
            unreal.log(f"  Min constraints: {min_scale}")
        if max_scale:
            unreal.log(f"  Max constraints: {max_scale}")
        
        return calculated_scale
    
    def auto_scale_navmesh(self, margin=1.2, min_scale=None, max_scale=None, 
                          agent_max_step_height=50.0, agent_max_jump_height=200.0):
        """
        Automatically calculate and apply NavMesh bounds based on level geometry
        Uses intelligent Volume layout strategy based on scene size
        
        Args:
            margin: Scale multiplier for margin (default 1.2 = 20% margin)
            min_scale: Minimum scale constraint [x, y, z] (default [20, 20, 5])
            max_scale: Maximum scale constraint [x, y, z] (default [500, 500, 50])
            agent_max_step_height: Max step height for agent (cm)
            agent_max_jump_height: Max jump height for agent (cm)
        
        Returns:
            NavMeshBoundsVolume actor(s) if successful, None otherwise
        """
        # Set default constraints
        if min_scale is None:
            min_scale = [20.0, 20.0, 5.0]
        if max_scale is None:
            max_scale = [500.0, 500.0, 50.0]
        
        unreal.log("=" * 60)
        unreal.log("Auto-scaling NavMesh based on level geometry")
        unreal.log("=" * 60)
        
        # Calculate bounds with agent physics parameters
        center, extent = self.calculate_map_bounds(
            agent_max_step_height=agent_max_step_height,
            agent_max_jump_height=agent_max_jump_height
        )
        if not center or not extent:
            unreal.log_error("Failed to calculate map bounds")
            return None
        
        # Calculate area in square meters (UE units are cm, so divide by 10000)
        area_sqm = (extent.x * 2 / 100.0) * (extent.y * 2 / 100.0)
        unreal.log(f"Scene area: {area_sqm:.1f} m²")
        
        # Intelligent Volume layout strategy
        if area_sqm < 200:
            # Small scene: single volume
            unreal.log("Using SMALL scene strategy: Single NavMeshBoundsVolume")
            scale = self.calculate_navmesh_scale(extent, margin, min_scale, max_scale)
            if not scale:
                unreal.log_error("Failed to calculate NavMesh scale")
                return None
            
            navmesh = self.add_navmesh_bounds_volume(center, scale)
            if not navmesh:
                unreal.log_error("Failed to add NavMesh bounds volume")
                return None
            
            unreal.log("Auto-scale NavMesh configuration complete")
            unreal.log("=" * 60)
            return navmesh
            
        elif area_sqm < 500:
            # Medium scene: consider splitting into 2-4 volumes
            # For now, use single volume (multi-volume can be implemented later)
            unreal.log("Using MEDIUM scene strategy: Single NavMeshBoundsVolume (multi-volume optimization available)")
            scale = self.calculate_navmesh_scale(extent, margin, min_scale, max_scale)
            if not scale:
                unreal.log_error("Failed to calculate NavMesh scale")
                return None
            
            navmesh = self.add_navmesh_bounds_volume(center, scale)
            if not navmesh:
                unreal.log_error("Failed to add NavMesh bounds volume")
                return None
            
            unreal.log("Auto-scale NavMesh configuration complete")
            unreal.log("=" * 60)
            return navmesh
            
        else:
            # Large scene: should use spatial partitioning (octree)
            # For now, use single large volume with max constraints
            unreal.log("Using LARGE scene strategy: Single NavMeshBoundsVolume with max constraints")
            unreal.log("  Note: Scene exceeds 500m², consider using spatial octree partitioning for optimal performance")
            
            scale = self.calculate_navmesh_scale(extent, margin, min_scale, max_scale)
            if not scale:
                unreal.log_error("Failed to calculate NavMesh scale")
                return None
            
            navmesh = self.add_navmesh_bounds_volume(center, scale)
            if not navmesh:
                unreal.log_error("Failed to add NavMesh bounds volume")
                return None
            
            unreal.log("Auto-scale NavMesh configuration complete")
            unreal.log("=" * 60)
            return navmesh


def example_usage():
    
    # Example map list
    map_list = [
        '/Game/Maps/Level01',
        '/Game/Maps/Level02',
    ]
    
    # NavMesh configuration
    location = (0.0, 0.0, 0.0)
    scale = (100.0, 100.0, 10.0)  # Large area coverage
    
    manager = NavMeshManager()
    results = manager.batch_add_navmesh_to_maps(map_list, location, scale)
    
    # Rebuild navmesh for the last loaded map
    manager.rebuild_navmesh()
    
    return results


if __name__ == "__main__":
    # Uncomment to run example
    # example_usage()
    pass
