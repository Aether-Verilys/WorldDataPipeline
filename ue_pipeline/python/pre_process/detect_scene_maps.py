"""
Detect all .umap files in UE project's Content directory
"""
import os
import json
import unreal
from pathlib import Path


def get_project_content_path():
    """Get the project's Content directory absolute path"""
    project_dir = unreal.Paths.project_dir()
    content_path = os.path.join(project_dir, "Content")
    return content_path


def find_all_umap_files(content_path):
    """
    Find all .umap files in Content directory
    
    Args:
        content_path: Absolute path to Content directory
        
    Returns:
        List of dict with umap info: {'name', 'relative_path', 'absolute_path', 'package_path'}
    """
    umap_files = []
    
    for root, dirs, files in os.walk(content_path):
        for file in files:
            if file.endswith('.umap'):
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, content_path)
                
                # Convert to UE package path
                # E.g., Maps/MyLevel.umap -> /Game/Maps/MyLevel
                package_path = rel_path.replace('\\', '/')
                package_path = '/Game/' + package_path.replace('.umap', '')
                
                map_name = os.path.splitext(file)[0]
                
                umap_files.append({
                    'name': map_name,
                    'relative_path': rel_path,
                    'absolute_path': abs_path,
                    'package_path': package_path
                })
    
    return umap_files


def detect_scene_maps():
    """Main function to detect all scene maps"""
    unreal.log("=" * 60)
    unreal.log("Detecting Scene Maps (.umap files)")
    unreal.log("=" * 60)
    
    content_path = get_project_content_path()
    unreal.log(f"Content Path: {content_path}")
    
    if not os.path.exists(content_path):
        unreal.log_error(f"Content path does not exist: {content_path}")
        return []
    
    umap_files = find_all_umap_files(content_path)
    
    unreal.log(f"\nFound {len(umap_files)} .umap file(s):")
    for i, umap in enumerate(umap_files, 1):
        unreal.log(f"  {i}. {umap['name']}")
        unreal.log(f"     Package: {umap['package_path']}")
        unreal.log(f"     Path: {umap['relative_path']}")
    
    unreal.log("=" * 60)
    
    return umap_files


def export_to_json(umap_files, output_path):
    """Export detected maps to JSON file"""
    data = {
        'detected_maps': umap_files,
        'total_count': len(umap_files)
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    unreal.log(f"Exported to: {output_path}")


if __name__ == "__main__":
    maps = detect_scene_maps()
    
    # Optional: Export to JSON
    # output_json = "E:/WorldDataPipeline/ue_pipeline/scenes/detected_maps.json"
    # export_to_json(maps, output_json)
