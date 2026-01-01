actor_guid (Guid): [Read-Write] The GUID for this actor; this guid will be the same for actors from instanced streaming levels. see: ActorInstanceGuid, FActorInstanceGuidMapper note: Don’t use VisibleAnywhere here to avoid getting the CPF_Edit flag and get this property reset when resetting to defaults. See FActorDetails::AddActorCategory and EditorUtilities::CopySingleProperty for details.

actor_instance_guid (Guid): [Read-Write] The instance GUID for this actor; this guid will be unique for actors from instanced streaming levels. see: ActorGuid note: This is not guaranteed to be valid during PostLoad, but safe to access from RegisterAllComponents.

allow_tick_before_begin_play (bool): [Read-Write] Whether we allow this Actor to tick before it receives the BeginPlay event. Normally we don’t tick actors until after BeginPlay; this setting allows this behavior to be overridden. This Actor must be able to tick for this setting to be relevant.

always_relevant (bool): [Read-Write] Always relevant for network (overrides bOnlyRelevantToOwner).

async_physics_tick_enabled (bool): [Read-Write] Whether to use use the async physics tick with this actor.

auto_destroy_when_finished (bool): [Read-Write] If true then destroy self when “finished”, meaning all relevant components report that they are done and no timelines or timers are in flight.

auto_receive_input (AutoReceiveInput): [Read-Write] Automatically registers this actor to receive input from a player.

block_input (bool): [Read-Write] If true, all input on the stack below this actor will not be considered

brush_builder (BrushBuilder): [Read-Only]

brush_component (BrushComponent): [Read-Only]

brush_type (BrushType): [Read-Write] Type of brush

call_pre_replication (bool): [Read-Write]

call_pre_replication_for_replay (bool): [Read-Write]

can_be_damaged (bool): [Read-Write] Whether this actor can take damage. Must be true for damage events (e.g. ReceiveDamage()) to be called. see: https://www.unrealengine.com/blog/damage-in-ue4 see: TakeDamage(), ReceiveDamage()

can_be_in_cluster (bool): [Read-Write] If true, this actor can be put inside of a GC Cluster to improve Garbage Collection performance

content_bundle_guid (Guid): [Read-Write] The GUID for this actor’s content bundle.

custom_time_dilation (float): [Read-Write] Allow each actor to run at a different time speed. The DeltaTime for a frame is multiplied by the global TimeDilation (in WorldSettings) and this CustomTimeDilation for this actor’s tick.

data_layer_assets (Array[DataLayerAsset]): [Read-Write] DataLayers assets the actor belongs to.

data_layers (Array[ActorDataLayer]): [Read-Only] DataLayers the actor belongs to.

default_update_overlaps_method_during_level_streaming (ActorUpdateOverlapsMethod): [Read-Only] Default value taken from config file for this class when ‘UseConfigDefault’ is chosen for ‘UpdateOverlapsMethodDuringLevelStreaming’. This allows a default to be chosen per class in the matching config. For example, for Actor it could be specified in DefaultEngine.ini as:

[/Script/Engine.Actor] DefaultUpdateOverlapsMethodDuringLevelStreaming = OnlyUpdateMovable

Another subclass could set their default to something different, such as:

[/Script/Engine.BlockingVolume] DefaultUpdateOverlapsMethodDuringLevelStreaming = NeverUpdate see: UpdateOverlapsMethodDuringLevelStreaming

display_shaded_volume (bool): [Read-Write] If true, display the brush with a shaded volume

enable_auto_lod_generation (bool): [Read-Write] Whether this actor should be considered or not during HLOD generation.

external_data_layer_asset (ExternalDataLayerAsset): [Read-Only]

find_camera_component_when_view_target (bool): [Read-Write] If true, this actor should search for an owned camera component to view through when used as a view target.

generate_overlap_events_during_level_streaming (bool): [Read-Write] If true, this actor will generate overlap Begin/End events when spawned as part of level streaming, which includes initial level load. You might enable this is in the case where a streaming level loads around an actor and you want Begin/End overlap events to trigger. see: UpdateOverlapsMethodDuringLevelStreaming

hidden (bool): [Read-Write] Allows us to only see this Actor in the Editor, and not in the actual game. see: SetActorHiddenInGame()

hlod_layer (HLODLayer): [Read-Write] The UHLODLayer in which this actor should be included.

ignores_origin_shifting (bool): [Read-Write] Whether this actor should not be affected by world origin shifting.

initial_life_span (float): [Read-Write] How long this Actor lives before dying, 0=forever. Note this is the INITIAL value and should not be modified once play has begun.

input_priority (int32): [Read-Write] The priority of this input component when pushed in to the stack.

instigator (Pawn): [Read-Write] Pawn responsible for damage and other gameplay events caused by this actor.

is_editor_only_actor (bool): [Read-Write] Whether this actor is editor-only. Use with care, as if this actor is referenced by anything else that reference will be NULL in cooked builds

is_main_world_only (bool): [Read-Write] If checked, this Actor will only get loaded in a main world (persistent level), it will not be loaded through Level Instances.

is_spatially_loaded (bool): [Read-Write] Determine if this actor is spatially loaded when placed in a partitioned world.
If true, this actor will be loaded when in the range of any streaming sources and if (1) in no data layers, or (2) one or more of its data layers are enabled. If false, this actor will be loaded if (1) in no data layers, or (2) one or more of its data layers are enabled.

layers (Array[Name]): [Read-Write] Layers the actor belongs to. This is outside of the editoronly data to allow hiding of LD-specified layers at runtime for profiling.

migrating_asset (bool): [Read-Write] If true, this actor can be migrated to another server even if it’s been loaded from disk

min_net_update_frequency (float): [Read-Write]

