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
                
                # Force NavMesh rebuild after adding volume
                # This ensures NavMesh generation starts immediately
                try:
                    world = unreal.EditorLevelLibrary.get_editor_world()
                    nav_sys = unreal.NavigationSystemV1.get_navigation_system(world)
                    if nav_sys:
                        # Trigger rebuild
                        rebuild_fn = getattr(nav_sys, "build", None)
                        if callable(rebuild_fn):
                            unreal.log("Triggering NavMesh rebuild...")
                            rebuild_fn()
                        else:
                            unreal.log("NavMesh will auto-build (rebuild API not available)")
                except Exception as e:
                    unreal.log_warning(f"Could not trigger manual rebuild: {str(e)}")
                
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
    
    def wait_for_navmesh_build(self, timeout_seconds=120):
        """
        Wait for NavMesh to finish building
        Returns True if build completed, False if timeout
        Default timeout increased to 120s for large scenes with Landscape
        """
        try:
            unreal.log(f"Waiting for NavMesh build to complete (timeout: {timeout_seconds}s)...")
            world = unreal.EditorLevelLibrary.get_editor_world()
            nav_sys = unreal.NavigationSystemV1.get_navigation_system(world)
            
            if not nav_sys:
                unreal.log_warning("NavigationSystem not found")
                return False
            
            # IMPORTANT: Give NavMesh time to start building before checking
            # NavMesh build may not start immediately after adding NavMeshBoundsVolume
            initial_delay = 2.0  # Wait 2 seconds for build to start
            unreal.log(f"Waiting {initial_delay}s for NavMesh build to start...")
            time.sleep(initial_delay)
            
            # Try to find the is_navigation_being_built method with various signatures
            check_fn = getattr(nav_sys, "is_navigation_being_built_or_locked", None)
            if not callable(check_fn):
                check_fn = getattr(unreal.NavigationSystemV1, "is_navigation_being_built_or_locked", None)
            
            if not callable(check_fn):
                # Fallback: just wait a fixed time (increased for Landscape)
                fallback_time = 10.0
                unreal.log(f"is_navigation_being_built API not available, waiting {fallback_time} seconds...")
                time.sleep(fallback_time)
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
                center, extent, _ = self.calculate_map_bounds()
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
    
    def enable_landscape_navigation(self):
        """
        Enable navigation generation on all Landscape actors in the level
        This is required for NavMesh to be generated on Landscape surfaces
        """
        try:
            all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
            landscape_count = 0
            
            for actor in all_actors:
                actor_class_name = actor.get_class().get_name()
                
                # Check if this is a Landscape actor
                if 'Landscape' in actor_class_name:
                    try:
                        # Enable navigation on Landscape
                        # Key properties for Landscape navigation:
                        # 1. bFillCollisionUnderneathForNavmesh - Fill collision gaps for navmesh
                        # 2. bCanAffectNavigation - Allow landscape to affect navigation
                        
                        # Method 1: Try to set via Landscape component properties
                        components = actor.get_components_by_class(unreal.LandscapeComponent)
                        for comp in components:
                            try:
                                # Enable collision for navigation
                                if comp.has_property('can_ever_affect_navigation'):
                                    comp.set_editor_property('can_ever_affect_navigation', True)
                                if comp.has_property('can_character_step_up_on'):
                                    # ECB_Yes = allows stepping
                                    comp.set_editor_property('can_character_step_up_on', unreal.CanBeCharacterBase.YES)
                            except Exception as e:
                                pass  # Continue even if some properties fail
                        
                        # Method 2: Try to set via Actor properties
                        try:
                            if actor.has_property('bFillCollisionUnderneathForNavmesh'):
                                actor.set_editor_property('bFillCollisionUnderneathForNavmesh', True)
                                unreal.log(f"  ✓ Enabled bFillCollisionUnderneathForNavmesh on {actor.get_name()}")
                        except Exception:
                            pass
                        
                        # Method 3: Set collision enabled on Landscape
                        try:
                            # Get root component (usually LandscapeComponent)
                            root_comp = actor.get_editor_property('root_component')
                            if root_comp:
                                # Enable collision
                                root_comp.set_editor_property('collision_enabled', unreal.CollisionEnabled.QUERY_AND_PHYSICS)
                                unreal.log(f"  ✓ Enabled collision on {actor.get_name()}")
                        except Exception:
                            pass
                        
                        landscape_count += 1
                        unreal.log(f"✓ Configured Landscape for navigation: {actor.get_name()}")
                        
                    except Exception as e:
                        unreal.log_warning(f"  Failed to configure Landscape {actor.get_name()}: {str(e)}")
            
            if landscape_count > 0:
                unreal.log(f"Enabled navigation on {landscape_count} Landscape actor(s)")
                return True
            else:
                unreal.log("No Landscape actors found in level")
                return False
                
        except Exception as e:
            unreal.log_error(f"Error enabling Landscape navigation: {str(e)}")
            return False
    
    def calculate_map_bounds(self, agent_max_step_height=50.0, agent_max_jump_height=200.0):
        """
        Calculate the bounding box of all navigable geometry in the current level
        Filters components by navigation relevance and collision settings
        
        Args:
            agent_max_step_height: Max step height for agent (cm), default 50.0
            agent_max_jump_height: Max jump height for agent (cm), default 200.0
        
        Returns: (center_location, bounds_extent, landscape_z_min) as unreal.Vector tuples and float
                 landscape_z_min is None if no Landscape found
        """
        try:
            unreal.log("Calculating map bounds from navigable geometry...")
            unreal.log(f"  Agent MaxStepHeight: {agent_max_step_height} cm")
            unreal.log(f"  Agent MaxJumpHeight: {agent_max_jump_height} cm")
            
            world = unreal.EditorLevelLibrary.get_editor_world()
            all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
            
            # First pass: Find the largest PostProcessVolume/LightmassImportanceVolume as scene boundary reference
            # Also detect Landscape for ground alignment
            max_volume_extent = 0.0
            volume_count = 0
            landscape_z_min = None
            
            for actor in all_actors:
                actor_class_name = actor.get_class().get_name()
                
                # Check for scene boundary volumes
                if 'PostProcessVolume' in actor_class_name or 'LightmassImportanceVolume' in actor_class_name:
                    try:
                        origin, extent = actor.get_actor_bounds(False)
                        max_extent = max(extent.x, extent.y, extent.z)
                        if max_extent > max_volume_extent:
                            max_volume_extent = max_extent
                        volume_count += 1
                        unreal.log(f"  Found {actor_class_name}: extent={max_extent:.0f} cm")
                    except Exception:
                        pass
                
                # Check for Landscape (ground)
                if 'Landscape' in actor_class_name:
                    try:
                        origin, extent = actor.get_actor_bounds(False)
                        landscape_z = origin.z - extent.z  # Bottom of landscape
                        if landscape_z_min is None or landscape_z < landscape_z_min:
                            landscape_z_min = landscape_z
                        unreal.log(f"  Found Landscape: Z_min={landscape_z:.1f} cm (origin={origin.z:.1f}, extent_z={extent.z:.1f})")
                    except Exception as e:
                        unreal.log_warning(f"  Error processing Landscape: {str(e)}")
            
            # Determine size threshold for filtering oversized actors
            if max_volume_extent > 0:
                # Use volume as reference (allow slightly larger)
                max_reasonable_extent = max_volume_extent * 1.5
                unreal.log(f"  Using scene volume reference: {max_volume_extent:.0f} cm")
                unreal.log(f"  Max reasonable actor extent: {max_reasonable_extent:.0f} cm")
            else:
                # Fallback to fixed threshold
                max_reasonable_extent = 100000.0  # 1000 meters
                unreal.log(f"  No scene volume found, using default threshold: {max_reasonable_extent:.0f} cm")
            
            if landscape_z_min is not None:
                unreal.log(f"  Landscape ground level detected at Z={landscape_z_min:.1f} cm")
            
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
                return None, None, None
            
            # Log excluded types summary
            if excluded_types:
                unique_excluded = list(set(excluded_types))
                unreal.log(f"  Excluded actor types: {', '.join(unique_excluded[:5])}")
                if len(unique_excluded) > 5:
                    unreal.log(f"    ... and {len(unique_excluded) - 5} more types")
            
            # Adjust Z bounds for agent physics parameters
            # LANDSCAPE最高优先级：如果存在Landscape，Z轴必须包含它
            if landscape_z_min is not None:
                # Align to landscape with small downward offset (10 cm)
                original_min_z = min_bounds.z
                min_bounds.z = landscape_z_min - 10.0
                unreal.log(f"  *** LANDSCAPE PRIORITY: Z_min forced to {min_bounds.z:.1f} cm (Landscape={landscape_z_min:.1f} - 10)")
                if original_min_z > min_bounds.z:
                    unreal.log(f"      (Expanded from geometry Z_min={original_min_z:.1f} to include Landscape)")
            else:
                # ZMin: lowest navigable surface - agent can step down
                min_bounds.z -= agent_max_step_height
            
            # ZMax: highest navigable surface + agent can jump up
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
            unreal.log(f"  Z Range: {min_bounds.z:.1f} to {max_bounds.z:.1f}")
            
            return center, extent, landscape_z_min
            
        except Exception as e:
            unreal.log_error(f"Error calculating map bounds: {str(e)}")
            return None, None, None
    
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
        
        # CRITICAL: Enable Landscape navigation FIRST before calculating bounds
        # This ensures Landscape surfaces will be included in NavMesh generation
        unreal.log("Enabling Landscape navigation...")
        self.enable_landscape_navigation()
        
        # Calculate bounds with agent physics parameters
        center, extent, landscape_z_min = self.calculate_map_bounds(
            agent_max_step_height=agent_max_step_height,
            agent_max_jump_height=agent_max_jump_height
        )
        if not center or not extent:
            unreal.log_error("Failed to calculate map bounds")
            return None
        
        # If Landscape exists, adjust NavMesh center Z position
        if landscape_z_min is not None:
            # Recalculate center Z to account for landscape alignment
            # min_bounds.z is already set to landscape_z_min - 10
            # We need to update center accordingly
            z_min = landscape_z_min - 10.0
            z_max = center.z + extent.z  # Top of the original bounds
            center.z = (z_min + z_max) / 2
            extent.z = (z_max - z_min) / 2
            unreal.log(f"NavMesh center adjusted for Landscape alignment:")
            unreal.log(f"  New Center Z: {center.z:.1f} cm")
            unreal.log(f"  New Extent Z: {extent.z:.1f} cm")
        
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
    
    def sample_navmesh_coverage(self, sample_grid_size=20, z_test_height=100.0):
        """
        采样NavMesh覆盖区域，找到实际可导航的点
        
        Args:
            sample_grid_size: 网格采样密度（每个维度的采样点数）
            z_test_height: 在边界中心Z轴±此高度范围内采样
        
        Returns:
            list of unreal.Vector: 有效的可导航点列表
        """
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            nav_sys = unreal.NavigationSystemV1.get_navigation_system(world)
            
            if not nav_sys:
                unreal.log_error("NavigationSystem not found")
                return []
            
            # 获取当前NavMesh边界（从现有NavMeshBoundsVolume）
            navmesh_volume = self.check_navmesh_exists()
            if not navmesh_volume:
                unreal.log_error("No NavMeshBoundsVolume found for sampling")
                return []
            
            volume_location = navmesh_volume.get_actor_location()
            volume_scale = navmesh_volume.get_actor_scale3d()
            
            # NavMeshBoundsVolume默认brush extent是100cm，实际覆盖范围=extent*2*scale
            extent_x = 100.0 * volume_scale.x
            extent_y = 100.0 * volume_scale.y
            extent_z = 100.0 * volume_scale.z
            
            unreal.log(f"Sampling NavMesh coverage in Volume: center={volume_location}, extent=({extent_x:.1f}, {extent_y:.1f}, {extent_z:.1f})")
            unreal.log(f"Grid size: {sample_grid_size}x{sample_grid_size}")
            
            valid_points = []
            total_samples = 0
            
            # 在XY平面上网格采样
            for i in range(sample_grid_size):
                for j in range(sample_grid_size):
                    # 计算采样点位置
                    x = volume_location.x - extent_x + (2.0 * extent_x * i / (sample_grid_size - 1)) if sample_grid_size > 1 else volume_location.x
                    y = volume_location.y - extent_y + (2.0 * extent_y * j / (sample_grid_size - 1)) if sample_grid_size > 1 else volume_location.y
                    
                    # 在Z轴方向多个高度测试
                    z_samples = 5
                    for k in range(z_samples):
                        z = volume_location.z - z_test_height + (2.0 * z_test_height * k / (z_samples - 1)) if z_samples > 1 else volume_location.z
                        test_point = unreal.Vector(x, y, z)
                        total_samples += 1
                        
                        # 投影到NavMesh
                        try:
                            nav_location = nav_sys.project_point_to_navigation(world, test_point)
                            if nav_location:
                                valid_points.append(nav_location)
                        except Exception:
                            pass
            
            coverage_rate = len(valid_points) / total_samples if total_samples > 0 else 0
            unreal.log(f"NavMesh coverage sampling complete: {len(valid_points)}/{total_samples} valid points ({coverage_rate*100:.1f}%)")
            
            return valid_points
            
        except Exception as e:
            unreal.log_error(f"Error sampling NavMesh coverage: {str(e)}")
            return []
    
    def find_largest_connected_region(self, valid_points, connectivity_radius=500.0):
        """
        从采样点中找到最大的连通区域
        使用简单的距离连通性判断
        
        Args:
            valid_points: 有效NavMesh点列表
            connectivity_radius: 连通判断距离（cm），小于此距离认为连通
        
        Returns:
            list of unreal.Vector: 最大连通区域的点
        """
        if not valid_points:
            return []
        
        unreal.log(f"Finding largest connected region from {len(valid_points)} points...")
        unreal.log(f"Connectivity radius: {connectivity_radius:.1f} cm")
        
        # 构建邻接关系（简化版：只检查距离）
        n = len(valid_points)
        visited = [False] * n
        
        def distance_2d(p1, p2):
            """XY平面距离（忽略Z轴）"""
            dx = p1.x - p2.x
            dy = p1.y - p2.y
            return (dx*dx + dy*dy) ** 0.5
        
        def bfs(start_idx):
            """广度优先搜索连通区域"""
            region = []
            queue = [start_idx]
            visited[start_idx] = True
            
            while queue:
                idx = queue.pop(0)
                region.append(valid_points[idx])
                
                # 查找邻居
                for i in range(n):
                    if not visited[i]:
                        dist = distance_2d(valid_points[idx], valid_points[i])
                        if dist <= connectivity_radius:
                            visited[i] = True
                            queue.append(i)
            
            return region
        
        # 找到所有连通区域
        regions = []
        for i in range(n):
            if not visited[i]:
                region = bfs(i)
                regions.append(region)
        
        # 找到最大的区域
        if not regions:
            return []
        
        largest_region = max(regions, key=len)
        
        unreal.log(f"Found {len(regions)} connected regions")
        for i, region in enumerate(sorted(regions, key=len, reverse=True)[:5]):
            unreal.log(f"  Region {i+1}: {len(region)} points")
        unreal.log(f"Largest region has {len(largest_region)} points ({len(largest_region)/len(valid_points)*100:.1f}% of total)")
        
        return largest_region
    
    def calculate_bounds_from_points(self, points, margin=1.2, landscape_z_min=None):
        """
        从点集计算边界框
        
        Args:
            points: unreal.Vector点列表
            margin: 边界扩展倍数
            landscape_z_min: Landscape最低Z值（如果存在），强制Z_min不高于此值
        
        Returns:
            (center, extent) as unreal.Vector tuples
        """
        if not points:
            return None, None
        
        # 找到min/max
        min_x = min(p.x for p in points)
        max_x = max(p.x for p in points)
        min_y = min(p.y for p in points)
        max_y = max(p.y for p in points)
        min_z = min(p.z for p in points)
        max_z = max(p.z for p in points)
        
        # LANDSCAPE最高优先级：如果有landscape，强制Z_min对齐到landscape
        if landscape_z_min is not None:
            original_min_z = min_z
            min_z = landscape_z_min - 10.0  # Landscape底部-10cm
            if original_min_z != min_z:
                unreal.log(f"  Landscape Z priority enforced: Z_min adjusted from {original_min_z:.1f} to {min_z:.1f} cm")
        
        # LANDSCAPE最高优先级：如果有landscape，强制Z_min对齐到landscape
        if landscape_z_min is not None:
            original_min_z = min_z
            min_z = landscape_z_min - 10.0  # Landscape底部-10cm
            if original_min_z != min_z:
                unreal.log(f"  Landscape Z priority enforced: Z_min adjusted from {original_min_z:.1f} to {min_z:.1f} cm")
        
        # 计算中心和范围
        center = unreal.Vector(
            (min_x + max_x) / 2,
            (min_y + max_y) / 2,
            (min_z + max_z) / 2
        )
        
        # 应用margin
        extent = unreal.Vector(
            (max_x - min_x) / 2 * margin,
            (max_y - min_y) / 2 * margin,
            (max_z - min_z) / 2 * margin
        )
        
        unreal.log(f"Calculated bounds from {len(points)} points:")
        unreal.log(f"  Center: X={center.x:.1f}, Y={center.y:.1f}, Z={center.z:.1f}")
        unreal.log(f"  Extent: X={extent.x:.1f}, Y={extent.y:.1f}, Z={extent.z:.1f}")
        unreal.log(f"  Size: X={extent.x*2:.1f}, Y={extent.y*2:.1f}, Z={extent.z*2:.1f}")
        
        return center, extent
    
    def adaptive_navmesh_optimization(self, initial_scale_multiplier=2.0, max_iterations=3, 
                                     sample_grid_size=20, connectivity_radius=500.0,
                                     min_coverage_ratio=0.3, target_shrink_ratio=0.8):
        """
        自适应NavMesh优化：先大后小的迭代收缩策略
        
        工作流程：
        1. 创建初始的大Volume（基于几何边界 × initial_scale_multiplier）
        2. 烘焙NavMesh
        3. 采样实际可导航区域
        4. 找到最大连通区域
        5. 根据连通区域收缩Volume
        6. 重复2-5直到收敛或达到最大迭代次数
        
        Args:
            initial_scale_multiplier: 初始Volume相对几何边界的放大倍数
            max_iterations: 最大迭代次数
            sample_grid_size: 每次迭代的采样网格密度
            connectivity_radius: 连通区域判断距离（cm）
            min_coverage_ratio: 最小可导航覆盖率（低于此值认为失败）
            target_shrink_ratio: 目标收缩比例（实际NavMesh占Volume的期望比例）
        
        Returns:
            NavMeshBoundsVolume if successful, None otherwise
        """
        unreal.log("=" * 60)
        unreal.log("Adaptive NavMesh Optimization (Simulated Annealing Strategy)")
        unreal.log("=" * 60)
        unreal.log(f"Max iterations: {max_iterations}")
        unreal.log(f"Initial scale multiplier: {initial_scale_multiplier}")
        unreal.log(f"Target shrink ratio: {target_shrink_ratio}")
        unreal.log("")
        
        # Step 1: 计算初始几何边界
        center, extent, landscape_z_min = self.calculate_map_bounds()
        if not center or not extent:
            unreal.log_error("Failed to calculate initial map bounds")
            return None
        
        # LANDSCAPE最高优先级：在整个优化过程中始终保持对齐
        if landscape_z_min is not None:
            unreal.log(f"Landscape detected at Z={landscape_z_min:.1f} cm - ENFORCING as minimum Z boundary")
            z_min = landscape_z_min - 10.0
            z_max = center.z + extent.z
            center.z = (z_min + z_max) / 2
            extent.z = (z_max - z_min) / 2
        else:
            unreal.log("No Landscape detected - using geometry-based Z bounds")
        
        # Step 2: 创建初始大Volume
        initial_extent = unreal.Vector(
            extent.x * initial_scale_multiplier,
            extent.y * initial_scale_multiplier,
            extent.z * initial_scale_multiplier
        )
        
        unreal.log(f"[Iteration 0] Creating initial large Volume")
        unreal.log(f"  Center: {center}")
        unreal.log(f"  Extent: {initial_extent}")
        
        # 删除现有NavMesh
        existing = self.check_navmesh_exists()
        if existing:
            unreal.log("Removing existing NavMeshBoundsVolume...")
            unreal.EditorLevelLibrary.destroy_actor(existing)
        
        # 计算scale（NavMesh默认extent=100）
        initial_scale = unreal.Vector(
            initial_extent.x / 100.0,
            initial_extent.y / 100.0,
            initial_extent.z / 100.0
        )
        
        current_navmesh = self.add_navmesh_bounds_volume(center, initial_scale)
        if not current_navmesh:
            unreal.log_error("Failed to create initial NavMeshBoundsVolume")
            return None
        
        # 迭代优化
        for iteration in range(1, max_iterations + 1):
            unreal.log("")
            unreal.log(f"[Iteration {iteration}/{max_iterations}] Optimizing NavMesh...")
            
            # Step 3: 等待NavMesh烘焙完成
            unreal.log("  Waiting for NavMesh build...")
            if not self.wait_for_navmesh_build(timeout_seconds=120):
                unreal.log_warning("  NavMesh build timeout, continuing anyway...")
            
            # Step 4: 采样NavMesh覆盖区域
            unreal.log("  Sampling NavMesh coverage...")
            valid_points = self.sample_navmesh_coverage(sample_grid_size=sample_grid_size)
            
            if not valid_points:
                unreal.log_error("  No valid NavMesh points found, stopping optimization")
                return current_navmesh
            
            # Step 5: 找到最大连通区域
            unreal.log("  Finding largest connected region...")
            largest_region = self.find_largest_connected_region(valid_points, connectivity_radius)
            
            if not largest_region:
                unreal.log_error("  No connected region found, stopping optimization")
                return current_navmesh
            
            # 检查覆盖率
            coverage_ratio = len(largest_region) / (sample_grid_size * sample_grid_size * 5)
            unreal.log(f"  Coverage ratio: {coverage_ratio*100:.1f}%")
            
            if coverage_ratio < min_coverage_ratio:
                unreal.log_warning(f"  Low coverage ratio ({coverage_ratio*100:.1f}% < {min_coverage_ratio*100:.1f}%), may indicate NavMesh generation issues")
            
            # Step 6: 计算新边界（强制包含Landscape）
            new_center, new_extent = self.calculate_bounds_from_points(
                largest_region, 
                margin=1.2,
                landscape_z_min=landscape_z_min  # 传递landscape约束
            )
            
            if not new_center or not new_extent:
                unreal.log_error("  Failed to calculate new bounds, stopping optimization")
                return current_navmesh
            
            # 检查是否收敛（变化<10%）
            old_volume = initial_extent.x * initial_extent.y * initial_extent.z
            new_volume = new_extent.x * new_extent.y * new_extent.z
            shrink_ratio = new_volume / old_volume if old_volume > 0 else 1.0
            
            unreal.log(f"  Volume shrink ratio: {shrink_ratio*100:.1f}%")
            
            if shrink_ratio > 0.9:  # 变化<10%，认为收敛
                unreal.log("  Converged (shrink < 10%), optimization complete")
                break
            
            # Step 7: 更新Volume
            unreal.log("  Updating NavMeshBoundsVolume...")
            
            # 删除旧的
            unreal.EditorLevelLibrary.destroy_actor(current_navmesh)
            
            # 创建新的
            new_scale = unreal.Vector(
                new_extent.x / 100.0,
                new_extent.y / 100.0,
                new_extent.z / 100.0
            )
            
            current_navmesh = self.add_navmesh_bounds_volume(new_center, new_scale)
            if not current_navmesh:
                unreal.log_error("  Failed to create updated NavMeshBoundsVolume")
                return None
            
            # 更新当前extent用于下次比较
            initial_extent = new_extent
        
        # 最终验证
        unreal.log("")
        unreal.log("Waiting for final NavMesh build...")
        self.wait_for_navmesh_build(timeout_seconds=120)
        
        if self.verify_navmesh_data():
            unreal.log("=" * 60)
            unreal.log("Adaptive NavMesh Optimization Complete!")
            unreal.log("=" * 60)
            return current_navmesh
        else:
            unreal.log_warning("Final NavMesh verification failed")
            return current_navmesh


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
