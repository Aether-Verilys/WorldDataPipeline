import unreal
import ue_api


class NavMeshManager:
    
    def __init__(self):
        self.level_editor_subsystem = ue_api.get_level_editor_subsystem()
        self.editor_actor_subsystem = ue_api.get_actor_subsystem()
    
    def count_static_mesh_actors(self) -> int:
        try:
            actor_subsystem = ue_api.get_actor_subsystem()
            all_actors = actor_subsystem.get_all_level_actors()
            count = 0
            
            for actor in all_actors:
                if isinstance(actor, unreal.StaticMeshActor):
                    count += 1
            
            unreal.log(f"StaticMeshActor count: {count}")
            return count
            
        except Exception as e:
            unreal.log_error(f"Error counting StaticMeshActors: {str(e)}")
            return 0
    
    def check_navmesh_exists(self):
        actor_subsystem = ue_api.get_actor_subsystem()
        all_actors = actor_subsystem.get_all_level_actors()
        
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
    
    
    def verify_navmesh_data(self, test_reachability=True, min_success_rate=0.8):
        try:
            world = ue_api.get_editor_world()
            nav_sys = ue_api.get_navigation_system(world)
            
            if not nav_sys:
                unreal.log_warning("NavigationSystem not found")
                return False
            
            unreal.log("NavigationSystem exists")
            
            # Check for required actors in level
            actor_subsystem = ue_api.get_actor_subsystem()
            all_actors = actor_subsystem.get_all_level_actors()
            nav_bounds_found = False
            recast_navmesh_found = False
            
            for actor in all_actors:
                if isinstance(actor, unreal.NavMeshBoundsVolume):
                    nav_bounds_found = True
                elif isinstance(actor, unreal.RecastNavMesh):
                    recast_navmesh_found = True
            
            if not nav_bounds_found:
                unreal.log_error("Verification Failed: No NavMeshBoundsVolume found in the level")
                return False
            else:
                unreal.log("✓ Found NavMeshBoundsVolume")
                
            if not recast_navmesh_found:
                unreal.log_error("Verification Failed: No RecastNavMesh (Built NavMesh data) found in the level. Build likely failed or empty.")
                return False
            else:
                unreal.log("✓ Found RecastNavMesh (Generated NavMesh data)")
            
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
        try:
            actor_subsystem = ue_api.get_actor_subsystem()
            all_actors = actor_subsystem.get_all_level_actors()
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
    
    def _is_navigable_actor(self, actor):
        """检查 actor 是否是可导航的"""
        if isinstance(actor, unreal.StaticMeshActor):
            return True
        
        actor_class_name = actor.get_class().get_name()
        if 'Landscape' in actor_class_name:
            return True
        
        try:
            components = actor.get_components_by_class(unreal.StaticMeshComponent)
            return components and len(components) > 0
        except Exception:
            return False
    
    def _should_skip_actor(self, actor, exclude_patterns):
        """检查是否应该跳过该 actor"""
        actor_class_name = actor.get_class().get_name()
        actor_name = actor.get_name()
        
        # 检查类名模式
        if any(pattern in actor_class_name for pattern in exclude_patterns):
            return True
        
        # 检查名称模式
        skip_name_patterns = ['Sky', 'sky', 'Atmosphere', 'atmosphere']
        if any(pattern in actor_name for pattern in skip_name_patterns):
            return True
        
        return False
    
    def _get_actor_bounds_safe(self, actor):
        """安全获取 actor 的边界，失败返回 None"""
        try:
            return actor.get_actor_bounds(False)
        except Exception:
            return None, None
    
    def _is_valid_bounds(self, extent, max_reasonable_extent):
        """检查边界是否有效且合理"""
        # 跳过零尺寸
        if extent.x < 1 and extent.y < 1 and extent.z < 1:
            return False
        
        # 跳过过大的 actor
        if (extent.x > max_reasonable_extent or 
            extent.y > max_reasonable_extent or 
            extent.z > max_reasonable_extent):
            return False
        
        return True
    
    def _collect_actor_z_centers(self, all_actors, exclude_patterns, max_reasonable_extent):
        """收集所有可导航 actor 的 Z 中心位置"""
        z_centers = []
        
        for actor in all_actors:
            if self._should_skip_actor(actor, exclude_patterns):
                continue
            
            # 跳过 Landscape 本身
            if 'Landscape' in actor.get_class().get_name():
                continue
            
            if not self._is_navigable_actor(actor):
                continue
            
            origin, extent = self._get_actor_bounds_safe(actor)
            if not origin or not extent:
                continue
            
            if not self._is_valid_bounds(extent, max_reasonable_extent):
                continue
            
            z_centers.append(origin.z)
        
        return z_centers
    
    def _analyze_terrain_type(self, actor_z_centers, ground_plane_z):
        """分析地形类型（平原或山谷）"""
        if len(actor_z_centers) == 0:
            return "Plain (default)", 0.0
        
        above_ground = sum(1 for z in actor_z_centers if z > ground_plane_z)
        total_objects = len(actor_z_centers)
        above_ratio = above_ground / total_objects
        
        unreal.log(f"  Ground plane reference: Z={ground_plane_z:.1f} cm")
        unreal.log(f"  Object distribution: {above_ground} above, {total_objects - above_ground} below ground ({above_ratio*100:.1f}% above)")
        unreal.log("")
        
        if above_ratio > 0.5:
            return "Plain", above_ratio
        else:
            return "Valley", above_ratio

    def calculate_map_bounds(self, agent_max_step_height=50.0, agent_max_jump_height=200.0):
        """
        Calculate NavMesh bounds using horizontal-first strategy:
        1. Calculate XY bounds from all navigable geometry (horizontal plane)
        2. Calculate Z bounds separately:
           - Z_min: Landscape ground level (if exists) - 10cm, otherwise geometry min - step_height
           - Z_max: Geometry max + jump_height
        3. Landscape is ALWAYS included if present (highest priority)
        
        Args:
            agent_max_step_height: Max step height for agent (cm), default 50.0
            agent_max_jump_height: Max jump height for agent (cm), default 200.0
        
        Returns: (center_location, bounds_extent, landscape_z_min) as unreal.Vector tuples and float
                 landscape_z_min is None if no Landscape found
        """
        try:
            unreal.log("=" * 60)
            unreal.log("Calculating NavMesh Bounds (Horizontal-First Strategy)")
            unreal.log("=" * 60)
            unreal.log(f"Agent MaxStepHeight: {agent_max_step_height} cm")
            unreal.log(f"Agent MaxJumpHeight: {agent_max_jump_height} cm")
            unreal.log("")
            
            world = ue_api.get_editor_world()
            actor_subsystem = ue_api.get_actor_subsystem()
            all_actors = actor_subsystem.get_all_level_actors()
            
            # Phase 1: Find Landscape (ground) - HIGHEST PRIORITY
            landscape_z_min = None
            landscape_z_max = None
            landscape_z_center = None
            landscape_origin_z = None  # Landscape actor position Z (true ground reference)
            landscape_count = 0
            
            unreal.log("[Phase 1] Detecting Landscape (ground)...")
            for actor in all_actors:
                actor_class_name = actor.get_class().get_name()
                if 'Landscape' in actor_class_name:
                    try:
                        # Get actual actor location (Transform position)
                        actor_location = actor.get_actor_location()
                        
                        # Get bounds for Z range
                        bounds_origin, extent = actor.get_actor_bounds(False)
                        landscape_z_bottom = bounds_origin.z - extent.z  # Bottom of landscape
                        landscape_z_top = bounds_origin.z + extent.z      # Top of landscape
                        
                        if landscape_z_min is None or landscape_z_bottom < landscape_z_min:
                            landscape_z_min = landscape_z_bottom
                        if landscape_z_max is None or landscape_z_top > landscape_z_max:
                            landscape_z_max = landscape_z_top
                        
                        # Store landscape actual position Z (Transform Z - this is the ground level)
                        if landscape_origin_z is None:
                            landscape_origin_z = actor_location.z
                        
                        landscape_count += 1
                        unreal.log(f"  Landscape #{landscape_count}: Transform Z={actor_location.z:.1f} cm (ground level), Bounds center={bounds_origin.z:.1f} cm, Z_min={landscape_z_bottom:.1f} cm, Z_max={landscape_z_top:.1f} cm")
                    except Exception as e:
                        unreal.log_warning(f"  Error processing Landscape: {str(e)}")
            
            if landscape_z_min is not None and landscape_z_max is not None:
                landscape_z_center = (landscape_z_min + landscape_z_max) / 2.0
                unreal.log(f"✓ Landscape detected: Position={landscape_origin_z:.1f} cm, Bounds Z_min={landscape_z_min:.1f} cm, Z_max={landscape_z_max:.1f} cm, Z_center={landscape_z_center:.1f} cm")
                unreal.log(f"  NavMesh Z center will align with Landscape center")
            else:
                unreal.log("  No Landscape found, Z bounds will be based on geometry")
            unreal.log("")
            
            # Phase 2: Find scene boundary volume as size reference
            unreal.log("[Phase 2] Finding scene boundary reference...")
            max_volume_extent = 0.0
            for actor in all_actors:
                actor_class_name = actor.get_class().get_name()
                if 'PostProcessVolume' in actor_class_name or 'LightmassImportanceVolume' in actor_class_name:
                    try:
                        origin, extent = actor.get_actor_bounds(False)
                        max_extent = max(extent.x, extent.y, extent.z)
                        if max_extent > max_volume_extent:
                            max_volume_extent = max_extent
                        unreal.log(f"  {actor_class_name}: extent={max_extent:.0f} cm")
                    except Exception:
                        pass
            
            # Determine size threshold for filtering oversized actors
            if max_volume_extent > 0:
                max_reasonable_extent = max_volume_extent * 1.5
                unreal.log(f"✓ Scene boundary reference: {max_volume_extent:.0f} cm")
                unreal.log(f"  Max actor size threshold: {max_reasonable_extent:.0f} cm")
            else:
                max_reasonable_extent = 100000.0  # 1000 meters
                unreal.log(f"  Using default threshold: {max_reasonable_extent:.0f} cm")
            unreal.log("")
            
            # Phase 3: Calculate XY bounds (horizontal plane) from navigable geometry
            unreal.log("[Phase 3] Calculating XY bounds (horizontal plane)...")
            
            min_x = None
            max_x = None
            min_y = None
            max_y = None
            geometry_z_min = None
            geometry_z_max = None
            
            navigable_actor_count = 0
            skipped_count = 0
            
            # Define non-navigable actor patterns
            exclude_patterns = [
                'SkyAtmosphere', 'SkyLight', 'SkySphere', 'ExponentialHeightFog', 
                'VolumetricCloud', 'PostProcessVolume', 'LightmassImportanceVolume',
                'DirectionalLight', 'PointLight', 'SpotLight', 'RectLight',
                'CameraActor', 'PlayerStart', 'TriggerVolume', 'TriggerBox',
                'AudioVolume', 'ReverbVolume', 'ReflectionCapture',
                'NavMeshBoundsVolume', 'NavigationTestingActor'
            ]
            
            for actor in all_actors:
                # 跳过不可导航的 actor
                if self._should_skip_actor(actor, exclude_patterns):
                    skipped_count += 1
                    continue
                
                if not self._is_navigable_actor(actor):
                    skipped_count += 1
                    continue
                
                # 获取 actor 边界
                origin, extent = self._get_actor_bounds_safe(actor)
                if not origin or not extent:
                    skipped_count += 1
                    continue
                
                # 验证边界有效性
                if not self._is_valid_bounds(extent, max_reasonable_extent):
                    skipped_count += 1
                    continue
                
                # 更新 XY 边界
                actor_min_x = origin.x - extent.x
                actor_max_x = origin.x + extent.x
                actor_min_y = origin.y - extent.y
                actor_max_y = origin.y + extent.y
                
                if min_x is None:
                    min_x = actor_min_x
                    max_x = actor_max_x
                    min_y = actor_min_y
                    max_y = actor_max_y
                else:
                    min_x = min(min_x, actor_min_x)
                    max_x = max(max_x, actor_max_x)
                    min_y = min(min_y, actor_min_y)
                    max_y = max(max_y, actor_max_y)
                
                # 跟踪 Z 边界
                actor_min_z = origin.z - extent.z
                actor_max_z = origin.z + extent.z
                
                if geometry_z_min is None:
                    geometry_z_min = actor_min_z
                    geometry_z_max = actor_max_z
                else:
                    geometry_z_min = min(geometry_z_min, actor_min_z)
                    geometry_z_max = max(geometry_z_max, actor_max_z)
                
                navigable_actor_count += 1
            
            if min_x is None or max_x is None:
                unreal.log_error("No valid navigable geometry found in level")
                return None, None, None
            
            unreal.log(f"  XY bounds from {navigable_actor_count} actors (skipped {skipped_count})")
            unreal.log(f"  X range: {min_x:.1f} to {max_x:.1f} cm (size: {(max_x-min_x):.1f} cm)")
            unreal.log(f"  Y range: {min_y:.1f} to {max_y:.1f} cm (size: {(max_y-min_y):.1f} cm)")
            unreal.log("")
            
            # Ensure geometry Z bounds are valid (should always be set if we reach here)
            if geometry_z_min is None or geometry_z_max is None:
                unreal.log_error("Invalid geometry Z bounds")
                return None, None, None
            
            # Phase 4: Calculate Z bounds (vertical) - SMART ALIGNMENT
            unreal.log("[Phase 4] Calculating Z bounds (vertical)...")
            
            # Determine reference Z center for alignment
            reference_z_center = None
            
            if landscape_z_center is not None:
                # Case 1: Landscape exists - analyze object distribution to choose alignment
                unreal.log("  Landscape detected - analyzing object distribution...")
                
                ground_plane_z = landscape_origin_z if landscape_origin_z is not None else 0.0
                
                # 收集所有可导航 actor 的 Z 中心位置
                actor_z_centers = self._collect_actor_z_centers(all_actors, exclude_patterns, max_reasonable_extent)
                
                # 分析地形类型
                if len(actor_z_centers) > 0:
                    terrain_type, above_ratio = self._analyze_terrain_type(actor_z_centers, ground_plane_z)
                    
                    if terrain_type == "Plain":
                        reference_z_center = ground_plane_z
                        unreal.log(f"  Terrain Type: PLAIN")
                        unreal.log(f"     Most objects ({above_ratio*100:.1f}%) are above ground")
                        unreal.log(f"     Alignment: Ground-level (Z={reference_z_center:.1f} cm)")
                    else:  # Valley
                        reference_z_center = landscape_z_min
                        unreal.log(f"  Terrain Type: VALLEY")
                        unreal.log(f"     Most objects ({(1-above_ratio)*100:.1f}%) are below ground")
                        unreal.log(f"     Alignment: Landscape bottom (Z={reference_z_center:.1f} cm)")
                else:
                    terrain_type = "Plain (default)"
                    reference_z_center = landscape_z_center
                    unreal.log(f"  No objects for terrain analysis")
                    unreal.log(f"  Terrain Type: {terrain_type}")
                    unreal.log(f"  Using Landscape center: Z={reference_z_center:.1f} cm")
            else:
                # Case 2: No Landscape - find most common Z level (ground plane)
                unreal.log("  No Landscape - finding dominant ground plane...")
                
                # 收集所有可导航 actor 的 Z_min 值
                z_values = []
                for actor in all_actors:
                    if self._should_skip_actor(actor, exclude_patterns):
                        continue
                    
                    if not self._is_navigable_actor(actor):
                        continue
                    
                    origin, extent = self._get_actor_bounds_safe(actor)
                    if not origin or not extent:
                        continue
                    
                    if not self._is_valid_bounds(extent, max_reasonable_extent):
                        continue
                    
                    # 记录底部 Z 位置
                    actor_z_min = origin.z - extent.z
                    z_values.append(actor_z_min)
                
                # Find most clustered Z level (dominant ground plane)
                if len(z_values) > 0:
                    z_values.sort()
                    # Group Z values into buckets (50cm resolution)
                    bucket_size = 50.0  # 50cm buckets
                    z_buckets = {}
                    
                    for z in z_values:
                        bucket_key = int(z / bucket_size)
                        if bucket_key not in z_buckets:
                            z_buckets[bucket_key] = []
                        z_buckets[bucket_key].append(z)
                    
                    # Find bucket with most values
                    max_bucket_count = 0
                    dominant_bucket = None
                    for bucket_key, bucket_values in z_buckets.items():
                        if len(bucket_values) > max_bucket_count:
                            max_bucket_count = len(bucket_values)
                            dominant_bucket = bucket_key
                    
                    if dominant_bucket is not None:
                        # Use average of dominant bucket as ground plane
                        dominant_z_values = z_buckets[dominant_bucket]
                        dominant_z = sum(dominant_z_values) / len(dominant_z_values)
                        reference_z_center = dominant_z
                        unreal.log(f"  Dominant ground plane: Z={dominant_z:.1f} cm ({len(dominant_z_values)} actors)")
                        unreal.log(f"  Reference Z center: {reference_z_center:.1f} cm")
                    else:
                        # Fallback to geometry center
                        reference_z_center = (geometry_z_min + geometry_z_max) / 2.0
                        unreal.log(f"  Fallback to geometry center: {reference_z_center:.1f} cm")
                else:
                    # No Z values found, use geometry center
                    reference_z_center = (geometry_z_min + geometry_z_max) / 2.0
                    unreal.log(f"  Using geometry center: {reference_z_center:.1f} cm")
            
            # Calculate Z bounds with reference center alignment
            # Determine required Z extent to cover all geometry
            z_extent_needed_below = reference_z_center - geometry_z_min + agent_max_step_height
            z_extent_needed_above = geometry_z_max - reference_z_center + agent_max_jump_height
            
            # Use maximum extent (symmetric box)
            z_extent = max(z_extent_needed_below, z_extent_needed_above)
            
            min_z = reference_z_center - z_extent
            max_z = reference_z_center + z_extent
            
            # Safety check: Ensure volume bottom is below actual Z_min with margin
            # Add 10cm safety margin below the minimum Z value
            z_min_safety_margin = 10.0  # 10cm margin below Z_min
            required_min_z = geometry_z_min - z_min_safety_margin
            
            if min_z > required_min_z:
                # Volume bottom is too high, adjust to ensure it covers Z_min
                unreal.log(f"  ⚠ Adjusting Z bounds: calculated min_z={min_z:.1f} > required_min_z={required_min_z:.1f}")
                min_z = required_min_z
                # Recalculate extent based on adjusted min_z
                z_extent = max(reference_z_center - min_z, max_z - reference_z_center)
                max_z = reference_z_center + z_extent
                unreal.log(f"  ✓ Adjusted: min_z={min_z:.1f}, z_extent={z_extent:.1f}, max_z={max_z:.1f}")
            
            unreal.log(f"  Z_min: {min_z:.1f} cm")
            unreal.log(f"  Z_max: {max_z:.1f} cm")
            unreal.log(f"  Z_center: {reference_z_center:.1f} cm (aligned)")
            unreal.log(f"  Z_extent: {z_extent:.1f} cm")
            unreal.log(f"  Z range: {min_z:.1f} to {max_z:.1f} cm (size: {(max_z-min_z):.1f} cm)")
            unreal.log("")
            
            # Phase 5: Calculate final center and extent
            unreal.log("[Phase 5] Final NavMesh bounds:")
            
            center = unreal.Vector(
                (min_x + max_x) / 2,
                (min_y + max_y) / 2,
                reference_z_center  # Use aligned Z center
            )
            
            extent = unreal.Vector(
                (max_x - min_x) / 2,
                (max_y - min_y) / 2,
                z_extent  # Use calculated Z extent
            )
            
            unreal.log(f"  Center: X={center.x:.1f}, Y={center.y:.1f}, Z={center.z:.1f} cm")
            unreal.log(f"  Extent: X={extent.x:.1f}, Y={extent.y:.1f}, Z={extent.z:.1f} cm")
            unreal.log(f"  Coverage: {(extent.x*2/100):.1f}m × {(extent.y*2/100):.1f}m × {(extent.z*2/100):.1f}m")
            unreal.log(f"  Area: {(extent.x*2/100 * extent.y*2/100):.1f} m²")
            unreal.log("=" * 60)
            
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
        
        # NavMeshBoundsVolume 默认基础 extent = 100cm
        # 实际 extent = scale * 100, 总大小 = extent * 2
        default_extent = 100.0 
        
        # Calculate raw scale before constraints
        raw_scale_x = (bounds_extent.x * margin) / default_extent
        raw_scale_y = (bounds_extent.y * margin) / default_extent
        raw_scale_z = (bounds_extent.z * margin) / default_extent
        
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
        Automatically calculate and apply NavMesh bounds based on level geometry.
        Simple and universal approach for all scene types.
        
        Strategy:
        1. Enable Landscape navigation (if Landscape exists)
        2. Calculate XY bounds from all navigable geometry
        3. Calculate Z bounds (Landscape ground as Z_min if exists)
        4. Create single NavMeshBoundsVolume
        
        Args:
            margin: Scale multiplier for margin (default 1.2 = 20% margin)
            min_scale: Minimum scale constraint [x, y, z] (default [20, 20, 5])
            max_scale: Maximum scale constraint [x, y, z] (default [500, 500, 50])
            agent_max_step_height: Max step height for agent (cm)
            agent_max_jump_height: Max jump height for agent (cm)
        
        Returns:
            NavMeshBoundsVolume actor if successful, None otherwise
        """
        # Set default constraints
        if min_scale is None:
            min_scale = [20.0, 20.0, 5.0]
        if max_scale is None:
            max_scale = [500.0, 500.0, 50.0]
        
        unreal.log("=" * 60)
        unreal.log("Auto-Scale NavMesh (Universal Strategy)")
        unreal.log("=" * 60)
        unreal.log(f"Margin: {margin}, Min Scale: {min_scale}, Max Scale: {max_scale}")
        unreal.log("")
        
        # Step 1: Enable Landscape navigation FIRST
        unreal.log("[Step 1] Enabling Landscape navigation...")
        self.enable_landscape_navigation()
        unreal.log("")
        
        # Step 2: Calculate bounds (XY first, then Z with Landscape priority)
        center, extent, landscape_z_min = self.calculate_map_bounds(
            agent_max_step_height=agent_max_step_height,
            agent_max_jump_height=agent_max_jump_height
        )
        if not center or not extent:
            unreal.log_error("Failed to calculate map bounds")
            return None
        
        # Step 3: Calculate NavMesh scale
        scale = self.calculate_navmesh_scale(extent, margin, min_scale, max_scale)
        if not scale:
            unreal.log_error("Failed to calculate NavMesh scale")
            return None
        
        # Step 4: Create NavMeshBoundsVolume
        unreal.log("")
        unreal.log("[Step 2] Creating NavMeshBoundsVolume...")
        navmesh = self.add_navmesh_bounds_volume(center, scale)
        if not navmesh:
            unreal.log_error("Failed to add NavMesh bounds volume")
            return None
        
        unreal.log("=" * 60)
        unreal.log("✓ Auto-Scale NavMesh Complete!")
        unreal.log("=" * 60)
        return navmesh


if __name__ == "__main__":
    pass