net_cull_distance_squared (float): [Read-Write]

net_dormancy (NetDormancy): [Read-Write] Dormancy setting for actor to take itself off of the replication list without being destroyed on clients.

net_load_on_client (bool): [Read-Write] This actor will be loaded on network clients during map load

net_priority (float): [Read-Write] Priority for this actor when checking for replication in a low bandwidth or saturated situation, higher priority means it is more likely to replicate

net_update_frequency (float): [Read-Write]

net_use_owner_relevancy (bool): [Read-Write] If actor has valid Owner, call Owner’s IsNetRelevantFor and GetNetPriority

on_actor_begin_overlap (ActorBeginOverlapSignature): [Read-Write] Called when another actor begins to overlap this actor, for example a player walking into a trigger. For events when objects have a blocking collision, for example a player hitting a wall, see ‘Hit’ events. note: Components on both this and the other Actor must have bGenerateOverlapEvents set to true to generate overlap events.

on_actor_end_overlap (ActorEndOverlapSignature): [Read-Write] Called when another actor stops overlapping this actor. note: Components on both this and the other Actor must have bGenerateOverlapEvents set to true to generate overlap events.

on_actor_hit (ActorHitSignature): [Read-Write] Called when this Actor hits (or is hit by) something solid. This could happen due to things like Character movement, using Set Location with ‘sweep’ enabled, or physics simulation. For events when objects overlap (e.g. walking into a trigger) see the ‘Overlap’ event. note: For collisions during physics simulation to generate hit events, ‘Simulation Generates Hit Events’ must be enabled.

on_begin_cursor_over (ActorBeginCursorOverSignature): [Read-Write] Called when the mouse cursor is moved over this actor if mouse over events are enabled in the player controller.

on_clicked (ActorOnClickedSignature): [Read-Write] Called when the left mouse button is clicked while the mouse is over this actor and click events are enabled in the player controller.

on_destroyed (ActorDestroyedSignature): [Read-Write] Event triggered when the actor has been explicitly destroyed.

on_end_cursor_over (ActorEndCursorOverSignature): [Read-Write] Called when the mouse cursor is moved off this actor if mouse over events are enabled in the player controller.

on_end_play (ActorEndPlaySignature): [Read-Write] Event triggered when the actor is being deleted or removed from a level.

on_input_touch_begin (ActorOnInputTouchBeginSignature): [Read-Write] Called when a touch input is received over this actor when touch events are enabled in the player controller.

on_input_touch_end (ActorOnInputTouchEndSignature): [Read-Write] Called when a touch input is received over this component when touch events are enabled in the player controller.

on_input_touch_enter (ActorBeginTouchOverSignature): [Read-Write] Called when a finger is moved over this actor when touch over events are enabled in the player controller.

on_input_touch_leave (ActorEndTouchOverSignature): [Read-Write] Called when a finger is moved off this actor when touch over events are enabled in the player controller.

on_released (ActorOnReleasedSignature): [Read-Write] Called when the left mouse button is released while the mouse is over this actor and click events are enabled in the player controller.

on_take_any_damage (TakeAnyDamageSignature): [Read-Write] Called when the actor is damaged in any way.

on_take_point_damage (TakePointDamageSignature): [Read-Write] Called when the actor is damaged by point damage.

on_take_radial_damage (TakeRadialDamageSignature): [Read-Write] Called when the actor is damaged by radial damage.

only_relevant_to_owner (bool): [Read-Write] If true, this actor is only relevant to its owner. If this flag is changed during play, all non-owner channels would need to be explicitly closed.

optimize_bp_component_data (bool): [Read-Write] Whether to cook additional data to speed up spawn events at runtime for any Blueprint classes based on this Actor. This option may slightly increase memory usage in a cooked build.

physics_replication_mode (PhysicsReplicationMode): [Read-Write] Which mode to replicate physics through for this actor. Only relevant if the actor replicates movement and has a component that simulate physics.

pivot_offset (Vector): [Read-Write] Local space pivot offset for the actor, only used in the editor

primary_actor_tick (ActorTickFunction): [Read-Write] Primary Actor tick function, which calls TickActor(). Tick functions can be configured to control whether ticking is enabled, at what time during a frame the update occurs, and to set up tick dependencies. see: https://docs.unrealengine.com/API/Runtime/Engine/Engine/FTickFunction see: AddTickPrerequisiteActor(), AddTickPrerequisiteComponent()

relevant_for_level_bounds (bool): [Read-Write] If true, this actor’s component’s bounds will be included in the level’s bounding box unless the Actor’s class has overridden IsLevelBoundsRelevant

remote_role (NetRole): [Read-Only] Describes how much control the remote machine has over the actor.

replay_rewindable (bool): [Read-Write] If true, this actor will only be destroyed during scrubbing if the replay is set to a time before the actor existed. Otherwise, RewindForReplay will be called if we detect the actor needs to be reset. Note, this Actor must not be destroyed by gamecode, and RollbackViaDeletion may not be used.

replicate_movement (bool): [Read-Write] If true, replicate movement/location related properties. Actor must also be set to replicate. see: SetReplicates() see: https://docs.unrealengine.com/InteractiveExperiences/Networking/Actors

replicate_using_registered_sub_object_list (bool): [Read-Write] When true the replication system will only replicate the registered subobjects and the replicated actor components list When false the replication system will instead call the virtual ReplicateSubobjects() function where the subobjects and actor components need to be manually replicated.

replicated_movement (RepMovement): [Read-Write] Used for replication of our RootComponent’s position and velocity

replicates (bool): [Read-Write] If true, this actor will replicate to remote machines see: SetReplicates()

role (NetRole): [Read-Only] Describes how much control the local machine has over the actor.

root_component (SceneComponent): [Read-Write] The component that defines the transform (location, rotation, scale) of this Actor in the world, all other components must be attached to this one somehow

runtime_grid (Name): [Read-Write] Determine in which partition grid this actor will be placed in the partition (if the world is partitioned). If None, the decision will be left to the partition.

shaded_volume_opacity_value (float): [Read-Write] Value used to set the opacity for the shaded volume, between 0-1

spawn_collision_handling_method (SpawnActorCollisionHandlingMethod): [Read-Write] Controls how to handle spawning this actor in a situation where it’s colliding with something else. “Default” means AlwaysSpawn here.

sprite_scale (float): [Read-Write] The scale to apply to any billboard components in editor builds (happens in any WITH_EDITOR build, including non-cooked games).

supported_agents (NavAgentSelector): [Read-Write]

tags (Array[Name]): [Read-Write] Array of tags that can be used for grouping and categorizing.

update_overlaps_method_during_level_streaming (ActorUpdateOverlapsMethod): [Read-Write] Condition for calling UpdateOverlaps() to initialize overlap state when loaded in during level streaming. If set to ‘UseConfigDefault’, the default specified in ini (displayed in

unreal.RecastNavMesh
class unreal.RecastNavMesh(outer: Object | None = None, name: Name | str = 'None')
Bases: NavigationData

Recast Nav Mesh

C++ Source:

Module: NavigationSystem

File: RecastNavMesh.h

Editor Properties: (see get_editor_property/set_editor_property)

actor_guid (Guid): [Read-Write] The GUID for this actor; this guid will be the same for actors from instanced streaming levels. see: ActorInstanceGuid, FActorInstanceGuidMapper note: Don’t use VisibleAnywhere here to avoid getting the CPF_Edit flag and get this property reset when resetting to defaults. See FActorDetails::AddActorCategory and EditorUtilities::CopySingleProperty for details.

actor_instance_guid (Guid): [Read-Write] The instance GUID for this actor; this guid will be unique for actors from instanced streaming levels. see: ActorGuid note: This is not guaranteed to be valid during PostLoad, but safe to access from RegisterAllComponents.

agent_height (float): [Read-Write] Size of the tallest agent that will path with this navmesh.

agent_max_slope (float): [Read-Write] The maximum slope (angle) that the agent can move on.

agent_max_step_height (float): [Read-Write] deprecated: Use NavMeshResolutionParams to set AgentMaxStepHeight for the different resolutions instead

agent_radius (float): [Read-Write] Radius of smallest agent to traverse this navmesh

allow_tick_before_begin_play (bool): [Read-Write] Whether we allow this Actor to tick before it receives the BeginPlay event. Normally we don’t tick actors until after BeginPlay; this setting allows this behavior to be overridden. This Actor must be able to tick for this setting to be relevant.

always_relevant (bool): [Read-Write] Always relevant for network (overrides bOnlyRelevantToOwner).

async_physics_tick_enabled (bool): [Read-Write] Whether to use use the async physics tick with this actor.

auto_destroy_when_finished (bool): [Read-Write] If true then destroy self when “finished”, meaning all relevant components report that they are done and no timelines or timers are in flight.

auto_destroy_when_no_navigation (bool): [Read-Write] Should this instance auto-destroy when there’s no navigation system on
world when it gets created/loaded

auto_receive_input (AutoReceiveInput): [Read-Write] Automatically registers this actor to receive input from a player.

block_input (bool): [Read-Write] If true, all input on the stack below this actor will not be considered

call_pre_replication (bool): [Read-Write]

call_pre_replication_for_replay (bool): [Read-Write]

can_be_damaged (bool): [Read-Write] Whether this actor can take damage. Must be true for damage events (e.g. ReceiveDamage()) to be called. see: https://www.unrealengine.com/blog/damage-in-ue4 see: TakeDamage(), ReceiveDamage()

can_be_in_cluster (bool): [Read-Write] If true, this actor can be put inside of a GC Cluster to improve Garbage Collection performance

can_be_main_nav_data (bool): [Read-Write] If set, navigation data can act as default one in navigation system’s queries

can_spawn_on_rebuild (bool): [Read-Only] If set, navigation data will be spawned in persistent level during rebuild if actor doesn’t exist

cell_height (float): [Read-Write] deprecated: Use NavMeshResolutionParams to set CellHeight for the different resolutions instead

cell_size (float): [Read-Write] deprecated: Use NavMeshResolutionParams to set CellSize for the different resolutions instead

content_bundle_guid (Guid): [Read-Write] The GUID for this actor’s content bundle.

custom_time_dilation (float): [Read-Write] Allow each actor to run at a different time speed. The DeltaTime for a frame is multiplied by the global TimeDilation (in WorldSettings) and this CustomTimeDilation for this actor’s tick.

data_layer_assets (Array[DataLayerAsset]): [Read-Write] DataLayers assets the actor belongs to.

data_layers (Array[ActorDataLayer]): [Read-Only] DataLayers the actor belongs to.

default_update_overlaps_method_during_level_streaming (ActorUpdateOverlapsMethod): [Read-Only] Default value taken from config file for this class when ‘UseConfigDefault’ is chosen for ‘UpdateOverlapsMethodDuringLevelStreaming’. This allows a default to be chosen per class in the matching config. For example, for Actor it could be specified in DefaultEngine.ini as:

[/Script/Engine.Actor] DefaultUpdateOverlapsMethodDuringLevelStreaming = OnlyUpdateMovable

Another subclass could set their default to something different, such as:

[/Script/Engine.BlockingVolume] DefaultUpdateOverlapsMethodDuringLevelStreaming = NeverUpdate see: UpdateOverlapsMethodDuringLevelStreaming

do_fully_async_nav_data_gathering (bool): [Read-Write] if set, navmesh data gathering will never happen on the game thread and will only be done on background threads

draw_clusters (bool): [Read-Write] Draw navmesh’s clusters and cluster links. (Requires WITH_NAVMESH_CLUSTER_LINKS=1)

draw_default_polygon_cost (bool): [Read-Write] Draw a label for every poly that indicates its default and fixed costs

draw_failed_nav_links (bool): [Read-Write] Draw failed links and valid links.

draw_filled_polys (bool): [Read-Write] if disabled skips filling drawn navmesh polygons

draw_labels_on_path_nodes (bool): [Read-Write]

draw_marked_forbidden_polys (bool): [Read-Write]

draw_nav_links (bool): [Read-Write] Draw valid links (both ends are valid).

draw_nav_mesh_edges (bool): [Read-Write] Draw border-edges

draw_octree (bool): [Read-Write] Draw octree used to store navigation relevant actors

draw_octree_details (bool): [Read-Write] Draw octree used to store navigation relevant actors with the elements bounds

draw_offset (float): [Read-Write] vertical offset added to navmesh’s debug representation for better readability

draw_path_colliding_geometry (bool): [Read-Write] Draw input geometry passed to the navmesh generator. Recommend disabling other geometry rendering via viewport showflags in editor.

draw_poly_edges (bool): [Read-Write] Draw edges of every poly (i.e. not only border-edges)

draw_polygon_area_i_ds (bool): [Read-Write] Draw a label for every poly that indicates its area id and the list of all NavAreaClass used in the displayed tiles.

draw_polygon_flags (bool): [Read-Write] Draw a label for every poly that indicates its poly and area flags

draw_polygon_labels (bool): [Read-Write] Draw a label for every poly that indicates its poly and tile indices

draw_tile_bounds (bool): [Read-Write] Draw the tile boundaries

draw_tile_build_times (bool): [Read-Write]

draw_tile_build_times_heat_map (bool): [Read-Write]

draw_tile_labels (bool): [Read-Write]

draw_tile_resolutions (bool): [Read-Write] Draw the tile resolutions

draw_triangle_edges (bool): [Read-Write] Draw edges of every navmesh’s triangle

enable_auto_lod_generation (bool): [Read-Write] Whether this actor should be considered or not during HLOD generation.

enable_drawing (bool): [Read-Write] if set to true then this navigation data will be drawing itself when requested as part of “show navigation”

expected_max_layers_per_tile (int32): [Read-Write] Used when connecting segment links across layers to determine how much memory to allocate to hold skipped layers

external_data_layer_asset (ExternalDataLayerAsset): [Read-Only]

filter_low_span_from_tile_cache (bool): [Read-Write] if set, only low height spans with corresponding area modifier will be stored in tile cache (reduces memory, can’t modify without full tile rebuild)

filter_low_span_sequences (bool): [Read-Write] if set, only single low height span will be allowed under valid one

find_camera_component_when_view_target (bool): [Read-Write] If true, this actor should search for an owned camera component to view through when used as a view target.

fixed_tile_pool_size (bool): [Read-Write] if true, the NavMesh will allocate fixed size pool for tiles, should be enabled to support streaming

force_rebuild_on_load (bool): [Read-Write] By default navigation will skip the first update after being successfully loaded setting bForceRebuildOnLoad to false can override this behavior

generate_nav_links (bool): [Read-Write] Experimental: if set, navlinks will be automatically generated. see: FNavLinkGenerationJumpConfig

generate_overlap_events_during_level_streaming (bool): [Read-Write] If true, this actor will generate overlap Begin/End events when spawned as part of level streaming, which includes initial level load. You might enable this is in the case where a streaming level loads around an actor and you want Begin/End overlap events to trigger. see: UpdateOverlapsMethodDuringLevelStreaming

heuristic_scale (float): [Read-Write] Euclidean distance heuristic scale used while pathfinding

hidden (bool): [Read-Write] Allows us to only see this Actor in the Editor, and not in the actual game. see: SetActorHiddenInGame()

hlod_layer (HLODLayer): [Read-Write] The UHLODLayer in which this actor should be included.

ignores_origin_shifting (bool): [Read-Write] Whether this actor should not be affected by world origin shifting.

initial_life_span (float): [Read-Write] How long this Actor lives before dying, 0=forever. Note this is the INITIAL value and should not be modified once play has begun.

input_priority (int32): [Read-Write] The priority of this input component when pushed in to the stack.

instigator (Pawn): [Read-Write] Pawn responsible for damage and other gameplay events caused by this actor.

invoker_tile_priority_bump_distance_threshold_in_tile_units (uint32): [Read-Write] If >= 1, when sorting pending tiles by priority, tiles near invokers (within the distance threshold) will have their priority increased.

invoker_tile_priority_bump_increase (uint8): [Read-Write] Priority increase steps for tiles that are withing near distance.

is_editor_only_actor (bool): [Read-Write] Whether this actor is editor-only. Use with care, as if this actor is referenced by anything else that reference will be NULL in cooked builds

is_main_world_only (bool): [Read-Write] If checked, this Actor will only get loaded in a main world (persistent level), it will not be loaded through Level Instances.

is_spatially_loaded (bool): [Read-Write] Determine if this actor is spatially loaded when placed in a partitioned world.
If true, this actor will be loaded when in the range of any streaming sources and if (1) in no data layers, or (2) one or more of its data layers are enabled. If false, this actor will be loaded if (1) in no data layers, or (2) one or more of its data layers are enabled.

is_world_partitioned (bool): [Read-Write] In a world partitioned map, is this navmesh using world partitioning

layer_chunk_splits (int32): [Read-Write] number of chunk splits (along single axis) used for layer’s partitioning: ChunkyMonotone

layer_partitioning (RecastPartitioning): [Read-Write] partitioning method for creating tile layers

layers (Array[Name]): [Read-Write] Layers the actor belongs to. This is outside of the editoronly data to allow hiding of LD-specified layers at runtime for profiling.

ledge_slope_filter_mode (NavigationLedgeSlopeFilterMode): [Read-Write] filtering methode used for filtering ledge slopes

mark_low_height_areas (bool): [Read-Write] mark areas with insufficient free height above instead of cutting them out (accessible only for area modifiers using replace mode)

max_simplification_error (float): [Read-Write] How much navigable shapes can get simplified - the higher the value the more freedom

max_simultaneous_tile_generation_jobs_count (int32): [Read-Write] Sets the limit for number of asynchronous tile generators running at one time, also used for some synchronous tasks

merge_region_size (float): [Read-Write] The size limit of regions to be merged with bigger regions (watershed partitioning only)

migrating_asset (bool): [Read-Write] If true, this actor can be migrated to another server even if it’s been loaded from disk

min_net_update_frequency (float): [Read-Write]

min_region_area (float): [Read-Write] The minimum dimension of area. Areas smaller than this will be discarded

nav_link_jump_configs (Array[NavLinkGenerationJumpConfig]): [Read-Write] Experimental configurations to generate jump links.

nav_mesh_origin_offset (Vector): [Read-Write] Use this if you don’t want your tiles to start at (0,0,0)

nav_mesh_resolution_params (NavMeshResolutionParam): [Read-Write] Resolution params If using multiple resolutions, it’s recommended to choose the highest resolution first and set it according to the highest desired precision and then the other resolutions.

net_cull_distance_squared (float): [Read-Write]

net_dormancy (NetDormancy): [Read-Write] Dormancy setting for actor to take itself off of the replication list without being destroyed on clients.

net_load_on_client (bool): [Read-Write] This actor will be loaded on network clients during map load

net_priority (float): [Read-Write] Priority for this actor when checking for replication in a low bandwidth or saturated situation, higher priority means it is more likely to replicate

net_update_frequency (float): [Read-Write]

net_use_owner_relevancy (bool): [Read-Write] If actor has valid Owner, call Owner’s IsNetRelevantFor and GetNetPriority

observed_paths_tick_interval (float): [Read-Write] all observed paths will be processed every ObservedPathsTickInterval seconds

on_actor_begin_overlap (ActorBeginOverlapSignature): [Read-Write] Called when another actor begins to overlap this actor, for example a player walking into a trigger. For events when objects have a blocking collision, for example a player hitting a wall, see ‘Hit’ events. note: Components on both this and the other Actor must have bGenerateOverlapEvents set to true to generate overlap events.

on_actor_end_overlap (ActorEndOverlapSignature): [Read-Write] Called when another actor stops overlapping this actor. note: Components on both this and the other Actor must have bGenerateOverlapEvents set to true to generate overlap events.

on_actor_hit (ActorHitSignature): [Read-Write] Called when this Actor hits (or is hit by) something solid. This could happen due to things like Character movement, using Set Location with ‘sweep’ enabled, or physics simulation. For events when objects overlap (e.g. walking into a trigger) see the ‘Overlap’ event. note: For collisions during physics simulation to generate hit events, ‘Simulation Generates Hit Events’ must be enabled.

on_begin_cursor_over (ActorBeginCursorOverSignature): [Read-Write] Called when the mouse cursor is moved over this actor if mouse over events are enabled in the player controller.

on_clicked (ActorOnClickedSignature): [Read-Write] Called when the left mouse button is clicked while the mouse is over this actor and click events are enabled in the player controller.

on_destroyed (ActorDestroyedSignature): [Read-Write] Event triggered when the actor has been explicitly destroyed.

on_end_cursor_over (ActorEndCursorOverSignature): [Read-Write] Called when the mouse cursor is moved off this actor if mouse over events are enabled in the player controller.

on_end_play (ActorEndPlaySignature): [Read-Write] Event triggered when the actor is being deleted or removed from a level.

on_input_touch_begin (ActorOnInputTouchBeginSignature): [Read-Write] Called when a touch input is received over this actor when touch events are enabled in the player controller.

on_input_touch_end (ActorOnInputTouchEndSignature): [Read-Write] Called when a touch input is received over this component when touch events are enabled in the player controller.

on_input_touch_enter (ActorBeginTouchOverSignature): [Read-Write] Called when a finger is moved over this actor when touch over events are enabled in the player controller.

on_input_touch_leave (ActorEndTouchOverSignature): [Read-Write] Called when a finger is moved off this actor when touch over events are enabled in the player controller.

on_released (ActorOnReleasedSignature): [Read-Write] Called when the left mouse button is released while the mouse is over this actor and click events are enabled in the player controller.

on_take_any_damage (TakeAnyDamageSignature): [Read-Write] Called when the actor is damaged in any way.

on_take_point_damage (TakePointDamageSignature): [Read-Write] Called when the actor is damaged by point damage.

on_take_radial_damage (TakeRadialDamageSignature): [Read-Write] Called when the actor is damaged by radial damage.

only_relevant_to_owner (bool): [Read-Write] If true, this actor is only relevant to its owner. If this flag is changed during play, all non-owner channels would need to be explicitly closed.

optimize_bp_component_data (bool): [Read-Write] Whether to cook additional data to speed up spawn events at runtime for any Blueprint classes based on this Actor. This option may slightly increase memory usage in a cooked build.

perform_voxel_filtering (bool): [Read-Write] controls whether voxel filtering will be applied (via FRecastTileGenerator::ApplyVoxelFilter).
Results in generated navmesh better fitting navigation bounds, but hits (a bit) generation performance

physics_replication_mode (PhysicsReplicationMode): [Read-Write] Which mode to replicate physics through for this actor. Only relevant if the actor replicates movement and has a component that simulate physics.

pivot_offset (Vector): [Read-Write] Local space pivot offset for the actor, only used in the editor

poly_ref_nav_poly_bits (int32): [Read-Only]

poly_ref_salt_bits (int32): [Read-Only]

poly_ref_tile_bits (int32): [Read-Only]

primary_actor_tick (ActorTickFunction): [Read-Write] Primary Actor tick function, which calls TickActor(). Tick functions can be configured to control whether ticking is enabled, at what time during a frame the update occurs, and to set up tick dependencies. see: https://docs.unrealengine.com/API/Runtime/Engine/Engine/FTickFunction see: AddTickPrerequisiteActor(), AddTickPrerequisiteComponent()

region_chunk_splits (int32): [Read-Write] number of chunk splits (along single axis) used for region’s partitioning: ChunkyMonotone

region_partitioning (RecastPartitioning): [Read-Write] partitioning method for creating navmesh polys

relevant_for_level_bounds (bool): [Read-Write] If true, this actor’s component’s bounds will be included in the level’s bounding box unless the Actor’s class has overridden IsLevelBoundsRelevant

remote_role (NetRole): [Read-Only] Describes how much control the remote machine has over the actor.

replay_rewindable (bool): [Read-Write] If true, this actor will only be destroyed during scrubbing if the replay is set to a time before the actor existed. Otherwise, RewindForReplay will be called if we detect the actor needs to be reset. Note, this Actor must not be destroyed by gamecode, and RollbackViaDeletion may not be used.

replicate_movement (bool): [Read-Write] If true, replicate movement/location related properties. Actor must also be set to replicate. see: SetReplicates() see: https://docs.unrealengine.com/InteractiveExperiences/Networking/Actors

replicate_using_registered_sub_object_list (bool): [Read-Write] When true the replication system will only replicate the registered subobjects and the replicated actor components list When false the replication system will instead call the virtual ReplicateSubobjects() function where the subobjects and actor components need to be manually replicated.

replicated_movement (RepMovement): [Read-Write] Used for replication of our RootComponent’s position and velocity

replicates (bool): [Read-Write] If true, this actor will replicate to remote machines see: SetReplicates()

role (NetRole): [Read-Only] Describes how much control the local machine has over the actor.

root_component (SceneComponent): [Read-Write] The component that defines the transform (location, rotation, scale) of this Actor in the world, all other components must be attached to this one somehow

runtime_generation (RuntimeGenerationType): [Read-Write] Navigation data runtime generation options

runtime_grid (Name): [Read-Write] Determine in which partition grid this actor will be placed in the partition (if the world is partitioned). If None, the decision will be left to the partition.

simplification_elevation_ratio (float): [Read-Write] When simplifying contours, how much is the vertical error taken into account when comparing with MaxSimplificationError. Use 0 to deactivate (Recast behavior), use 1 as a typical value.

sort_navigation_areas_by_cost (bool): [Read-Write] Controls whether Navigation Areas will be sorted by cost before application
to navmesh during navmesh generation. This is relevant when there are areas overlapping and we want to have area cost express area relevancy as well. Setting it to true will result in having area sorted by cost, but it will also increase navmesh generation cost a bit

spawn_collision_handling_method (SpawnActorCollisionHandlingMethod): [Read-Write] Controls how to handle spawning this actor in a situation where it’s colliding with something else. “Default” means AlwaysSpawn here.

sprite_scale (float): [Read-Write] The scale to apply to any billboard components in editor builds (happens in any WITH_EDITOR build, including non-cooked games).

tags (Array[Name]): [Read-Write] Array of tags that can be used for grouping and categorizing.

tile_generation_debug (RecastNavMeshTileGenerationDebug): [Read-Write]

tile_number_hard_limit (int32): [Read-Write] Absolute hard limit to number of navmesh tiles. Be very, very careful while modifying it while
having big maps with navmesh. A single, empty tile takes 176 bytes and empty tiles are allocated up front (subject to change, but that’s where it’s at now)

note: TileNumberHardLimit is always rounded up to the closest power of 2

tile_pool_size (int32): [Read-Write] maximum number of tiles NavMesh can hold

tile_size_uu (float): [Read-Write] size of single tile, expressed in uu

time_slice_filter_ledge_spans_max_y_process (int32): [Read-Write] The maximum number of y coords to process when time slicing filter ledge spans during navmesh regeneration.

time_slice_long_duration_debug (double): [Read-Write] If a single time sliced section of navmesh regen code exceeds this duration then it will trigger debug logging

update_overlaps_method_during_level_streaming (ActorUpdateOverlapsMethod): [Read-Write] Condition for calling UpdateOverlaps() to initialize overlap state when loaded in during level streaming. If set to ‘UseConfigDefault’, the default specified in ini (displayed in ‘DefaultUpdateOverlapsMethodDuringLevelStreaming’) will be used. If overlaps are not initialized, this actor and attached components will not have an initial state of what objects are touching it, and overlap events may only come in once one of those objects update overlaps themselves (for example when moving). However if an object touching it does initialize state, both objects will know about their touching state with each other. This can be a potentially large performance savings during level loading and streaming, and is safe if the object and others initially overlapping it do not need the overlap state because they will not trigger overlap notifications.

Note that if ‘bGenerateOverlapEventsDuringLevelStreaming’ is true, overlaps are always updated in this case, but that flag determines whether the Begin/End overlap events are triggered. see: bGenerateOverlapEventsDuringLevelStreaming, DefaultUpdateOverlapsMethodDuringLevelStreaming, GetUpdateOverlapsMethodDuringLevelStreaming()

use_extra_top_cell_when_marking_areas (bool): [Read-Write] Expand the top of the area nav modifier’s bounds by one cell height when applying to the navmesh.
If unset, navmesh on top of surfaces might not be marked by marking bounds flush with top surfaces (since navmesh is generated slightly above collision, depending on cell height).

vertical_deviation_from_ground_compensation (float): [Read-Write] Value added to each search height to compensate for error between navmesh polys and walkable geometry

property agent_max_step_height: float
[Read-Write] deprecated: Use NavMeshResolutionParams to set AgentMaxStepHeight for the different resolutions instead

Type:
(float)

property cell_height: float
[Read-Write] deprecated: Use NavMeshResolutionParams to set CellHeight for the different resolutions instead

Type:
(float)

property cell_size: float
[Read-Write] deprecated: Use NavMeshResolutionParams to set CellSize for the different resolutions instead

Type:
(float)

k2_replace_area_in_tile_bounds(bounds, old_area, new_area, replace_links=True) → bool
Parameters:
bounds (Box)

old_area (type(Class))

new_area (type(Class))

replace_links (bool)

Returns:
true if any polygon/link has been touched

Return type:
bool

class unreal.NavigationSystemV1(outer: Object | None = None, name: Name | str = 'None')
Bases: NavigationSystemBase

Navigation System V1

C++ Source:

Module: NavigationSystem

File: NavigationSystem.h

Editor Properties: (see get_editor_property/set_editor_property)

active_tiles_update_interval (float): [Read-Write] Minimal time, in seconds, between active tiles set update

allow_client_side_navigation (bool): [Read-Write] If false, will not create nav collision when connecting as a client

auto_create_navigation_data (bool): [Read-Write] Should navigation system spawn default Navigation Data when there’s none and there are navigation bounds present?

crowd_manager_class (Class): [Read-Write]

data_gathering_mode (NavDataGatheringModeConfig): [Read-Write] Sets how navigation data should be gathered when building collision information

default_agent_name (Name): [Read-Write] If not None indicates which of navigation datas and supported agents are going to be used as the default ones. If navigation agent of this type does not exist or is not enabled then the first available nav data will be used as the default one

dirty_area_warning_size_threshold (float): [Read-Write] -1 by default, if set to a positive value dirty areas with any dimensions in 2d over the threshold created at runtime will be logged

gathering_nav_modifiers_warning_limit_time (float): [Read-Write] -1.0f by default, if set to a positive value, all calls to GetNavigationData will be timed and compared to it.
Over the limit calls will be logged as warnings. In seconds. Non-shipping build only.

generate_navigation_only_around_navigation_invokers (bool): [Read-Write] If set to true navigation will be generated only around registered “navigation enforcers”
This has a range of consequences (including how navigation octree operates) so it needs to be a conscious decision. Once enabled results in whole world being navigable.

see: RegisterNavigationInvoker

geometry_export_triangle_count_warning_threshold (int32): [Read-Write] Warnings are logged if exporting the navigation collision for an object exceed this triangle count. Use -1 to disable.

initial_building_locked (bool): [Read-Write] if set to true will result navigation system not rebuild navigation until
a call to ReleaseInitialBuildingLock() is called. Does not influence editor-time generation (i.e. does influence PIE and Game). Defaults to false.

invokers_maximum_distance_from_seed (double): [Read-Write] When in use, invokers farther away from any invoker seed will be ignored (set to -1 to disable).

on_navigation_generation_finished_delegate (OnNavDataGenericEvent): [Read-Write]

should_discard_sub_level_nav_data (bool): [Read-Write] If true, games should ignore navigation data inside loaded sublevels

skip_agent_height_check_when_picking_nav_data (bool): [Read-Write] false by default, if set to true will result in not caring about nav agent height
when trying to match navigation data to passed in nav agent

spawn_nav_data_in_nav_bounds_level (bool): [Read-Write] If true will try to spawn the navigation data instance in the sublevel with navigation bounds, if false it will spawn in the persistent level

supported_agents (Array[NavDataConfig]): [Read-Write] List of agents types supported by this navigation system

supported_agents_mask (NavAgentSelector): [Read-Write] NavigationSystem’s properties in Project Settings define all possible supported agents,
but a specific navigation system can choose to support only a subset of agents. Set via NavigationSystemConfig

tick_while_paused (bool): [Read-Write] If true, will update navigation even when the game is paused

property crowd_manager_class: Class
[Read-Only]

Type:
(Class)

property default_agent_name: Name
[Read-Only] If not None indicates which of navigation datas and supported agents are going to be used as the default ones. If navigation agent of this type does not exist or is not enabled then the first available nav data will be used as the default one

Type:
(Name)

classmethod find_path_to_actor_synchronously(world_context_object, path_start, goal_actor, tether_distance=50.000000, pathfinding_context=None, filter_class=None) → NavigationPath
Finds path instantly, in a FindPath Synchronously. Main advantage over FindPathToLocationSynchronously is that
the resulting path will automatically get updated if goal actor moves more than TetherDistance away from last path node

Parameters:
world_context_object (Object)

path_start (Vector)

goal_actor (Actor)

tether_distance (float)

pathfinding_context (Actor) – could be one of following: NavigationData (like Navmesh actor), Pawn or Controller. This parameter determines parameters of specific pathfinding query

filter_class (type(Class))

Return type:
NavigationPath

classmethod find_path_to_location_synchronously(world_context_object, path_start, path_end, pathfinding_context=None, filter_class=None) → NavigationPath
Finds path instantly, in a FindPath Synchronously.

Parameters:
world_context_object (Object)

path_start (Vector)

path_end (Vector)

pathfinding_context (Actor) – could be one of following: NavigationData (like Navmesh actor), Pawn or Controller. This parameter determines parameters of specific pathfinding query

filter_class (type(Class))

Return type:
NavigationPath

classmethod get_navigation_system(world_context_object) → NavigationSystemV1
Blueprint functions

Parameters:
world_context_object (Object)

Return type:
NavigationSystemV1

classmethod get_path_cost(world_context_object, path_start, path_end, nav_data=None, filter_class=None) -> (NavigationQueryResult, path_cost=double)
Potentially expensive. Use with caution. Consider using UPathFollowingComponent::GetRemainingPathCost instead

Parameters:
world_context_object (Object)

path_start (Vector)

path_end (Vector)

nav_data (NavigationData)

filter_class (type(Class))

Returns:
path_cost (double):

Return type:
double

classmethod get_path_length(world_context_object, path_start, path_end, nav_data=None, filter_class=None) -> (NavigationQueryResult, path_length=double)
Potentially expensive. Use with caution

Parameters:
world_context_object (Object)

path_start (Vector)

path_end (Vector)

nav_data (NavigationData)

filter_class (type(Class))

Returns:
path_length (double):

Return type:
double

classmethod get_random_location_in_navigable_radius(world_context_object, origin, radius, nav_data=None, filter_class=None) → Vector or None
Generates a random location in navigable space within given radius of Origin.

Parameters:
world_context_object (Object)

origin (Vector)

radius (float)

nav_data (NavigationData)

filter_class (type(Class))

Returns:
Return Value represents if the call was successful

random_location (Vector):

Return type:
Vector or None

classmethod get_random_point_in_navigable_radius(world_context_object, origin, radius, nav_data=None, filter_class=None) → Vector or None
K2 Get Random Point in Navigable Radius deprecated: GetRandomPointInNavigableRadius is deprecated. Use GetRandomLocationInNavigableRadius instead

Parameters:
world_context_object (Object)

origin (Vector)

radius (float)

nav_data (NavigationData)

filter_class (type(Class))

Returns:
random_location (Vector):

Return type:
Vector or None

classmethod get_random_reachable_point_in_radius(world_context_object, origin, radius, nav_data=None, filter_class=None) → Vector or None
Generates a random location reachable from given Origin location.

Parameters:
world_context_object (Object)

origin (Vector)

radius (float)

nav_data (NavigationData)

filter_class (type(Class))

Returns:
Return Value represents if the call was successful

random_location (Vector):

Return type:
Vector or None

classmethod is_navigation_being_built(world_context_object) → bool
Is Navigation Being Built

Parameters:
world_context_object (Object)

Return type:
bool

classmethod is_navigation_being_built_or_locked(world_context_object) → bool
Is Navigation Being Built or Locked

Parameters:
world_context_object (Object)

Return type:
bool

k2_replace_area_in_octree_data(object, old_area, new_area) → bool
K2 Replace Area in Octree Data

Parameters:
object (Object)

old_area (type(Class))

new_area (type(Class))

Return type:
bool

classmethod navigation_raycast(world_context_object, ray_start, ray_end, filter_class=None, querier=None) → Vector or None
Performs navigation raycast on NavigationData appropriate for given Querier.

Parameters:
world_context_object (Object)

ray_start (Vector)

ray_end (Vector)

filter_class (type(Class))

querier (Controller) – if not passed default navigation data will be used

Returns:
true if line from RayStart to RayEnd was obstructed. Also, true when no navigation data present

hit_location (Vector): if line was obstructed this will be set to hit location. Otherwise it contains SegmentEnd

Return type:
Vector or None

on_navigation_bounds_updated(nav_volume) → None
todo: document

Parameters:
nav_volume (NavMeshBoundsVolume)

property on_navigation_generation_finished_delegate: OnNavDataGenericEvent
[Read-Write]

Type:
(OnNavDataGenericEvent)

classmethod project_point_to_navigation(world_context_object, point, nav_data, filter_class, query_extent=[0.000000, 0.000000, 0.000000]) → Vector or None
Project a point onto the NavigationData

Parameters:
world_context_object (Object)

point (Vector)

nav_data (NavigationData)

filter_class (type(Class))

query_extent (Vector)

Returns:
projected_location (Vector):

Return type:
Vector or None

register_navigation_invoker(invoker, tile_generation_radius=3000.000000, tile_removal_radius=5000.000000) → None
Registers given actor as a “navigation enforcer” which means navigation system will
make sure navigation is being generated in specified radius around it.

note:: you need NavigationSystem’s GenerateNavigationOnlyAroundNavigationInvokers to be set to true to take advantage of this feature

Parameters:
invoker (Actor)

tile_generation_radius (float)

tile_removal_radius (float)

reset_max_simultaneous_tile_generation_jobs_count() → None
Brings limit of simultaneous navmesh tile generation jobs back to Project Setting’s default value

set_geometry_gathering_mode(new_mode) → None
Set Geometry Gathering Mode

Parameters:
new_mode (NavDataGatheringModeConfig)

set_max_simultaneous_tile_generation_jobs_count(max_number_of_jobs) → None
will limit the number of simultaneously running navmesh tile generation jobs to specified number.

Parameters:
max_number_of_jobs (int32) – gets trimmed to be at least 1. You cannot use this function to pause navmesh generation

unregister_navigation_invoker(invoker) → None
Removes given actor from the list of active navigation enforcers. see: RegisterNavigationInvoker for more details

Parameters:
invoker (Actor)